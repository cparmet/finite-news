## Welcome to Finite News!
## This entry point orchestrates all the tasks to create and email issues of Finite News. 

import logging
from tqdm import tqdm
import traceback

from tasks.io import init_logging, load_subscriber_configs
from tasks.publishing import create_issue, deliver_issue

DEV_MODE = True # True will not send email and not cache newly fetched headlines for dedup later
DISABLE_GPT = True # True will not call GPT API, so we don't incur costs while debugging
LOGGING_LEVEL = "warning" # What level of logging should go in admin's issue/local log file?
                       # Use "warning" by default. 
                       # Use "info" to get more detailed FN messages for debugging
                       # Use "debug" to get lower-level messages from dependencies
                       # Reminder: When re-running notebook, to change logging level for example, restart kernel. Logger can only initialize once

def run_finite_news(dev_mode, disable_gpt, logging_level):
    """Entry point to create and deliver issues to all subscribers of Finite News.

    ARGUMENTS
    dev_mode (bool): If True we're in development or debug mode, so don't send emails or modify headline_logs, and also output plots to local files.
    disable_gpt (bool): If True, don't call the GPT API and incur costs, for example during dev or debug cycles.
    logging_level (level from logging library): The deepest granularity of log messages to track
    
    RETURNS
    None
    """
    
    log_stream = init_logging(logging_level, dev_mode)
    for subscriber_config in tqdm(load_subscriber_configs(dev_mode, disable_gpt)):
        try:
            html, images = create_issue(subscriber_config, log_stream, dev_mode)
            deliver_issue(subscriber_config, html, images)
        except Exception as e:
            if dev_mode: # During dev or debugging, raise exception and show traceback in notebook.
                raise e
            logging.critical(f"{subscriber_config['subscriber_email']}: Issue failed due to unhandled exception. {traceback.format_exc()}") # In prod mode, save traceback for admin's issue, but continue to try to publish the next issue.
    print("👍")

if __name__ == "__main__":
    run_finite_news(DEV_MODE, DISABLE_GPT, LOGGING_LEVEL)