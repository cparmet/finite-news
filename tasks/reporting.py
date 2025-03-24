"""🕵🏻‍♀️ Reporting functions to research the content for an issue"""

from bs4 import BeautifulSoup
import logging
from datetime import date, timedelta
import feedparser
import pandas as pd
import platform
import requests
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from time import sleep
import base64
from io import BytesIO
from PIL import Image

from tasks.editing import postprocess_scraped_content
from tasks.events import get_calendar_events
from tasks.io import get_fn_secret, parse_frequency_config

feedparser.USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome 75.0.3770.142 Safari/537.36"

HEADERS = {
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/75.0.3770.142 Safari/537.36"
}


def create_calendar_sitemap_url(base_url, path_format, substract_one_day):
    """Generate a URL for sites that organize content chronologically in site-map.

    Useful for sites where there's no good way to ensure a page with headlines ordered by recency,
    where normal scraping would lead to old headlines reemerging"

    ARGUMENTS
    base_url (str): The core part of the URL that we'll add onto, e.g. "http://www.website.com/sitemap/"
    path_format (str): The format for the path pointing to the date we want to hit. e.g. "full_year/month_lower/day"
        Supported elements (in any order): full_year (2024), month_lower (august), month_title_case (August), day (5)
    subtract_one_day (bool): Whether to traverse to yesterday's date instead of today

    RETURNS
    string with fully specified url to the date desired, e.g. "http://www.website.com/sitemap/2024/august/5"
    """
    target_date = (
        date.today() - timedelta(days=1) if substract_one_day else date.today()
    )
    return (
        base_url
        + path_format
        # Replace supported
        .replace("full_year", str(target_date.year))
        .replace("month_lower", target_date.strftime("%B").lower())
        # Initial-capitalized
        .replace("month_title_case", target_date.strftime("%B").title())
        .replace("day", str(target_date.day))
    )


