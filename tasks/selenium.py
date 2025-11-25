import logging
import platform
from time import sleep

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options


def load_selenium_driver():
    ## Configure Selenium
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")

    # Find the correct location of the chromedriver, depending if we're in local dev mode or deployed to GCP
    os_name = platform.system()

    if os_name == "Darwin":
        # For local development on Mac, we use local chromedriver, which expects Chrome executable is also installed
        # To download appropriate chromedriver, see https://googlechromelabs.github.io/chrome-for-testing/
        # TODO: This now could just be a system install too instead of assets/
        service = webdriver.ChromeService(
            executable_path="assets/chromedriver_mac_arm64"
        )
    elif os_name == "Linux":
        # For GCP deployment, we use Chromium instead of Chrome
        # and use the paths from the Docker install of Chromium and chromium-driver from Ubuntu repos
        options.binary_location = "/usr/bin/chromium"
        service = webdriver.ChromeService(executable_path="/usr/bin/chromedriver")
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


def scrape_text_with_selenium(source, scrape_all=False, driver=None):
    """Extract text from HTML using Selenium and headless Chrome

    Args:
        source (dict): A dictionary describing what to scrape
        scape_all (bool): Return all HTML, not filtered to specific elements
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

        # Return the entire HTML
        if scrape_all:
            # Wait for sites that are rendered with JavaScript
            sleep(source.get("delay_secs_for_js_render", 0))

            html_str = driver.page_source

            # Wait for elements that exist but are gradually loaded like dynamic images
            sleep(source.get("delay_secs_for_loading", 0))

            return html_str

        # Find the requested element
        # You can only use one of these criteria
        if "tag" in source:
            criteria = By.TAG_NAME
            value = source["tag"]
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

        # Wait for sites that are rendered with JavaScript
        sleep(source.get("delay_secs_for_js_render", 0))

        elements = [element.text for element in driver.find_elements(criteria, value)]

        # Wait for elements that exist but are gradually loaded like dynamic images
        sleep(source.get("delay_secs_for_loading", 0))

        # Select only the single element the user wants, if requested
        if "item_number" in source:
            if len(elements) >= source["item_number"]:
                # Converts 1-based index to 0-based Python index
                elements = [elements[source["item_number"] - 1]]
            else:
                elements = []

        if quit_after_scrape:
            driver.quit()
        return elements

    except Exception as e:
        logging.warning(
            f"Error in scrape_text_with_selenium() on {source['url']}: {str(type(e))}, {str(e)}. source: {source}"
        )
        if quit_after_scrape:
            try:
                driver.quit()
            except Exception as e:
                logging.warning(
                    f"Error while trying to quit driver in scrape_text_with_selenium() on {source['url']}: {str(type(e))}, {str(e)}. source: {source}"
                )
                return []
        return []
