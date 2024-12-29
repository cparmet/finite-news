"""🎨 Layout: Organize the issue content into an HTML email """

import logging
from random import choice

from tasks.reporting import get_attributions, get_car_talk_credit


def get_weather_emoji(forecast):
    """
    Label a weather forecast with an emoji. It's used to spice up the section header.
    
    ARGUMENTS
    forecast (dict): Attributes of the forecast retrieved.
    
    RETURNS
    emoji (str): One character
    """

    forecast = forecast.lower()
    if "tornado" in forecast:
        return "🌪️"
    if "hurricane" in forecast:
        return "🌀"
    if "thunder" in forecast or "lightning" in forecast:
        return "⚡"
    if "snow" in forecast or "flurries" in forecast:
        return "❄️"
    if "rain" in forecast or "pour" in forecast or "shower" in forecast or "drizzle" in forecast: # Must come after snow for snow showers
        return "☔"
    if "hot" in forecast:
        return "🥵"
    if "freezing" in forecast:
        return "🥶"
    if "partly cloudy" in forecast or "mostly sunny" in forecast:
        return "🌤️"
    if "sunny" in forecast or "beautiful" in forecast or "warm" in forecast: # Must come after mostly sunny
        return "😎"
    if "mostly cloudy" in forecast:
        return "🌥️"
    if "cloudy" in forecast:
        return "☁️"
    if "windy" in forecast:
        return "🌬️"
    if "fog" in forecast or "smoke" in forecast:
        return "😶‍🌫️"
    return "🔮"


def populate_template(template_text, placeholder, new_content, html_list=None, condition=True):
    """Replaces placeholder text from a template with real content. 
    If there's no content, remove the placeholder.
    
    ARGUMENTS
    template_text (str): The text from a template we are filling in.
    placeholder (str): The characters in the template where content goes
    new_content (str): The content to add to the template, or None
    html_list (list): Optional, appends a list of items to end of `replacement` as html list. If this argument is passed, and list is empty, we remove placheolder altogether.
    condition (object, bool, or None): Optional, if False/None we replace placeholder with "" regardless of `new_content`. Usually this means some _piece_ of new_content must be non-Null, or we should remove the entire section
    
    RETURNS
    populated_text (str): The text with placeholder filled in or removed
    """
    # If placeholder doesn't exist in template, log that nothing will get populated below
    if placeholder not in template_text: 
        logging.warning(f"Template does not contain section so we cannot populate it. Placeholder: {placeholder}. Content to populate: {new_content}. Template text state: {template_text}")

    if not new_content or not condition: # This also checks if new_content is None (vs "")
        replacement = ""
    elif type(html_list)==list:     # If placeholder is populated by a list of items, insert that HTML into `replacement` string
        if len(html_list)>0:
            replacement = new_content + "<ul>" + ''.join([f'<li>{item}</li>' for item in html_list]) + "</ul>"
        else:
            replacement = ""
    else:
        replacement = new_content

    return template_text.replace(placeholder, replacement)


