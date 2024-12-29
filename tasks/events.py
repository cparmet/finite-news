"""📅 Events: Obtain content on upcoming events"""

from bs4 import BeautifulSoup
import logging
import requests
from datetime import date, datetime, timedelta


def extract_tag_class(element, soup, config):
    """Helper function to locate an HTML element's content by class and parse into a string.

    ARGUMENT
    element (str): Internal Finite News name of the element
    soup (BeautifulSoup object): The parsed HTML to search
    config (dict): The calendar_config dictionary describing the web calendar and how we'll process it 

    RETURNS
    element_str (str): The text of the desired element, if present in the soup
    """
    
    class_name = f"{element}_class"
    if class_name in config:
        return (
            soup
            .find(class_=config[class_name])
            .text
            .strip()
        )
    return ""


def extract_event_details(event_soup, calendar_config):
    """Parse an event description from HTML to structured data.
    
    ARGUMENTS
    event_soup (BeautifulSoup object): Parsed HTML for the event
    calendar_config (dict): Description of the website, calendar structure, and configuration

    RETURNS
    event (dict): Description of event with keys required for rendering in issue
    """
    
    event = {}
    
    # Extract text descriptions about the event
    for element in ["title", "venue", "dates", "description"]:
        event[element] = extract_tag_class(element, event_soup, calendar_config)
    
    # Extract thumbnail image
    if "image_html_class" in calendar_config:
        event["image_html"] = event_soup.find(class_=calendar_config["image_html_class"])
        if "placeholder_image_src" in calendar_config:
            if calendar_config["placeholder_image_src"] in event["image_html"].get("src", ""):
                event["image_html"] = calendar_config["placeholder_image_replacement_url"]
    else:
        event["image_html"] = ""

    # Extract link   
    if "link_url_class" in calendar_config and "link_url_child_key" in "calendar_config":
        event["link_url"] = (
            event_soup
            .find(class_=calendar_config["link_url_class"])
            .get(calendar_config["link_url_child_key"], "")
        )
    else:
        event["link_url"] = ""
        
    return event


def scrape_calendar_page(url_base, page, event_item_tag, event_list_class, requests_timeout):
    """Pull content from one page of a web calendar.
    
    ARGUMENTS
    url_base (str): The url for the calendar, with {PAGE} as a placeholder
    page (int): The page to request
    event_item_tag (str): The HTML tag where each event is stored
    event_list_class (str): The element CSS class for those event tags


    RETURNS
    page_soup (BeautifulSoup object): Parsed HTML for the calendar page
    """

    try:
        url = url_base.replace("{PAGE}", str(page))
        response = requests.get(url, timeout=requests_timeout)
        return (
            BeautifulSoup(response.text, "html.parser")
            .find_all(event_item_tag, class_=event_list_class)
        )
    except Exception as e:
        logging.warning(f"scrape_calendar_page: {str(type(e))}, {str(e)}. {url}")


def scrape_calendar(calendar_config, requests_timeout):
    """Pull content from a web calendar. Handle multi-page calendars.
    
    ARGUMENTS
    calendar_config (dict): Description of the website, calendar structure, and configuration
    requests_timeout (int): Number of seconds to wait before giving up on an HTTP request

    RETURNS
    calendar_events (lsit of dict): List of event descriptions
    """
    
    today = datetime.today() 
    start_date = today.strftime('%m-%d-%Y')
    end_date = (
        (today + timedelta(days=calendar_config["window"]))
        .strftime('%m-%d-%Y')
    )
    url_base = (
        calendar_config["url_base"]
        .replace("{START_DATE}", start_date)
        .replace("{END_DATE}", end_date)
    )

    exhausted = False
    calendar_events = []
    page = 1
    while True:
        page_soup = scrape_calendar_page(
            url_base,
            page,
            calendar_config["event_item_tag"],
            calendar_config["event_list_class"],
            requests_timeout
        )
        if page_soup:
            page_events = [extract_event_details(event_soup, calendar_config) for event_soup in page_soup]
            calendar_events.append(page_events)
            page += 1
        else:
            return [item for sublist in calendar_events for item in sublist] # FLatten nested list

        
def format_event(event):
    """Render one event as a table row
    
    ARGUMENT
    event (dict): Description of event
    
    RETURNS
    event_row (str): HTML table row describing that event
    """
    
    if len(event['title'])<2:
        return ''
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
    calendar_html (str): List of events formatted as an HTML table
    """
    
    calendar_events = scrape_calendar(calendar_config, requests_timeout)

    # Limit total events if requested
    if calendar_config.get("max_events"):
        calendar_events = calendar_events[:min(calendar_config["max_events"], len(calendar_events))]
    return f"""
                <table>
                    {''.join([format_event(event) for event in calendar_events])}
                </table>
            """.replace("\n","")