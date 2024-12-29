"""📦 I/O functions to import resources and interact with the cache"""

import calendar
from copy import deepcopy
from datetime import date
from io import StringIO
import json
import logging
import yaml


def init_logging(logging_level, dev_mode):
    """Initialize logging to either 
        * (default) in-memory object (for optional delivery in admin's issue of Finite News) or
        * (if dev_mode=True) a local log file
    
    NOTE
    Reminder: This function doesn't reset an active log. Must restart the kernel in SageMaker.
    
    ARGUMENTS
    logging_level (str): The granularity of logging messages, 'warning', 'info' or 'debug'. If dev_mode=True, forced to 'debug'
    dev_mode (bool): If False, we're in prod mode and logs will go to log_stream. If True, will send logs to local file
    
    RETURNS
    log_stream (StringIO object): If dev_mode=False, returns in-memory file-like object that collects results from logging during the Finite News run
    """
    
    if logging_level=='warning':
        level = logging.WARNING
    elif logging_level=='info':
        level = logging.INFO
    elif logging_level=='debug':
        level = logging.DEBUG

    if dev_mode:
        # Local file 
        logging.basicConfig(
            filename='app.log',
            level=level,
            format='%(asctime)s - %(levelname)s - %(message)s'
        )
        return None
    else:
        # Create in-memory file-like object
        log_stream = StringIO() 
        logging.basicConfig(stream=log_stream, level=level)
        return log_stream


def get_fn_secret(secret_key, secret_name="fn_secrets", region_name="us-east-1"):
    """Retrieve a secret from AWS Secrets Manager.
    
    ARGUMENTS
    secret_key (string): the specific secret to retrieve, such as BUCKET_PATH or OPENAI_API_KEY
    secret_name (string): the group where the Finite News secrets are stored in AWS Secrets Manager
    region_name (string): the region where your AWS Secrets Manager secret_name lives. See the sample code provided by Secrets Manager after you create the secret

    RETURNS
    secret_value (string): the secret!
    """

    # Create a Secrets Manager client
    session = boto3.session.Session()
    client = session.client(
        service_name='secretsmanager',
        region_name=region_name
    )

    try:
        get_secret_value_response = client.get_secret_value(
            SecretId=secret_name
        )
    except ClientError as e: # Stop the presses, we can't get our secret.
        raise e

    # Decrypt secret using the associated KMS key.
    try:
        return json.loads(get_secret_value_response["SecretString"])[secret_key]
    except KeyError as e:
        raise KeyError(f"Secret key {str(e)} not found. Is it stored in AWS Secrets Manager? Have you given permissions for your SageMaker user to access the secret?") # No sense in logging the exception since we won't be sending any emails (where we store logs)
        

def load_s3(bucket_path, file_path, required=True):
    """Loads a file from S3 into Python variable
    
    ARGUMENTS
    bucket_path (str): The location of the S3 bucket where required files are stored.
    file_path (str): The name or path of the file
    required (bool): Should we error out if we can't load it?
    
    RETURNS
    variable
    """
    file_format = file_path.split(".")[-1]
    try:
        with fs.open(bucket_path + file_path, "r") as f:
            if file_format=="yml":
                variable = yaml.load(f, Loader=yaml.Loader)
            elif file_format=="htm" or file_format=="html":
                variable = f.read()
            elif file_format=="txt":
                variable = f.readlines()
            else:
                logging.warning(f"Unsupported file type in load_s3: {file_path}")
                return None
        logging.info(f"Read {file_path} from S3")
        return variable
                
    except Exception as e:
        error_message = f"Couldn't load {file_path} from S3. {str(type(e))}, {str(e)}"
        if required: 
            logging.critical(error_message)
            raise(e)
        logging.warning(error_message)
        return None


