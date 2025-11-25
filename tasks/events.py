"""📅 Events: Obtain content on upcoming events"""

from bs4 import BeautifulSoup
import logging
import requests
from datetime import datetime, timedelta

from tasks.selenium import scrape_text_with_selenium


def extract_tag_class(element, soup, config):
    """Helper function to locate an HTML element's content by class and parse into a string.

    ARGUMENT
    element (str): Internal Finite News name of the element
    soup (BeautifulSoup object): The parsed HTML to search
    config (dict): The calendar_config dictionary describing the web calendar and how we'll process it

    RETURNS
    The str of the desired element, if present in the soup
    """

    class_name = f"{element}_class"
    if class_name in config:
        return soup.find(class_=config[class_name]).text.strip()
    return ""


def extract_event_details(event_soup, calendar_config):
    """Parse an event description from HTML to structured data.

    ARGUMENTS
    event_soup (BeautifulSoup object): Parsed HTML for the event
    calendar_config (dict): Description of the website, calendar structure, and configuration

    RETURNS
    Dict description of event with keys required for rendering in issue
    """

    event = {}

    # Extract text descriptions about the event
    for element in ["title", "venue", "dates", "description"]:
        event[element] = extract_tag_class(element, event_soup, calendar_config)

    # Extract thumbnail image
    if "image_html_class" in calendar_config:
        event["image_html"] = event_soup.find(
            class_=calendar_config["image_html_class"]
        )
        if "placeholder_image_src" in calendar_config:
            if calendar_config["placeholder_image_src"] in event["image_html"].get(
                "src", ""
            ):
                event["image_html"] = calendar_config[
                    "placeholder_image_replacement_url"
                ]
    else:
        event["image_html"] = ""

    # Extract link
    if (
        "link_url_class" in calendar_config
        and "link_url_child_key" in "calendar_config"
    ):
        event["link_url"] = event_soup.find(
            class_=calendar_config["link_url_class"]
        ).get(calendar_config["link_url_child_key"], "")
    else:
        event["link_url"] = ""

    return event


def scrape_calendar_page(calendar_config, url_base, page, requests_timeout=None):
    """Pull content from one page of a web calendar.

    ARGUMENTS
    calendar_config (dict): The source configuration for the calendar; keys:
        - "event_item_tag" (str): The HTML tag where each event is stored
        - "event_list_class" (str): The element CSS class for those event tags
        - "use_selenium" (bool): (Optional) whether to use Selenium to fetch the HTML instead of requests
    url_base (str): The url for the calendar, with {PAGE} as a placeholder, but dates populated if placeholders were in the publication_config
    page (int): The page to request
    request_timeout (int):  Number of seconds to wait before giving up on an HTTP request.(Ignored if use_selenium is True. Required if not, because we're using requests to scrape)

    RETURNS
    BeautifulSoup object with parsed HTML for the calendar page
    """

    url = None
    try:
        url = calendar_config["url_base"].replace("{PAGE}", str(page))

        if calendar_config.get("use_selenium", False):
            # Derive a new config dictionary that contains the "url" key as our Selenium scraper expects
            calendar_config_for_selenium = calendar_config.copy()
            calendar_config_for_selenium["url"] = url_base
            html_str = scrape_text_with_selenium(
                source=calendar_config_for_selenium, scrape_all=True
            )
        else:
            if not requests_timeout:
                raise AttributeError(
                    f"scrape_calendar_page: use_selenium is False, so we're using requests, but no value passed for requests_timeout (required). Full source: {calendar_config}"
                )
            response = requests.get(url, timeout=requests_timeout)
            html_str = response.text
        return (
            BeautifulSoup(html_str, "html.parser")
            .find_all(
                calendar_config["event_item_tag"],
                class_=calendar_config["event_list_class"]
            )
        )  # fmt: skip
    except Exception as e:
        logging.warning(f"scrape_calendar_page: {str(type(e))}, {str(e)}. URL: {url}")


def scrape_calendar(calendar_config, requests_timeout):
    """Pull content from a web calendar. Handle multi-page calendars.

    ARGUMENTS
    calendar_config (dict): Description of the website, calendar structure, and configuration
    requests_timeout (int): Number of seconds to wait before giving up on an HTTP request

    RETURNS
    List of event descriptions dicts
    """

    today = datetime.today()
    start_date = today.strftime("%m-%d-%Y")
    end_date = (today + timedelta(days=calendar_config["window"])).strftime("%m-%d-%Y")
    url_base = (
        calendar_config["url_base"]
        .replace("{START_DATE}", start_date)
        .replace("{END_DATE}", end_date)
    )

    calendar_events = []
    page = 1
    while True:
        page_soup = scrape_calendar_page(
            calendar_config,
            url_base,
            page,
            requests_timeout,
        )
        if page_soup:
            page_events = [
                extract_event_details(event_soup, calendar_config)
                for event_soup in page_soup
            ]
            calendar_events.append(page_events)
            page += 1
        else:
            # Flatten the nested list
            return [item for sublist in calendar_events for item in sublist]


def format_event(event):
    """Render one event as a table row

    ARGUMENT
    event (dict): Description of event

    RETURNS
    Str of HTML table row describing that event
    """

    if len(event["title"]) < 2:
        return ""
    return f"""
    <tr>
       <td>
           {event['image_html']}
       </td>
       <td>
           <h4><a href="{event['link_url']}">{event['title']}</a></h4>
           <p><b>{event['venue']}</b></p>
           <p><b><i>{event['dates']}</b></i></p>
           <p>{event['description']}</p>
           <br>
        </td>
    </tr>
    """


def get_calendar_events(calendar_config, requests_timeout):
    """Pull all events from a website calendar, formatting results as HTML table.

    ARGUMENTS
    calendar_config (dict): Description of the website, calendar structure, and configuration
    requests_timeout (int): Number of seconds to wait before giving up on an HTTP request

    RETURNS
    List of events formatted as an HTML table
    """

    calendar_events = scrape_calendar(calendar_config, requests_timeout)

    # Limit total events if requested
    if calendar_config.get("max_events"):
        calendar_events = calendar_events[
            : min(calendar_config["max_events"], len(calendar_events))
        ]
    return f"""
                <table>
                    {''.join([format_event(event) for event in calendar_events])}
                </table>
            """.replace("\n", "")