def scrape_source(source, requests_timeout, retry=True):
    """Fetch and parse the HTML tags from a web location.

    ARGUMENTS
    source (dict): Description of the website to scrape
    requests_timeout (int): Number of seconds to wait before giving up on an HTTP request
    retry (bool): Whether to run the request again if no items were scraped

    RETURNS
    items (list of str): Text retrieved

    """
    try:
        if source.get("use_selenium", False):
            return scrape_text_with_selenium(source)

        if "calendar_sitemap_format" in source:
            url = create_calendar_sitemap_url(
                source["url"],
                source.get("calendar_sitemap_format"),
                source.get("calendar_sitemap_subtract_one_day", False),
            )
        else:
            url = source["url"]

        if source.get("specify_request_headers", False):
            headers = HEADERS
        else:
            headers = None

        try:
            response = requests.get(url, headers=headers, timeout=requests_timeout)
        except requests.exceptions.SSLError as e:
            logging.warning(
                f"SSL error on {source['name']}, {url}. {str(type(e))}, {str(e)}"
            )
            return []
        except requests.exceptions.Timeout as e:
            logging.warning(
                f"Request timed out after {requests_timeout} seconds: {url}. More details: {source['name']}, {str(type(e))}, {str(e)}"
            )
            return []
        except Exception as e:
            logging.warning(
                f"Requests error on {source['name']}, {url}. {str(type(e))}, {str(e)}"
            )
            return []

        soup = BeautifulSoup(
            response.text, features=source.get("parser", "html.parser")
        )

        if "select_query" in source:  # Scrape the content using a BeautifulSoup query
            items = soup.select(source["select_query"])
        elif "tag_class" in source:
            # Scrape the content by finding tags with a specific class
            items = soup.find_all(source["tag"], {"class": source["tag_class"]})
        elif "multitag_group" in source:
            # Scrape the content by finding repeating groups of tags and combine the text of each set of tags.
            groups = soup.find_all(source["multitag_group"])
            separator = source.get("multitag_separator", " ")
            for i, tag in enumerate(source["multitag_tags"]):
                # Iteratively append text from multiple consecutive tags into each string
                if i == 0:
                    items = [f"{group.find(tag).text}" for group in groups]
                else:
                    try:
                        items = [
                            f"{item_text}{separator}{group.find(tag).text}"
                            for item_text, group in zip(items, groups)
                        ]
                    except Exception as e:
                        logging.warning(
                            f"multitag error on {source['name']} while appending tag {tag}. Maybe tag not present for all items? {str(type(e))}, {str(e)}"
                        )
        elif source.get("img_tag", False):
            response = requests.get(
                source["url"],
                headers=HEADERS,  # Specify request headers by default
                timeout=requests_timeout,
            )
            soup = BeautifulSoup(
                response.text, features=source.get("parser", "html.parser")
            )
            img_element = soup.find_all("img")[source.get("img_tag_number", 0)]

            src = img_element.attrs.get("src", None)
            if src:
                items = [
                    f"""
                            <h4>{source.get("header","")}</h4>
                            <img src="{src}">"""
                ]
            else:
                items = []

        else:
            items = soup.find_all(source["tag"])

        if "tag_next" in source:
            # Scrape a specified tag that appears _after_ "tag"
            items = items[0].findNext(source["tag_next"])

        if "detail_page_root" in source:
            # Scrape a child page. We have to go depper!
            detail_link = items[0].attrs["href"]
            header = items[0].get_text().strip()
            # Request a detail page
            response = requests.get(
                source["detail_page_root"] + detail_link,
                headers=headers,
                timeout=requests_timeout,
            )
            soup = BeautifulSoup(
                response.text, features=source.get("parser", "html.parser")
            )

            # Get the detail image
            img_element = soup.find_all("img")[source["detail_img_number"] - 1]
            alt = img_element.attrs["alt"]
            src = img_element.attrs["src"]
            # TODO: Make the following reuse code above
            if "detail_text_tag_class" in source:
                text = (
                    soup.find_all(
                        source["detail_text_tag"],
                        {"class": source["detail_text_tag_class"]},
                    )[0]
                    .get_text()
                    .strip()
                )
            elif "detail_text_tag" in source:
                text = soup.find_all(source["detail_text_tag"])[0].get_text().strip()
            else:
                text = ""

            if source.get("add_http_img", False):
                src = f"http:{src}"
            items = [f"""<h4>{header}</h4><img alt="{alt}" src="{src}"><p>{text}</p>"""]

        elif "split_char" in source:
            items = [
                item for item in items.get_text().split(source["split_char"]) if item
            ]
        elif "multitag_group" not in source and not source.get("img_tag", False):
            # multitag scraping at this stage already has text for each item. The other approaches need us to extract the text.
            items = [item.get_text() for item in items]

        # If at first you don't succeed...try just one more time
        # Some sources are finnicky and work better with two swings
        # But don't retry if this is a source we expect 0 results often
        if (
            not items
            and retry
            and not source.get("exclude_from_0_results_warning", False)
        ):
            logging.info(
                f"No items scraped. Waiting 3 seconds and retrying.... {source['name']}"
            )
            sleep(3)
            scrape_source(source, requests_timeout, retry=False)

        return items
    except Exception as e:
        logging.warning(
            f"Source failed on {source['name']}. {str(type(e))}, {str(e)}. Source: {source}"
        )
        return []


def load_selenium_driver():
    ## Configure Selenium
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")

    # Find the correct location of the chromedriver, depending if we're in local dev mode or deployed to GCP
    os_name = platform.system()

    if os_name == "Darwin":
        # For local Mac development
        # To download appropriate chromedriver, see https://googlechromelabs.github.io/chrome-for-testing/
        # TODO: This now could just be a system install too
        service = webdriver.ChromeService(
            executable_path="assets/chromedriver_mac_arm64"
        )
    elif os_name == "Linux":
        # For Google Cloud Run (Docker container), use the system-installed chromedriver
        # To change the chromedriver for a different image, update Dockerfile
        service = webdriver.ChromeService(executable_path="/usr/local/bin/chromedriver")
    else:
        raise AttributeError(
            f"Unexpected platform in get_screenshots. No chromedriver handled for {os_name}"
        )
    try:
        driver = webdriver.Chrome(service=service, options=options)
        driver.maximize_window()
        return driver
    except Exception as e:
        logging.warning(
            f"Selenium could not initialize Chrome driver: {str(type(e))}, {str(e)}. os_name = {os_name}"
        )
        return None