def load_publication_config(
    publication_config_file_name="publication_config.yml",
    dev_mode=False,
    disable_gpt=False
):
    """Import general settings and assets from files on S3, used for all subscribers
    
    ARGUMENTS
    publication_config_file_name (str): file name for the general publication parameters YML file in the S3 bucket identified by BUCKET_PATH
    dev_mode (bool): If True we're in development or debug mode, so don't send emails or modify headline_logs.
    disable_gpt (bool): If True, don't call the GPT API and incur costs, for example during dev or debug cycles.
    
    RETURNS
    publication_config (dict): General settings for all subscribers 
    """
    
    bucket_path = get_fn_secret("BUCKET_PATH")

    # Load publication settings
    publication_config = load_s3(bucket_path, publication_config_file_name)
    
    # Populate config dictionary, loading more assets as needed
    if publication_config["editorial"].get("enable_thoughts_of_the_day", False):
        thoughts_of_the_day = load_s3(bucket_path, "thoughts_of_the_day.yml", required=False)
        if thoughts_of_the_day: 
            thoughts_of_the_day = thoughts_of_the_day["quotes"]
    else:
        thoughts_of_the_day = []
    
    return {
        "bucket_path": bucket_path,
        "email_delivery": not dev_mode, # If dev_mode is True, don't send emails
        "sender": publication_config["sender"],
        "layout": {
            "template_html": load_s3(bucket_path, "template.htm", "r"),
            "logo_url": publication_config["layout"]["logo_url"],
        },
        "editorial": {
            "one_headline_keywords": publication_config["editorial"].get("one_headline_keywords", []),
            "substance_rules": load_s3(bucket_path, "substance_rules.yml"),
            "cache_issue_content": False if dev_mode else True,
            "gpt": publication_config["editorial"].get("gpt", None) if not disable_gpt else None,
            "smart_deduper": publication_config["editorial"].get("smart_deduper", None),
            "enable_thoughts_of_the_day": publication_config["editorial"].get("enable_thoughts_of_the_day", False)
        },
        "forecast" : publication_config.get("forecast", {}),
        "news_sources": publication_config["news_sources"],
        "events_sources": publication_config.get("events_sources", []),
        "alerts_sources": publication_config.get("alerts_sources", []),
        "image_sources": publication_config.get("image_sources", []),
        "thoughts_of_the_day": thoughts_of_the_day
    }


def get_subscriber_list(bucket_path, folder_name="finite_files"):
    """Find the subscribers (the names of their config files) on the Finite News bucket.
    
    ARGUMENTS
    bucket_path (str): The location of the S3 bucket where required files are stored.
    folder_name (str): The part of the path that contains the folder on the bucket, if present. Used to remove from .
    
    NOTE: 
    1. Assumes the folder is at the root of the bucket. If it's nested, use relative path up to root.
    2. Assumes all files in the folder that begin with "config_" are a subscriber config file.
    
    RETURNS
    subscriber_config_file_names (list): yml file names in finite bucket
    """
    
    fn_bucket = (
        boto3
        .resource("s3")
        .Bucket(
            bucket_path
            .split("//")
            [1]
            .split("/")
            [0]
        )
    )
    # Iterate through files on the bucket and select those that begin with config_
    return [
        f.key.replace(f"{folder_name}/", "")
        for f in fn_bucket.objects.filter(Prefix=f"{folder_name}/")
        if f.key.startswith(f"{folder_name}/config_")
    ]


def filter_sources(sources, selections, criterion="name"):
    """Applies subscriber's selections to list of sources

    ARGUMENTS
    sources (list of dict): Descriptions of sources from publication_config
    selections (list of str): Names/Categories of sources that subscriber wants
    criterion (str): "name" or "category" for how to filter
    
    RETURNS
    sources_filtered (list of dict): Subset of sources that match subscriber's selections
    """
    if not selections:
        filtered_sources = []
    else:
        # Get the source details from publication config that were in susbcriber's selections
        # while keeping the order of subscriber's selections
        filtered_sources = sorted(
            [source for source in sources if source[criterion] in selections],
            key=lambda x: selections.index(x[criterion])
        )
    logging.info(f"Filtered out sources not in {selections}: {[source['name'] for source in sources if source[criterion] not in selections]}")
    return filtered_sources


def day_name_to_number(day_name):
    """Helper function to convert a named day like "Friday" to an ISO standard number like 4.
    
    ARGUMENTS
    day_name (str): Fully spelled out day of week. Case insensitive
    
    RETURNS
    day_number (int): Number from 0-6, where 0 = Monday
    """
    calendar.Calendar(firstweekday=0)
    return (
        {name: i for i, name in enumerate(calendar.day_name)}
        .get(day_name.capitalize(), None)
        + 1  # To align with isocalendar()
    )


