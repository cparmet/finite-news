"""⛈️ Functions for getting the weather forecast"""

import requests
import logging
from time import sleep
from env_canada import ECWeather
import asyncio

from tasks.reporting import scrape_source

def get_nws_forecast(nws_config):
    """Use National Weather Service API to get local forecast.
        
    NOTE: We use a fixed timeout for this API request, overriding publication_config's requests_timeout parameter.
    The value here is based on experience with NWS possibly needing a number of API attempts to get a response
    
    ARGUMENTS
    nws_config (dict): Parameters for calling the NWS API, including keys for:
        - office (str): Which NWS office to get the forecast from (See NOTE above)
        - grid_x (int), grid_y (int): Coordinates for the forecast (See NOTE above)
        - location_name (str): Optional, Town or city name (no state/country etc)
        - api_snooze_bar (int): How many seconds to wait before retrying NWS after an exception

    RETURNS
    forecast (dict or None): Attributes of the forecast retrieved, or None if there was a problem.
    """
    
    MAX_ATTEMPTS = 10 
    try:
        attempts=1
        while attempts<MAX_ATTEMPTS:
            url =f"https://api.weather.gov/gridpoints/{nws_config['office']}/{nws_config['grid_x']},{nws_config['grid_y']}/forecast"
            r = requests.get(url, timeout=5)
            if r.status_code==200:
                break
            else:
                attempts+=1
                logging.info(f"Weather request {r.status_code}. Wait {nws_config['api_snooze_bar']} seconds and retry, take # {attempts} ...")
                sleep(nws_config["api_snooze_bar"])
        
        # Get the next daytime forecast
        # Traverse the list of forecast periods to find the first that isn't Overnight, ~Tuesday Night, Tonight, Evening  
        daytime_forecasts = [
            period for period in r.json()["properties"]["periods"]
            if "night" not in period['name'].lower() 
            and "evening" not in period['name'].lower()
        ]
        if not daytime_forecasts: # No daytime forecasts found
            logging.warning(f"No NWS forecast added because no non-night/overnight period available. Config: {nws_config}. Response from NWS: {r.json()}.")
            print("error")
            return None
        result = daytime_forecasts[0] # Get the daytime forecast that's coming first
        
        # Format forecast
        forecast = {
            "short": result.get("shortForecast", None),
            "detailed": result.get("detailedForecast", None),
            "icon_url": result.get("icon", None)
        }
        forecast["short"] = forecast["short"].capitalize() # Change from Title Case to Sentence case 
        if "location_name" in nws_config:
            forecast["short"] += f" in {nws_config['location_name']}"
        return forecast
    except Exception as e:
        try:
            logging.warning(f"Forecast error after {MAX_ATTEMPTS} attempts: {str(type(e))}, {str(e)}, {r}")
        except UnboundLocalError:
            logging.warning(f"Forecast error after {MAX_ATTEMPTS} attempts: {str(type(e))}, {str(e)}. requests.get() did not return a response r.")
        return None
    

def get_ca_forecast(forecast_config):
    """Use Environment Canada API to get local forecast.
        
    ARGUMENTS
    forecast_config (dict): Parameters for calling the env_canada API, including keys for:
        - lat (float), lon (float): Coordinates for the forecast 
        - location_name (str): Optional, Town or city name (no province etc)

    RETURNS
    forecast (dict or None): Attributes of the forecast retrieved, or None if there was a problem.
    """
    
    try:
        ec_en = ECWeather(coordinates=(forecast_config["lat"], forecast_config["lon"]))
        asyncio.run(ec_en.update())
        forecast_short, forecast_detailed = (
            ec_en
            .daily_forecasts
            [0]
            ["text_summary"]
            .split(".", maxsplit=1)
        )
        # If the first forecast returned is a day forecast, add the second forecast -- tonight
        # If the first forecast is a night forecast, don't add the second forecast. That's tomorrow's day forecast.
        if "night" not in ec_en.daily_forecasts[0]['period'].lower():
            forecast_detailed += f"\n\nTonight: {ec_en.daily_forecasts[1]['text_summary']}"            
        forecast = {
            "short": forecast_short,
            "detailed": forecast_detailed,
        }
        if "location_name" in forecast_config:
            forecast["short"] += f" in {forecast_config['location_name']}"
        return forecast
    except Exception as e:
        logging.warning(f"env_canada forecast error: {str(type(e))}, {str(e)}")
        return None


def get_gws_forecast(forecast_config):
    """Pull latest forecast from German Weather Service's Open Data. 
    
    
    ARGUMENTS
    forecast_config (dict): Parameters for getting GWS data, including keys for:
        - forecast_file (str): the name of the html file on "https://opendata.dwd.de/weather/text_forecasts/html/", the "LATEST" file for the desired region
        - location_name (str): Optional, Town or city name (no province etc)
        - api_timeout (int): Optional, Number of seconds to wait before giving up on a request

        
    RETURNS
    forecast (dict or None): Attributes of the forecast retrieved, or None if there was a problem.
    """
    
    try:
        forecast_config["url"] = f"https://opendata.dwd.de/weather/text_forecasts/html//{forecast_config['forecast_file']}"
        forecast_config["tag"] = "pre"
        
        forecast = {
            # Unlike NWS and env_canada, we don't have a brief forecast to use in the heading. :(
            "short": "Weather forecast",
            
            # But we got a big honking forecast! Just needs some cleaning
            "detailed": (
                scrape_source(forecast_config, forecast_config.get("api_timeout", 30))
                [0]
                .strip("\r\n")
                .replace("\r\n\r\n", "</p><p>")
                .replace("\r\n", " ")
            )
        }
        if "location_name" in forecast_config:
            forecast["short"] += f" for {forecast_config['location_name']}"
        return forecast

    except Exception as e:
        logging.warning(f"German Weather Service forecast error: {str(type(e))}, {str(e)}, {forecast_config}")
        return None
    
    
def get_forecast(forecast_config):
    """Use selected API to get weather forecast
    
    ARGUMENT
    forecast_config (dict): Parameters for calling the API, depending on "source"
    
    RETURNS
    forecast (dict or None): Attributes of the forecast retrieved, or None if there was a problem.
    """
    
    if forecast_config["source"] == "env_canada":
        return get_ca_forecast(forecast_config)
    elif forecast_config["source"]== "gws":
        return get_gws_forecast(forecast_config)
    elif forecast_config["source"] == "nws":
        return get_nws_forecast(forecast_config)
    else:
        logging.warning(f"Unexpected forecast source. No forecast added. {forecast_config}") 
        return None