def scrape_text_with_selenium(source, driver=None):
    """Extract text from HTML using Selenium and headless Chrome

    Args:
        source (dict): A dictionary describing what to scrape
        drivers (webdriver.Chrome): A Selenium Chrome driver, if caller has already loaded one.
            - If None, we'll load a driver just for the session

    """
    try:
        # Validate source config
        criteria = [
            criterion
            for criterion in source
            if criterion in ["tag", "tag_class", "tag_id", "tag_xpath", "tag_css"]
        ]
        if len(criteria) > 1:
            logging.warning(
                f"scrape_text_with_selenium() received multiple scraping criteria. Only one will be used. {source}"
            )

        if not driver:
            driver = load_selenium_driver()
            quit_after_scrape = True
        else:
            quit_after_scrape = False

        driver.get(source["url"])
        # These are one at a time right now, not composable like with our Beautiful Soup implementation
        if "tag" in source:
            criteria = By.NAME
            value = source["tag_name"]
        elif "tag_class" in source:
            criteria = By.CLASS_NAME
            value = source["tag_class"]
        elif "tag_id" in source:
            criteria = By.ID
            value = source["tag_id"]
        elif "tag_xpath" in source:
            criteria = By.XPATH
            value = source["tag_xpath"]
        elif "tag_css" in source:
            criteria = By.CSS_SELECTOR
            value = source["tag_css"]
        else:
            logging.warning(
                f"scrape_text_with_selenium() was given unhandled criteria from {source}. No results scraped."
            )
            if quit_after_scrape:
                driver.quit()
            return []

        elements = [element.text for element in driver.find_elements(criteria, value)]

        if "item_number" in source:
            # Converts 1-based index to 0-based Python index
            elements = [elements[source["item_number"] - 1]]

        if quit_after_scrape:
            driver.quit()
        return elements

    except Exception as e:
        logging.warning(
            f"Error [a] in scrape_text_with_selenium() on {source['url']}: {str(type(e))}, {str(e)}. source: {source}"
        )
        if quit_after_scrape:
            try:
                driver.quit()
            except Exception as e:
                logging.warning(
                    f"Error [b] in scrape_text_with_selenium() on {source['url']}: {str(type(e))}, {str(e)}. source: {source}"
                )
                return []
        return []


