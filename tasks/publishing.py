"""📰 Publishing functions to deliver the news"""

from sendgrid import Attachment, SendGridAPIClient
from sendgrid.helpers.mail import Mail
from datetime import date, datetime
import logging

from tasks.editing import edit_headlines, unnest_list, cache_issue_content
from tasks.layout import format_issue
from tasks.io import get_fn_secret
from tasks.reporting import dedup, research_source, get_screenshots
from tasks.sports import get_todays_nba_game, edit_sports_headlines, get_todays_nhl_game
from tasks.stocks import get_stocks_plot
from tasks.weather import get_forecast


def email_issue(sender, subscriber_email, html, images):
    """Send issue of Finite News to a subscriber by email using the SendGrid API service.

    NOTE
    Requires a secret in AWS Secret Manager for SENDGRID_API_KEY

    ARGUMENTS
    sender (dict): Metadata about the email source, with keys for "subject" and "email"
    subscriber_email (str): The email address for the destination
    html (str): The issue content
    images (list): Optional, png images to attach to the email

    RETURNS
    None
    """

    today = date.today().strftime("%m.%d.%y").lstrip("0")
    message = Mail(
        from_email=sender["email"],
        to_emails=subscriber_email,
        subject=f"{sender['subject']} for {today}",
        html_content=html,
    )
    attachments = []
    for i, image in enumerate(images):
        attachedFile = Attachment(
            disposition="inline",
            file_name=f"image_{i}.png",
            file_type="image/png",
            file_content=image,
            content_id=f"image_{i}",
        )
        attachments.append(attachedFile)
    message.attachment = attachments
    try:
        sendgrid_key = get_fn_secret("SENDGRID_API_KEY")
        sg = SendGridAPIClient(sendgrid_key)
        response = sg.send(message)
        if response.status_code == 202:
            logging.info(f"{subscriber_email}: Extry extry! Email is away!")
    except Exception as e:
        # Admin issue will get this logging line in its email about failures in prior, non-admin issues.
        logging.critical(
            f"{subscriber_email}: Error in send_email: {str(type(e))}, {str(e)}"
        )


def deliver_issue(issue_config, html, images):
    """Send the content of Finite News to one subscriber by the selected method

    ARGUMENTS
    issue_config (dict): The settings for the issue
    html (str): The content of the email formatted for the email
    images (list): Optional, images to attach to the image

    RETURNS
    None
    """
    logging.info(f"{issue_config['subscriber_email']}: Starting deliver_issue()")
    if issue_config["email_delivery"]:
        email_issue(
            issue_config["sender"], issue_config["subscriber_email"], html, images
        )
    else:
        # Write issue to file
        # Append issue's html to local .txt file that collect the day's issues. Creates file if it doesn't exist.
        with open(f"issues_for_{datetime.now().strftime('%m-%d-%y')}.txt", "a") as f:
            f.write(
                f"""{issue_config['subscriber_email']}\n{datetime.now().strftime('%m-%d-%y %H:%M:%S')}\n{html}\n--------------------------------------------\n"""
            )
        logging.info(
            f"{issue_config['subscriber_email']}: Extry extry! Wrote to text file."
        )


