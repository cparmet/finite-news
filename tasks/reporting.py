"""🕵🏻‍♀️ Reporting functions to research the content for an issue"""

from bs4 import BeautifulSoup
import logging
from datetime import date, timedelta
import feedparser
import pandas as pd
import requests
from time import sleep

from tasks.events import get_calendar_events
from tasks.io import get_fn_secret, parse_frequency_config


def dedup(li):
    """De-duplicate a list while preserving the order of elements, unlike list(set()).

    ARGUMENTS
    li (list): A list of items

    RETURNS
    The list in its original order, but without dups

    """
    seen = set()
    return [x for x in li if not (x in seen or seen.add(x))]


def heal_inner_n(s):
    """Replace one or more inner \n with a colon.

    NOTES
    Assumes \n have been removed from ends

    ARGUMENTS
    s (str): A string with or without one or more \n in the middle

    RETURNS
    string with any \n in the middle replaced with a ": "
    """

    if "\n" in s:
        return s.split("\n")[0] + ": " + s.split("\n")[-1]
    return s


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
        if "calendar_sitemap_format" in source:
            url = create_calendar_sitemap_url(
                source["url"],
                source.get("calendar_sitemap_format"),
                source.get("calendar_sitemap_subtract_one_day", False),
            )
        else:
            url = source["url"]

        if source.get("specify_request_headers", False):
            headers = {
                "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/75.0.3770.142 Safari/537.36"
            }
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
        elif "multitag_group" not in source:
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

        # Apply certain text cleaning that depends on source config
        # TODO: Move these to editing; keep items associated with their source config longer
        # Also because then user can apply these configs to API sources, not just scrapes

        # Check if certain phrases are present/absent
        if "must_contain" in source:
            # When it's a list, it's an OR
            if isinstance(source["must_contain"], list):
                items = [
                    h
                    for h in items
                    if sum(
                        [
                            must_contain.lower() in h.lower()
                            for must_contain in source["must_contain"]
                        ]
                    )
                    > 0
                ]
            else:
                items = [
                    h for h in items if source["must_contain"].lower() in h.lower()
                ]
        if "cant_contain" in source:
            if isinstance(source["cant_contain"], list):
                cant_contains = source["cant_contain"]
            else:
                cant_contains = [source["cant_contain"]]
            for cant_contain in cant_contains:
                items = [h for h in items if cant_contain.lower() not in h.lower()]

        # Clean text
        if "remove_text" in source:
            items = [h.replace(source["remove_text"], "") for h in items]

        # Remove \n and \t from ends of strings. Needed before heal_inner_n
        precleaning = True
        while precleaning:
            original_len = sum([len(h) for h in items])
            items = [h.strip("\r").strip("\n").strip("\t") for h in items]
            precleaning = original_len != sum([len(h) for h in items])

        # Clean strings with a "\n" in the middle
        if "heal_inner_n" in source:
            items = [heal_inner_n(item) for item in items]

        # Ensure each string is long enough.
        if "min_words" in source:
            # simple way to count words
            items = [
                item
                for item in items
                if len(item.strip().split(" ")) >= source["min_words"]
            ]

        return dedup(items)
    except Exception as e:
        logging.warning(
            f"Source failed on {source['name']}. {str(type(e))}, {str(e)}. Source: {source}"
        )
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
        if source["type"] == "reminder":
            if parse_frequency_config(source.get("frequency", None)):
                return [source.get("reminder_message", None)]
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
        if items:
            items = [item.replace("\n", "").strip() for item in items if item]
            # The attribute can have either of two names
            max_items = source.get("max_items", source.get("max_headlines", None))
            items = items[0:max_items]
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


def get_car_talk_credit(bucket_path):
    """Pull a random Car Talk credit from a CSV on S3.

    NOTE
    - These credits are fake staff credits that were used at the end of each episode of
    the National Public Radio automotive advice radio show, Car Talk
    - They came from downloading https://www.cartalk.com/content/staff-credits.

    ARGUMENTS
    bucket_path (str): The location of the S3 bucket where required files are stored.

    RETURNS
    A string credit to a fake staff member to thank for creation of this issue of Finite News :D
    """
    try:
        credit = (
            pd.read_csv(bucket_path + "car_talk_credits.csv", header=None)
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


def get_screenshots(sources):
    """Not currently working on SM. Disabled."""
    return []


#     options = Options()
#     options.add_argument('headless')
#     s=Service(ChromeDriverManager().install())
#     driver = webdriver.Chrome(service=s, options=options)
#     driver.maximize_window()

#     screenshots = []
#     for source in sources:
#         url = source["url"]
#         driver.get(url)
#         try:
#             elements = driver.find_elements(By.CLASS_NAME, source["element_class"])
#             if source.get("automate_gradually", False):
#             # TODO: Temporary workaround for Birdcast. There's surely a better way
#                 b64_screenshots = [element.screenshot_as_base64 for element in elements]
#                 screenshot_b64 = b64_screenshots[source["element_number"]]
#             else:
#                 # The simpler way that should work for nondynamically loaded images
#                 chart_element = elements[source["element_number"]]
#                 screenshot_b64 = chart_element.screenshot_as_base64
#         except Exception as e:
#             logging.warning(f"Selenium error on {source['url']}: {str(type(e))}, {str(e)}")
#         screenshots.append(screenshot_b64)
#         driver.quit()
#     return screenshots
