"""🎨 Layout: Organize the issue content into an HTML email"""

import logging
from random import choice

from tasks.reporting import get_attributions, get_car_talk_credit


def get_weather_emoji(forecast):
    """
    Label a weather forecast with an emoji. It's used to spice up the section header.

    ARGUMENTS
    forecast (dict): Attributes of the forecast retrieved.

    RETURNS
    The emoji as a one-character string
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
    # Showers must come after snow for snow showers
    if (
        "rain" in forecast
        or "pour" in forecast
        or "shower" in forecast
        or "drizzle" in forecast
    ):
        return "☔"
    if "hot" in forecast:
        return "🥵"
    if "freezing" in forecast:
        return "🥶"
    if "partly cloudy" in forecast or "mostly sunny" in forecast:
        return "🌤️"
    # Sunny must come after mostly sunny
    if "sunny" in forecast or "beautiful" in forecast or "warm" in forecast:
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


def populate_template(
    template_text, placeholder, new_content, html_list=None, condition=True
):
    """Replaces placeholder text from a template with real content.
    If there's no content, remove the placeholder.

    ARGUMENTS
    template_text (str): The text from a template we are filling in.
    placeholder (str): The characters in the template where content goes
    new_content (str): The content to add to the template, or None
    html_list (list): Optional, appends a list of items to end of `replacement` as html list. If this argument is passed, and list is empty, we remove placheolder altogether.
    condition (object, bool, or None): Optional, if False/None we replace placeholder with "" regardless of `new_content`. Usually this means some _piece_ of new_content must be non-Null, or we should remove the entire section

    RETURNS
    The text with placeholder filled in or removed
    """
    # If placeholder doesn't exist in template, log that nothing will get populated below
    if placeholder not in template_text:
        logging.warning(
            f"Template does not contain section so we cannot populate it. Placeholder: {placeholder}. Content to populate: {new_content}. Template text state: {template_text}"
        )

    if not new_content or not condition:
        # This also checks if new_content is None (vs "")
        replacement = ""
    elif isinstance(html_list, list):
        # If placeholder is populated by a list of items, insert that HTML into `replacement` string
        if len(html_list) > 0:
            replacement = (
                new_content
                + "<ul>"
                + "".join([f"<li>{item}</li>" for item in html_list])
                + "</ul>"
            )
        else:
            replacement = ""
    else:
        replacement = new_content

    return template_text.replace(placeholder, replacement)


def format_issue(issue_config, content, log_stream=None):
    """Organize the final content as HTML for one subscriber's issue.

    ARGUMENTS
    content (dict): The content to go into an issue, with these keys (although their values may be None/[]):
        - alerts (list of str): The alerts to be reported in this issue
        - headlines (list of str): The final news headlines to be reported in this issue
        - scoreboard (list of str): HTML formatted section with sports scores
        - forecast (dict): Forecast content, if any
        - events_html (str): HTML-formatted section with upcoming events
        - stock_plots (list of base64): List of pngs as base64
        - images (list of base64): Other images to attach to the image. Will combine stock_plots and screenshot images as one list
        - screenshot_headings (list of str): Headings for the screenshots that appear in images
    issue_config (dict): The settings for the issue
    log_stream (String IO): Optional, the log report from running Finite News

    RETURNS
    The Finite News template populated with the final content, in HTML as string
    """

    html = issue_config["layout"]["template_html"]

    html = populate_template(html, "[[LOGO_URL]]", issue_config["layout"]["logo_url"])
    html = populate_template(
        html, "[[SLOGAN]]", choice(issue_config.get("slogans", [""]))
    )
    html = populate_template(
        html, "[[ALERTS_BLOCK]]", "<h3>🚨 Alert weeoooweeooo</h3>", content["alerts"]
    )
    html = populate_template(
        html, "[[HEADLINES_BLOCK]]", "<h3>🗞️ News</h3>", content["headlines"]
    )
    scoreboard_block = "".join(content["scoreboard"])
    html = populate_template(
        html,
        "[[SCOREBOARD_BLOCK]]",
        f"<h3>🏟 Scoreboard</h3>{scoreboard_block}",
        condition=scoreboard_block,
    )

    if content["forecast"]:
        weather_emoji = get_weather_emoji(content["forecast"]["short"])
        weather_icon = (
            f"<img src={content['forecast']['icon_url']} alt='Forecast icon'><br>"
            if "icon_url" in content["forecast"]
            else ""
        )
        weather_block = f"<h3>{weather_emoji} {content['forecast']['short']}</h3>{weather_icon}<p>{content['forecast']['detailed']}</p>"
    else:
        weather_block = ""
    html = populate_template(html, "[[WEATHER_BLOCK]]", weather_block)

    html = populate_template(
        html,
        "[[EVENTS_BLOCK]]",
        f"<h3>🪩 Upcoming events</h3>{content['events_html']}",
        condition=content["events_html"],
    )
    # Reference the cids (filenames) of images attached to email
    stocks_block = "".join(
        [
            f"<img src='cid:image_{i}.png', alt='image_{i}.png'><br>"
            for i in range(0, len(content["stock_plots"]))
        ]
    )
    html = populate_template(
        html,
        "[[STOCKS_BLOCK]]",
        f"<h3>💰 Financial update</h3>{stocks_block}",
        condition=stocks_block,
    )
    # Create an HTML item for each image from get_screenshots().
    # Increment cids if stock plots already attached to email
    # since cid is the order of the attachment to the email

    cids = range(0, len(content["images"]) - len(content["stock_plots"]))
    cids_and_headings = zip(cids, content["screenshot_headings"])
    images_block = "".join(
        [
            f"<h4>{screenshot_heading}</h4><img src='cid:image_{cid_i + len(content['stock_plots'])}.png', alt='image_{cid_i + len(content['stock_plots'])}.png'><br>"
            for cid_i, screenshot_heading in cids_and_headings
        ]
    )
    image_urls_block = "".join(content["image_urls"])
    html = populate_template(
        html,
        "[[IMAGES_BLOCK]]",
        f"<h3>📸 Finstagram</h3>{images_block}{image_urls_block}",
        condition=images_block + image_urls_block,
    )

    try:
        thoughts = issue_config["thoughts_of_the_day"]
        if len(thoughts) == 0:
            # To make choice() happy, it can't handle []
            thoughts = [None]
        html = populate_template(
            html,
            "[[THOUGHT_OF_THE_DAY]]",
            f"""<h3>💭 Thought for the day</h3><p>{choice(thoughts)}</p>""",
            condition=len(issue_config["thoughts_of_the_day"]) > 0,
        )
    except TypeError as e:
        logging.warning(
            f"TypeError on replace closing thoughts. Yaml malfored?: {e}. thoughts_of_the_day type: {type(issue_config['thoughts_of_the_day'])}. Expected string. {issue_config['thoughts_of_the_day']}"
        )
        html = populate_template(html, "[[THOUGHT_OF_THE_DAY]]", "")

    # Credits section
    # We need this car_talk_block variable later too
    try:
        car_talk_credit = get_car_talk_credit()
        car_talk_block = (
            "<p>" + car_talk_credit + "</p><br>"
            if issue_config["editorial"]["add_car_talk_credit"]
            else ""
        )
    except Exception as e:
        logging.warning(
            f"""
            Malformed car talk credit {car_talk_credit}. Not added.
            
            {type(e)}: {e}
            """
        )
        car_talk_block = ""
    html = populate_template(html, "[[CAR_TALK_CREDIT]]", car_talk_block)

    attributions = get_attributions(
        general_sources=issue_config["news_sources"]
        + issue_config["events_sources"]
        + issue_config["alerts_sources"]
        + issue_config["image_sources"],
        sports_tracked=issue_config["sports"],
        weather_source=issue_config["forecast"].get("source", None),
        stocks_used=len(content["stock_plots"]) > 0,
        car_talk_used=issue_config["editorial"]["add_car_talk_credit"],
    )
    html = populate_template(
        html,
        "[[ATTRIBUTIONS]]",
        "<p><i>Sources used: " + ", ".join(attributions) + "</i></p>",
        condition=attributions,
    )
    # No attribtions or Car Talk credits? No credits section at all!
    html = populate_template(
        html,
        "[[CREDITS_INTRO]]",
        "<h3>💝 Credits</h3>" if (len(attributions) + len(car_talk_block)) > 0 else "",
    )

    # Append logs to admin's email, if we're in prod mode
    log_items = (
        [li for li in log_stream.getvalue().split("\n") if len(li) > 0]
        if log_stream
        else []
    )
    html = populate_template(
        html,
        "[[LOGGING_BLOCK]]",
        "<h3>👾 Logs</h3>",
        log_items,
        condition=issue_config["admin"] is True and log_items,
    )

    return html