def create_issue(issue_config, log_stream, dev_mode=False):
    """Populate the content of Finite News customized for one subscriber

    ARGUMENTS
    issue_config (dict): The settings for the issue
    log_stream (StringIO object): In-memory file-like object that collects results from logging during the Finite News run
    dev_mode (bool): If we're in dev/debug, output plots to local files too.

    RETURNS
        - The content of the email formatted for the email, HTML as string
        - Optional, list of images to attach to the image
    """

    logging.info(f"{issue_config['subscriber_email']}: Starting create_issue()")

    # Get news
    news_headlines = [
        research_source(source, issue_config["requests_timeout"])
        for source in issue_config["news_sources"]
    ]
    news_headlines = unnest_list(news_headlines)
    # Dedup at source and aggregate level here too, because sometimes we get same headline from multiple sources, like if we pull from multiple sections of the same site
    news_headlines = dedup(news_headlines)
    # Start collecting items we don't want to repeat in the next issue. Do before editing, which dedups using that cache.
    content_to_cache = news_headlines
    headlines = edit_headlines(news_headlines, issue_config)

    # Sports: Get tonight's games for tracked teams
    # Note: These are not added to content_to_cache, so they are not cached in cache_path file or de-duped from the last issue
    nba_headlines = [
        get_todays_nba_game(nba_team, issue_config["requests_timeout"])
        for nba_team in issue_config["sports"].get("nba_teams", [])
    ]
    nba_headlines = edit_sports_headlines(
        nba_headlines, issue_config["sports"].get("nba_teams", [])
    )
    nhl_headlines = [
        get_todays_nhl_game(team_place_name, issue_config["requests_timeout"])
        for team_place_name in issue_config["sports"].get("nhl_teams", [])
    ]
    nhl_headlines = edit_sports_headlines(
        nhl_headlines, issue_config["sports"].get("nhl_teams", [])
    )
    headlines = nba_headlines + nhl_headlines + headlines

    # Get Alerts, a separate kind of headline that get edited more lightly
    alerts = [
        research_source(source, issue_config["requests_timeout"])
        for source in issue_config["alerts_sources"]
    ]
    alerts = unnest_list(alerts)
    # Cache alerts so we don't repeat them in the next issue. Do before editing, which checks that cache.
    content_to_cache += alerts
    # Remove exact repeats, but don't try to remove non-substantive content or smart dedup (MBTA can have multiple, semantically similar alerts)
    alerts = edit_headlines(
        alerts, issue_config, filter_for_substance=False, smart_deduplicate=False
    )

    if issue_config["forecast"]:
        forecast = get_forecast(issue_config["forecast"])
    else:
        forecast = None

    # Get Events section in HTML
    events_html = "".join(
        [
            research_source(source, issue_config["requests_timeout"])
            for source in issue_config["events_sources"]
        ]
    )

    # Get Stock plot images, if requested by subscriber
    stock_plots = []
    if len(issue_config["stocks"]) > 0:
        try:
            for tickers_set in issue_config["stocks"]:
                stock_plots.append(
                    get_stocks_plot(
                        tickers_set, issue_config["stocks_frequency"], dev_mode
                    )
                )
        except Exception as e:
            logging.warning(
                f"{issue_config['subscriber_email']}: Error during create_issue() while getting stock plots: {str(type(e))}, {str(e)}"
            )

    # Other images
    # A. images that we need to attach to the email
    images = stock_plots + get_screenshots(
        [
            source
            for source in issue_config["image_sources"]
            if source["type"] == "screenshot"
        ]
    )

    # B. image_urls that we don't need to attach, the <img> html is sufficient
    image_urls = [
        research_source(source, issue_config["requests_timeout"])
        for source in issue_config["image_sources"]
        if source["type"] == "image_url"
    ]
    image_urls = unnest_list([element for element in image_urls if element])
    content_to_cache += image_urls
    # Don't show the image if it was in the last issue
    image_urls = edit_headlines(
        image_urls,
        issue_config,
        filter_for_substance=False,
        smart_deduplicate=False,
        enforce_trailing_period=False,
    )

    # Cache content, including unedited news headlines, sports headlines, alerts, and image_urls.
    # Do so with originals before removing repeats, cleaning, or applying substance filters.
    # That way, when checking cache for repeats, we compare unedited to unedited (same punctuation etc).
    # Also GPT filtering is nondeterministic. We need to remove repeats before GPT changes the pool.
    # But update the cache them _after_ edit_headlines(), which uses the cache to dedup and, at that point, needs to be the last issue's content, not this issue's.
    if issue_config["editorial"]["cache_issue_content"]:
        cache_issue_content(
            content_to_cache,
            issue_config["bucket_path"],
            issue_config["editorial"]["cache_path"],
        )

    # Pull it all together
    html = format_issue(
        content={
            "headlines": headlines,
            "alerts": alerts,
            "forecast": forecast,
            "events_html": events_html,
            "stock_plots": stock_plots,
            "images": images,
            "image_urls": image_urls,
        },
        issue_config=issue_config,
        log_stream=log_stream,
    )
    logging.info(f"{issue_config['subscriber_email']}: Finished create_issue()")
    return html, images