def format_issue(
    issue_config,
    content,
    log_stream=None
):
    """Organize the final content as HTML for one subscriber's issue.
    
    ARGUMENTS
    content (dict): The content to go into an issue, with these keys (although their values may be None/[]):
        - headlines (list of str): The final news headlines to be reported in this issue
        - forecast (dict): Forecast content, if any
        - events_html (str): HTML-formatted section with upcoming events
        - stock_plots (list of base64): List of pngs as base64
        - screenshots (list): Other images to attach to the image
    issue_config (dict): The settings for the issue
    log_stream (String IO): Optional, the log report from running Finite News
    
    RETURNS
    html (str): The Finite News template populated with the final content
    """
        
    html = issue_config["layout"]["template_html"]
    
    html = populate_template(html, "[[LOGO_URL]]", issue_config["layout"]["logo_url"])
    html = populate_template(html, "[[SLOGAN]]", choice(issue_config.get("slogans", [""])))
    html = populate_template(html, "[[HEADLINES_BLOCK]]", "<h3>🗞️ News</h3>", content["headlines"])
    html = populate_template(html, "[[ALERTS_BLOCK]]", "<h3>🚨 Alert weeoooweeooo</h3>", content["alerts"])

    if content["forecast"]:
        weather_emoji = get_weather_emoji(content["forecast"]["short"])
        weather_icon = f"<img src={content['forecast']['icon_url']} alt='Forecast icon'><br>" if "icon_url" in content["forecast"] else ""
        weather_block = f"<h3>{weather_emoji} {content['forecast']['short']}</h3>{weather_icon}<p>{content['forecast']['detailed']}</p>"
    else:
        weather_block = ""
    html = populate_template(html, "[[WEATHER_BLOCK]]", weather_block)

    html = populate_template(html, "[[EVENTS_BLOCK]]", f"<h3>🪩 Upcoming events</h3>{content['events_html']}", condition=content["events_html"])
    stocks_block = "".join([f"<img src='cid:image_{i}', alt='image_{i}'><br>" for i in range(0,len(content["stock_plots"]))]) # Reference cids of images attached to email
    html = populate_template(html, "[[STOCKS_BLOCK]]", f"<h3>💰 Financial update</h3>{stocks_block}", condition=stocks_block)
    images_block = "".join([f"<img src='cid:image_{i + len(content['stock_plots'])}', alt='image_{i + len(content['stock_plots'])}'><br>" for i in range(0,len(content['images']) - len(content['stock_plots']) )]) # Increment cids if stock plots already attached to email
    image_urls_block = ''.join(content["image_urls"])
    html = populate_template(html, "[[IMAGES_BLOCK]]", f"<h3>📸 Finstagram</h3>{images_block}{image_urls_block}", condition=images_block+image_urls_block)

    try:
        thoughts = issue_config["thoughts_of_the_day"]
        if len(thoughts)==0:
            thoughts = [None] # To make choice() happy, it can't handle []
        html = populate_template(html, "[[THOUGHT_OF_THE_DAY]]", f"""<h3>💭 Thought for the day</h3><p>{choice(thoughts)}</p>""", condition=len(issue_config["thoughts_of_the_day"])>0)
    except TypeError as e:
        logging.warning(f"TypeError on replace closing thoughts. Yaml malfored?: {e}. thoughts_of_the_day type: {type(issue_config['thoughts_of_the_day'])}. Expected string. {issue_config['thoughts_of_the_day']}")
        html = populate_template(html, "[[THOUGHT_OF_THE_DAY]]","")

    # Credits section
    car_talk_block = "<p>" + get_car_talk_credit(issue_config["bucket_path"]) + "</p><br>" if issue_config["editorial"]["add_car_talk_credit"] else "" # We need this car_talk_block variable later too
    html = populate_template(html, "[[CAR_TALK_CREDIT]]", car_talk_block)
    attributions=get_attributions(
        general_sources=issue_config["news_sources"] + issue_config["events_sources"] + issue_config["alerts_sources"] + issue_config["image_sources"] ,
        sports_tracked=issue_config["sports"],
        weather_source=issue_config["forecast"].get("source", None),
        stocks_used=len(content["stock_plots"])>0,
        car_talk_used=issue_config["editorial"]["add_car_talk_credit"]
    )
    html = populate_template(html, "[[ATTRIBUTIONS]]", "<p><i>Sources used: " + ", ".join(attributions) + "</i></p>", condition=attributions)
    html = populate_template(html, "[[CREDITS_INTRO]]", "<h3>💝 Credits</h3>" if (len(attributions) + len(car_talk_block)) > 0 else "") # No attribtions or Car Talk credits? No credits section at all!
    
    # Append logs to admin's email, if we're in prod mode
    log_items = [l for l in log_stream.getvalue().split("\n") if len(l)>0] if log_stream else []
    html = populate_template(html, "[[LOGGING_BLOCK]]", f"<h3>👾 Logs</h3>", log_items, condition=issue_config["admin"] is True and log_items)
    
    return html