def research_source(source, requests_timeout):
    """Get a source's content, whether from API or scraping, and format into desired structure.

    NOTE
    See also clean_headline() for post-processing that's done on the level of an individual headline.

    ARGUMENTS
    source (dict): Description of the API to call or website to scrape
    requests_timeout (int): Number of seconds to wait before giving up on an HTTP request

    RETURNS
        - List of items fround from source
        or
        - Formatted block of html as a str

    """
    try:
        # Get specialized content
        if source["type"] == "events_calendar":
            return get_calendar_events(source, requests_timeout)
        if source["type"] == "static":
            if parse_frequency_config(source.get("frequency", None)):
                static_message = source.get("static_message", None)
                if static_message:
                    # Throw in the date if requested, like in an img's alt text.
                    # Because with content like an img that always has the same src url,
                    # e.g. NOAA Aurora forecasts, the <img> content is the same every day.
                    # When we dedup today's content by comparing to the cached version of yesterday,
                    # the <img> content would get dropped from today's issue.
                    # So, vary the alt text each day.
                    # publication_config.yml can have {{DATE}} in the "static_message" key
                    static_message = static_message.replace(
                        "{{DATE}}", date.today().strftime("%m/%d/%Y")
                    )
                return [static_message]
            else:
                return []
        if source["type"] == "mbta_alerts":
            if (
                not source["route"]
                or not source["stations"]
                or not source["direction_id"]
            ):
                logging.warning(
                    f"mbta_alert not checked. Expected route, stations, and direction_id. Found: {source}"
                )
                return []
            return get_mbta_alerts(
                source["route"],
                source["stations"],
                source["direction_id"],
                requests_timeout,
            )
        # Get general content
        if source["method"] == "api":
            response = requests.get(
                source["url"] + get_fn_secret(source["api_key_name"]),
                timeout=requests_timeout,
            )
            items = [
                item[source["headline_field"]] for item in response.json()["results"]
            ]
        elif source["method"] == "scrape":
            items = scrape_source(source, requests_timeout)
        elif source["method"] == "rss_images":
            if "get_img_tag_under_this_key" in source:
                html_blocks = [
                    entry[source["get_img_tag_under_this_key"]]
                    for entry in feedparser.parse(source["url"]).entries
                ]
                # Extract the first <img> tag in each html_block
                items = [
                    f"""
                        <h4>{source.get("header","")}</h4>
                        {BeautifulSoup(html_block, "html.parser").find("img")}"""
                    for html_block in html_blocks
                ]
                # Drop items that have no <img> component, only <h4>
                items = [item for item in items if "<img" in item]
            # Extract media_thumbnail and summary keys
            elif source.get("media_thumbnail_and_summary", False):
                entries = feedparser.parse(source["url"]).entries
                items = [
                    f"""
                        <h4>{source.get("header","")}</h4>
                        <img src="{entry["media_thumbnail"][0].get("url", None)}">
                        <p>{entry.get("summary", None)}</p>
                        <p><i>{entry.get("author", None)}</i></p>
                        """
                    for entry in entries
                    if "media_thumbnail" in entry
                ]
            # Extract the media_content key
            else:
                urls = [
                    entry["media_content"][0].get("url", None)
                    for entry in feedparser.parse(source["url"]).entries
                    if "media_content" in entry
                ]
                items = [
                    f"""
                        <h4>{source.get("header","")}</h4>
                        <img src="{url}">"""
                    for url in urls
                ]

            # Replace http: with https: if requested
            # Some http: img urls from RSS feeds don't render in all situations
            items = (
                [item.replace("http:", "https:") for item in items]
                if source.get("enforce_https_img_url", False)
                else items
            )

        elif source["method"] == "atom":
            newest_entry = feedparser.parse(source["url"]).entries[0]
            if "header_path" in source:
                header = newest_entry
                for node in source["header_path"]:
                    header = header[node]
                header = f"<h4>{source.get('header_preface', '')}{header}</h4>"
            else:
                header = ""
            if "image_path" in source:
                img = newest_entry
                for node in source["image_path"]:
                    img = img[node]
            else:
                img = ""
            if "body_path" in source:
                body = newest_entry
                for node in source["body_path"]:
                    body = body[node]
                body = f"<p>{body}</p>"
            else:
                body = ""
            items = [f"""{header}{img}{body}"""]

        # Lightly postprocess results
        items = postprocess_scraped_content(items, source)

        # Log count
        if len(items) == 0 and not source.get("exclude_from_0_results_warning", False):
            # Escalate to admin if no results were returned, and that was unexpected. Source's scraper/API may be broken.
            logging.warning(f"{source['name']}: retrieved 0 items")
        else:
            logging.info(f"{source['name']}: retrieved {len(items)} items")

        # Add prefaces and return
        if source["type"] in ["headlines", "image_url"]:
            # Add preface, if requested
            return [f"{source.get('preface','')}{item}" for item in items]
        elif source["type"] == "alert_new":
            # Wrap the alert in a URL. Add preface, if requested (add separately from regular 'preface', to isolate item)
            return [
                f"""{source.get('alert_preface', '')} <a href="{source['url']}" target="_blank">{item}</a>"""
                for item in items
            ]
        else:
            logging.warning(f"Unknown type of source {source['type']}: {str(source)}")
            return []
    except Exception as e:
        logging.warning(f"Error getting content from source {source['name']}: {str(e)}")
        return []