def parse_frequency_config(frequency_config):
    """Determine if today is the day to deliver a scheduled section of the paper.
    
    NOTE
    * Reminder: When adding new frequencies, update get_stocks_plot()
    * Assumes the paper is delivered once per day. So "daily" config always returns True.
    
    ARGUMENTS
    frequency_config (dict): Parameters for a cycle
    
    RETURNS
    match (bool): Is today on the schedule?
    """
    
    if not frequency_config:
        logging.warning("Missing frequency config, assumed to be False")
        return False
    
    frequency = frequency_config.get("frequency", None) # The cadence label
        
    if frequency == "monthly":
        dom = frequency_config.get("day_of_month", 1) # Which day of the month does subscriber want?
        dom_today = date.today().day # What's the day of the month today?
        match = dom == dom_today
        logging.info(f"parse_frequency_config, result: {match}. Today: {dom_today}. Requested: {dom}")
        return match
    
    if frequency == "weekly":
        dow_number = day_name_to_number(frequency_config.get("day_of_week", "Monday"))
        _, today_dow_number = date.today().isocalendar()[1:] # Get today's "week of year" and "day of week" as integers using ISO standard
        match = today_dow_number==dow_number # Is today the requested day of the week?
        logging.info(f"parse_frequency_config, result: {match}. Today dow number: {today_dow_number}. Requested: {frequency_config.get('day_of_week')}, dow_number: {dow_number}")
        return match

    if frequency == "every_other_week":
        dow_number = day_name_to_number(frequency_config.get("day_of_week", "Monday"))
        eow_odd = frequency_config.get("eow_odd", False) # Should every other week fall on odd week numbers or even?
        week_number, today_dow_number = date.today().isocalendar()[1:] # Get today's "week of year" and "day of week" as integers using ISO standard
        week_number_match = (
                (eow_odd and week_number % 2 == 1)
                or (not eow_odd and week_number % 2 == 0)
        )
        match = (
            today_dow_number==dow_number # Today is the requested day of the week
            and week_number_match # This is the requested week
        )
        logging.info(f"parse_frequency_config, result: {match}. Today week_number, dow_number: {week_number, today_dow_number}. Requested: dow_number: {dow_number}, eow_odd: {eow_odd}")
        return match

    if frequency == "daily":
        logging.info(f"parse_frequency_config, result: True, because 'daily' is always True")
        return True

    if frequency == "weekdays":
        match = date.today().isoweekday()<6
        logging.info(f"parse_frequency_config, result: {match}, requested: weekeday (iso number <6), today: {date.today().isoweekday()}.")
        return match

    else:
        logging.warning(f"Unexpected value for frequency: {frequency}. Not parsed.")
        return False


def load_events_config(publication_events_sources, subscriber_sources):
    """Import the parameters for an events calendar source, if subscriber requests. 
    
    Includes deciding if today meets the subscriber's frequency for including events in their issue.
    
    ARGUMENTS
    publication_events_sources (list of dict): The source config for event-type sources in the publication, if present
    subscriber_sources (list of str): The subscriber's source configuration, which may or may not include preferences for event sources
    
    RETURNS
    event_sources (list of dict): Source configuration for events that 
    """
    
    try:
        subscriber_events_sources = subscriber_sources.get("events", {}).get("sources", [])
        frequency_match = parse_frequency_config(
            subscriber_sources.get("events", {}).get("frequency", {"frequency":"daily"})
        )
        if frequency_match and len(publication_events_sources)>0 and len(subscriber_events_sources)>0:
            return filter_sources(publication_events_sources, subscriber_events_sources)
        else:
            return []
    except Exception as e:
        logging.warning(f"Unhandled exception in load_events_config: {str(type(e))}, {str(e)}. publication_events_sources: {publication_events_sources}. subscriber_sources: {subscriber_sources}")
        return []
        
        
def load_stocks_config(subscriber_sources):
    """Import the parameters for subscriber's stock section, if any.

    ARGUMENTS
    subscriber_sources (list of str): The subscriber's source configuration, which may or may not include preferences for stock data
    
    RETURNS
    stocks (list of lists): Lists of tickers for each plot [ [TICKER1, TICKER2], [TICKER3, TICKER4] ], or empty list for none
    frequency (str): How often we are delivering this section. Used to determine how much history to put in plot
    """
    
    try:
        stocks_config = subscriber_sources.get("stocks", None)
        if not stocks_config:
            return [], None
        frequency_match = parse_frequency_config(stocks_config)
        frequency = stocks_config.get("frequency", None)
        ticker_sets = stocks_config.get("tickers", [])
        if len(ticker_sets)==0 or not frequency_match:
            return [], None
        return [[ticker.strip() for ticker in ticker_set.split(",")] for ticker_set in ticker_sets], frequency

    except Exception as e:
        logging.warning(f"Unhandled exception in load_stocks_confg: {str(type(e))}, {str(e)}. subscriber_sources: {subscriber_sources}")
        return [], None
    

