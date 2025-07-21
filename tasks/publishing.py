"""📰 Publishing functions to deliver the news"""

from mailjet_rest import Client
from datetime import date, datetime
import logging
import os
import sys
import traceback

from tasks.io import (
    init_logging,
    load_smart_dedup_model,
    load_publication_config,
    load_subscriber_configs,
)
from tasks.editing import dedup, edit_headlines, unnest_list, cache_issue_content
from tasks.layout import format_issue
from tasks.io import get_fn_secret
from tasks.reporting import research_source, get_screenshots
from tasks.sports import (
    get_todays_nba_game,
    edit_sports_headlines,
    get_todays_nhl_game,
    get_nba_scoreboard,
    get_nhl_scoreboard,
)
from tasks.stocks import get_stocks_plot
from tasks.weather import get_forecast


def email_issue(sender, subscriber_email, html, images):
    """Send issue of Finite News to a subscriber by email using the Mailjet API.

    NOTE
    Requires a secret/environment variable for MAILJET_API_KEY and MALIJET_SECRET_KEY. See README.md.

    ARGUMENTS
    sender (dict): Metadata about the email source, with keys for "subject" and "email"
    subscriber_email (str): The email address for the destination
    html (str): The issue content
    images (list): Optional, png images to attach to the email

    RETURNS
    None
    """

    today = date.today().strftime("%m.%d.%y").lstrip("0")
    email_data = {
        "FromEmail": sender["email"],
        "FromName": "Finite News",
        "Subject": f"{sender['subject']} for {today}",
        "Html-part": html,
        "Recipients": [{"Email": subscriber_email}],
    }
    if images:
        email_data["Inline_attachments"] = [
            {
                "Content-type": "image/png",
                # Filname doubles as content id (cid) referenced in HTML
                "Filename": f"image_{i}.png",
                "content": image,
            }
            for i, image in enumerate(images)
        ]
    try:
        mailjet_un = get_fn_secret("MAILJET_API_KEY")
        malijet_pw = get_fn_secret("MAILJET_SECRET_KEY")
        mailjet = Client(auth=(mailjet_un, malijet_pw))
        response = mailjet.send.create(data=email_data)
        if response.status_code == 202:
            logging.info(f"{subscriber_email}: Extry extry! Email is away!")
        else:
            try:
                json = response.json()
            except Exception as e:
                json = f"Could not decode JSON: {e}"

            logging.critical(
                f"{subscriber_email}: Error in send_email: Response code {response.status_code}, reason: {response.reason}. JSON: {json}"
            )
            print(response.status_code, response.reason, json)

    except Exception as e:
        # Admin issue will get this logging line in its email about failures in prior, non-admin issues.
        print(e)
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