def get_attributions(
    general_sources, sports_tracked, weather_source, stocks_used, car_talk_used
):
    """Compile the names of all sources used in the issue, to give credit.

    ARGUMENTS
    general_sources (list of dict): A list of sources we tried to get news, alerts, etc from
    sports_tracked (dict): Sources we tried to get sports from
    weather_source (str): The forecast "source" attribute from subsciber's config, or None
    stocks_used (bool): True if we included stock data
    car_talk_used (bool): True if subscriber includes Car Talk credits

    RETURNS
    List of str names of the sources
    """
    # De-dup and sort
    attributions = list(set([source["name"] for source in general_sources]))
    if "nba_teams" in sports_tracked:
        attributions += ["NBA API"]
    if "nhl_teams" in sports_tracked:
        attributions += ["NHL API"]
    if weather_source == "nws":
        attributions += ["National Weather Service API"]
    if weather_source == "env_canada":
        attributions += ["Environment Canada Weather API"]
    if stocks_used:
        attributions += ["Yahoo Finance API"]
    if car_talk_used:
        attributions += ["Car Talk credits"]
    return sorted(attributions)


def get_mbta_alerts(route, station_ids, direction_id, requests_timeout):
    """Use the MBTA API to get alerts for a station.

    ARGUMENTS
    route (str): The mbta id of the route. Browse at https://api-v3.mbta.com/routes
    station_ids (list of str): The mbta ids of the station, either parent station ID from https://api-v3.mbta.com/stops, or get the end of the URL like https://www.mbta.com/stops/place-sstat
    direction_id (int): 0 for outbound, 1 for inbound
    requests_timeout (int): Number of seconds to wait before giving up on an HTTP request

    RETURNS
    List of str alerts for this station

    """
    if not route or not station_ids:
        return []
    url = f"https://api-v3.mbta.com/alerts?filter[route]={route}&filter[stop]={','.join(station_ids)}&filter[direction_id]={direction_id}"
    response = requests.get(url, timeout=requests_timeout)
    return [
        f"🚂 MBTA ruh-roh: {alert['attributes']['header'].strip()}"
        for alert in response.json()["data"]
    ]


def get_car_talk_credit():
    """Pull a random Car Talk credit from CSV on the Finite News bucket.

    NOTE
    - These credits are fake staff credits that were used at the end of each episode of
    the National Public Radio automotive advice radio show, Car Talk
    - They came from downloading https://www.cartalk.com/content/staff-credits.

    RETURNS
    A string credit to a fake staff member to thank for creation of this issue of Finite News :D
    """
    try:
        path_to_car_talk_csv = (
            f"gs://{get_fn_secret('FN_BUCKET_NAME')}/car_talk_credits.csv"
        )

        credit = (
            pd.read_csv(path_to_car_talk_csv, header=None)
            .dropna()  # Remove invalid credits
            .sample(1)
            .values
        )
        return ": ".join(credit.flatten().tolist())
    except Exception as e:
        logging.warning(
            f"""
            Exception in get_car_talk_credit: {credit}

            Exception: {e}
            """
        )
        return []


def get_screenshots(sources, dev_mode=False):
    """Scrape images that require taking a screenshot with Selenium.

    Returns: A list of dicts with {image: image as base64, heading: any header text to place above the image}
    """
    screenshots = []
    driver = None
    try:
        driver = load_selenium_driver()

        ## Get the screenshot for each source
        for i, source in enumerate(sources):
            ## Get the screenshot
            driver.get(source["url"])
            elements = driver.find_elements(
                By.CLASS_NAME, source["image_element_class"]
            )
            # For some dynamically generated images, scraping them too quickly leads to incompelte screenshots
            sleep(source.get("delay_secs_for_loading", 5))
            chart_element = elements[source["image_element_number"]]
            screenshot_b64 = chart_element.screenshot_as_base64
            screenshots.append(
                {"image": screenshot_b64, "heading": source.get("header", None)}
            )
            if dev_mode:
                ## Save locally for debug
                # Convert base64 string to image
                img = Image.open(BytesIO(base64.b64decode(screenshot_b64)))
                # Save as JPG
                img.save(f"screenshots_{i}.jpg", "JPEG")

    except Exception as e:
        print(e)
        logging.warning(
            f"Error in get_screenshots() on {source['url']}: {str(type(e))}, {str(e)}"
        )
        return []

    if driver:
        driver.quit()

    return screenshots