def load_subscriber_config(subscriber_config_file_name, publication_config):
    """Import subscriber-specific parameters and combine with general publication settings
    
    ARGUMENTS
    subscriber_config_file_name (str): name of the subscriber's config YML file in the S3 bucket
    publication_config (dict): loaded general publication parameters
    
    RETURNS
    issue (dict): Settings for an issue, combining subscriber and general publication parameters
    """
    
    # Transfer general settings from publication config
    issue = deepcopy(publication_config) # Copy dict with nested dicts
    
    # Load subscriber's specific settings
    subscriber_config = load_s3(issue["bucket_path"], subscriber_config_file_name)
    
    # Check are we delivering this issue today?
    if not parse_frequency_config(
        subscriber_config.get("issue_frequency", {"frequency":"daily"})
    ):
        logging.info(f"{subscriber_config['email']}: No issue today, not in issue_frequency.")
        return None
    
    issue["admin"] = subscriber_config.get("admin", False)
    issue["sender"]["subject"] = subscriber_config["editorial"].get("subject", "Finite News")
    issue["subscriber_email"] = subscriber_config["email"]

    issue["editorial"]["add_car_talk_credit"] = subscriber_config["editorial"].get("add_car_talk_credit", False)
    issue["editorial"]["cache_path"] = subscriber_config.get("editorial", {}).get("cache_path", "")
    if issue["editorial"]["cache_path"] == "":
        logging.warning("No cache_path. Not logging new content or removing content already presented in last year.")
    else:
        # If cache file doesn't exist, create empty file
        if not fs.exists(issue["bucket_path"] + issue["editorial"]["cache_path"]):
            with fs.open(issue["bucket_path"] + issue["editorial"]["cache_path"], "wb") as f:
                f.write(b"")
    issue["requests_timeout"] = subscriber_config.get("editorial",{}).get("requests_timeout", 30)
    
    issue["news_sources"] = filter_sources(
        issue["news_sources"],
        subscriber_config.get("sources", {}).get("news_categories", []),
        "category"
    )
    issue["events_sources"] = load_events_config(publication_config["events_sources"], subscriber_config["sources"])
    issue["alerts_sources"] = filter_sources(
        issue["alerts_sources"],
        subscriber_config.get("sources", {}).get("alerts_sources", []),
        "name"
    )
    issue["alerts_sources"] += [
        {
            "name": "MBTA API: Alerts",
            "type": "mbta_alerts",
            "route": mbta_source.get("route", None),
            "stations": mbta_source.get("stations", []),
            "direction_id": mbta_source.get("direction_id", None),
        }
        for mbta_source in subscriber_config.get("sources",{}).get("mbta",[])
        if parse_frequency_config(mbta_source)
    ]
    issue["image_sources"] = filter_sources(
        issue["image_sources"],
        subscriber_config.get("sources", {}).get("image_categories", []),
        "category"
    )          
    issue["stocks"], issue["stocks_frequency"] = load_stocks_config(subscriber_config["sources"])
    issue["sports"] = subscriber_config.get("sports", {})
    issue["forecast"] = subscriber_config.get("forecast", {})
    if issue["forecast"]:
        issue["forecast"]["api_snooze_bar"] = publication_config["forecast"].get("api_snooze_bar", None)
        
    issue["slogans"] = subscriber_config["slogans"]
    if publication_config["editorial"]["enable_thoughts_of_the_day"]:
        issue["thoughts_of_the_day"] = subscriber_config.get("thoughts_of_the_day", [])
        if issue["thoughts_of_the_day"] and subscriber_config["editorial"].get("add_shared_thoughts", False):
            issue["thoughts_of_the_day"] += publication_config["thoughts_of_the_day"] 
    else: 
        issue["thoughts_of_the_day"] = []
    return issue


def load_subscriber_configs(dev_mode, disable_gpt):
    """Create the config file needed to generate each issue, combining publication and subscriber settings.
    
    ARGUMENTS
    dev_mode (bool): If True we're in development or debug mode, so don't send emails or modify headline_logs.
    disable_gpt (bool): If True, don't call the GPT API and incur costs, for example during dev or debug cycles.

    RETURNS
    subscriber_configs (list): issue_config for each subscriber we need to generate an issue for
    """ 
    
    publication_config = load_publication_config(dev_mode=dev_mode, disable_gpt=disable_gpt)    
    subscriber_list = get_subscriber_list(publication_config["bucket_path"])
    subscriber_configs = [
        load_subscriber_config(subscriber_config_file_name, publication_config)
        for subscriber_config_file_name in subscriber_list
    ]
    subscriber_configs = [c for c in subscriber_configs if c is not None] # Drop Nones, which occur if today is not in the issue_frequency for that subscriber
    
    # Sort subscribers so the "admins" go last. 
    # Allows the admin email issue(s) to include logging warnings from the non-admin issues.
    subscriber_configs = sorted(subscriber_configs , key=lambda x: x["admin"]) 
    return subscriber_configs