def create_issue(issue_config, log_stream, smart_dedup_model=None, dev_mode=False):
    """Populate the content of Finite News customized for one subscriber

    ARGUMENTS
    issue_config (dict): The settings for the issue
    log_stream (StringIO object): In-memory file-like object that collects results from logging during the Finite News run
    smart_dedup_model (SentenceTransformer): Optional, a model to use for smart deduplication of similar headlines
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
    headlines = edit_headlines(
        raw_headlines=news_headlines,
        issue_config=issue_config,
        smart_dedup_model=smart_dedup_model,
    )

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
        raw_headlines=alerts,
        issue_config=issue_config,
        smart_dedup_model=None,  # Override publication_config
        filter_for_substance=False,
    )

    # Get scoreboard
    scoreboard = []
    if not issue_config["sports"].get("hide_nba_scoreboard", False):
        scoreboard += get_nba_scoreboard(
            issue_config["sports"].get("nba_teams", []),
            issue_config["requests_timeout"],
        )
    if not issue_config["sports"].get("hide_nhl_scoreboard", False):
        scoreboard += get_nhl_scoreboard(
            issue_config["sports"].get("nhl_teams", []),
            issue_config["requests_timeout"],
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
    # Reminders:
    #   - We append screenshots after stock_plots due to expectations in format_issue()
    #   - stock_plots are a list of base64 images. screenshots are a dict with keys "image" and "heading"

    screenshots = get_screenshots(
        [
            source
            for source in issue_config["image_sources"]
            if source["type"] == "screenshot"
        ],
        dev_mode,
    )
    screenshot_images = [
        screenshot["image"] for screenshot in screenshots if screenshot
    ]
    screenshot_headings = [
        screenshot["heading"] for screenshot in screenshots if screenshot
    ]
    images = stock_plots + screenshot_images

    # B. image_urls that we don't need to attach, the <img> html is sufficient
    image_urls = [
        research_source(source, issue_config["requests_timeout"])
        for source in issue_config["image_sources"]
        if source["type"] in ["image_url", "static"]
    ]
    image_urls = unnest_list([element for element in image_urls if element])
    content_to_cache += image_urls
    # Don't show the image if it was in the last issue
    image_urls = edit_headlines(
        raw_headlines=image_urls,
        issue_config=issue_config,
        filter_for_substance=False,
        smart_dedup_model=None,  # Override publication_config
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
            issue_config["editorial"]["cache_path"],
        )

    # Pull it all together
    html = format_issue(
        content={
            "alerts": alerts,
            "headlines": headlines,
            "scoreboard": scoreboard,
            "forecast": forecast,
            "events_html": events_html,
            "stock_plots": stock_plots,
            "images": images,
            "screenshot_headings": screenshot_headings,
            "image_urls": image_urls,
        },
        issue_config=issue_config,
        log_stream=log_stream,
    )
    logging.info(f"{issue_config['subscriber_email']}: Finished create_issue()")
    return html, images


def run_finite_news(dev_mode=True, disable_gpt=True, logging_level="warning"):
    """Entry point to create and deliver issues to all subscribers of Finite News.

    ARGUMENTS
    dev_mode (bool): If True we're in development or debug mode, so:
        - don't send emails
        - don't cache new headlines for later dedup
        - output plots to local files
    disable_gpt (bool): If True, don't call the GPT API and incur costs, for example during dev or debug cycles.
    logging_level (level from logging library): The deepest granularity of log messages to track
        - Use "warning" by default
        - Use "info" to get more detailed FN messages for debugging
        - Use "debug" to get lower-level messages from dependencies

    RETURNS
    None
    """
    # Avoids unnecessary disablement of parallelism
    os.environ["TOKENIZERS_PARALLELISM"] = "true"

    if "ipykernel" in sys.modules:
        ## Housekeeping for notebook environments
        # TQDM in notebook mode
        from tqdm import TqdmExperimentalWarning
        import warnings

        warnings.filterwarnings("ignore", category=TqdmExperimentalWarning)
        from tqdm.notebook import tqdm

    else:
        from tqdm import tqdm

    log_stream = init_logging(logging_level, dev_mode)
    publication_config = load_publication_config(
        dev_mode=dev_mode, disable_gpt=disable_gpt
    )
    subscriber_configs = load_subscriber_configs(publication_config)
    smart_dedup_model = load_smart_dedup_model(
        publication_config["editorial"]
        .get(
            "smart_deduper",
            {},
        )
        .get("path_to_model", None)
    )

    for subscriber_config in tqdm(subscriber_configs):
        try:
            html, images = create_issue(
                subscriber_config, log_stream, smart_dedup_model, dev_mode
            )
            deliver_issue(subscriber_config, html, images)
        except Exception as e:
            # During dev or debugging, raise exception and show traceback in notebook.
            if dev_mode:
                raise e
            # In prod mode, save traceback for admin's issue, but continue to try to publish the next issue.
            logging.critical(
                f"{subscriber_config['subscriber_email']}: Issue failed due to unhandled exception. {traceback.format_exc()}"
            )
    if dev_mode:
        print("👍")
    else:
        logging.info("👍")
