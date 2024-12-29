"""🏀 Sports! Functions to report and edit sports content"""

import logging
import pandas as pd
import requests
from datetime import date, datetime
import pytz


def get_todays_nba_game(team_name, requests_timeout):
    """Call the NBA API to find out if a team is playing today.

    NOTE
    This updated version accounts for the limitation of using the NBA API's current day's scoreboard:
    the scoreboard isn't always updated until a certain hour in the morning, after FN may be run.
    The updated approach here looks at the whole year's schedule, including post-season. Adapted from : https://github.com/swar/nba_api/issues/296

    TODO: Clean and simpify. No need to use Pandas.

    ARGUMENTS:
    team_name (str): NBA team such as "Celtics" or "Lakers"
    requests_timeout (int): Number of seconds to wait before giving up on an HTTP request

    RETURNS
    A headline-style string update if the team is playing tonight, or None
    """

    try:
        url = "https://cdn.nba.com/static/json/staticData/scheduleLeagueV2.json"
        r = requests.get(url, timeout=requests_timeout)
        schedule = r.json()
        schedule = schedule["leagueSchedule"]["gameDates"]
        games = []
        for gameday in schedule:
            for game in gameday["games"]:
                game_details = [
                    game["gameDateTimeUTC"],
                    game["homeTeam"]["teamName"],
                    game["homeTeam"]["teamCity"],
                    game["awayTeam"]["teamName"],
                    game["awayTeam"]["teamCity"],
                ]
                game_details = pd.DataFrame(
                    [game_details],
                    columns=[
                        "gameDateTimeUTC",
                        "homeTeam",
                        "homeCity",
                        "awayTeam",
                        "awayCity",
                    ],
                )
                games.append(game_details)

        if not games:
            # A day with no games in the league
            return None

        games = pd.concat([game for game in games])

        eastern = pytz.timezone("US/Eastern")
        games["gameDateTimeUTC"] = pd.to_datetime(
            games["gameDateTimeUTC"], errors="coerce"
        )
        games = games.dropna(subset=["gameDateTimeUTC"])
        games["gameDateTimeEastern"] = games["gameDateTimeUTC"].apply(
            lambda t: t.astimezone(eastern)
        )
        games["gameDate"] = games["gameDateTimeEastern"].apply(lambda d: d.date())

        game = games.loc[
            ((games["awayTeam"] == team_name) | (games["homeTeam"] == team_name))
            & (games["gameDate"] == datetime.today().date())
        ]
        if game.shape[0] == 1:
            game = game.iloc[0]
            tipoff = (
                game["gameDateTimeEastern"]
                .strftime("%I:%M")
                .lstrip("0")
                .replace(":00", "")
            )
            if team_name in game["homeTeam"]:
                other_team = game["awayTeam"]
                return f"🏀 The {team_name} host the {other_team} at {tipoff}."
            else:
                other_city = game["homeCity"]
                return f"🏀 The {team_name} are in {other_city}. Tipoff at {tipoff}."
        else:
            return None
    except Exception as e:
        logging.warning(f"NBA game error for {team_name}: {str(type(e))}, {str(e)}")
        return None


def get_todays_nhl_game(team_place_name, requests_timeout):
    """Call the NHL API to find out if a team is playing today.

    TODO: Clean and simpify. No need to use Pandas.

    ARGUMENTS:
    team_place_name (str): the team's official named place, like Buffalo, Minnesota. For Montréal use the accented e. For New York, use team_place_name of Islanders or Rangers
    requests_timeout (int): Number of seconds to wait before giving up on an HTTP request

    RETURNS
    A headline-style string update if the team is playing tonight, or None
    """

    try:
        url = "https://api-web.nhle.com/v1/schedule/" + date.today().strftime(
            "%Y-%m-%d"
        )
        r = requests.get(url, timeout=requests_timeout)
        schedule = r.json()["gameWeek"][0]["games"]
        games = []
        for game in schedule:
            game_details = [
                game["startTimeUTC"],
                game["homeTeam"]["placeName"]["default"],
                game["awayTeam"]["placeName"]["default"],
            ]
            game_details = pd.DataFrame(
                [game_details],
                columns=[
                    "gameDateTimeUTC",
                    "home_place_name",
                    "away_place_name",
                ],
            )
            games.append(game_details)
        if not games:
            # A day with no games in the league
            return None
        games = pd.concat([game for game in games])
        eastern = pytz.timezone("US/Eastern")
        games["gameDateTimeUTC"] = pd.to_datetime(
            games["gameDateTimeUTC"], errors="coerce"
        )
        games = games.dropna(subset=["gameDateTimeUTC"])
        games["gameDateTimeEastern"] = games["gameDateTimeUTC"].apply(
            lambda t: t.astimezone(eastern)
        )
        games["gameDate"] = games["gameDateTimeEastern"].apply(lambda d: d.date())

        game = games.loc[
            (
                (games["away_place_name"] == team_place_name)
                | (games["home_place_name"] == team_place_name)
            )
            & (games["gameDate"] == datetime.today().date())
        ]
        if game.shape[0] == 1:
            game = game.iloc[0]
            tipoff = (
                game["gameDateTimeEastern"]
                .strftime("%I:%M")
                .lstrip("0")
                .replace(":00", "")
            )
            if team_place_name in game["home_place_name"]:
                other_place_name = game["away_place_name"]
                if team_place_name in ["Islanders", "Rangers"]:
                    team_place_name = f"The {team_place_name} host"
                else:
                    team_place_name += " hosts"
                if other_place_name in ["Islanders", "Rangers"]:
                    other_place_name = f"the {other_place_name}"
                return f"🏒🥅 {team_place_name} {other_place_name}. They face off at {tipoff}."
            else:
                if team_place_name in ["Islanders", "Rangers"]:
                    team_place_name = f"The {team_place_name} are"
                else:
                    team_place_name += " skates"
                other_place_name = game["home_place_name"]
                if other_place_name in ["Islanders", "Rangers"]:
                    other_place_name = f"New York to face the {other_place_name}"
                return f"🏒🥅 {team_place_name} in {other_place_name}. The puck drops at {tipoff}."
        else:
            return None
    except Exception as e:
        logging.warning(
            f"NHL game error for {team_place_name}: {str(type(e))}, {str(e)}"
        )
        return None


def edit_sports_headlines(headlines, teams):
    """Clean and harmonize game headlines. The key outcome: when two of our tracked teams are playing each other, only report once, not twice.

    ARGUMENTS
    headlines (list of str): News related to today's game(s) for tracked teams
    teams (list of str): The names of the tracked teams that may be in the headlines.

    RETURNS
    List of strings with harmonized news about today's game(s)
    """

    # Avoid [None] lists
    headlines = [h for h in headlines if h]

    # If two tracked teams are playing each other, only give one headline
    cleaned_headlines = []
    teams_already_reported = set()
    for headline in headlines:
        teams_found = {t for t in teams if t in headline}
        if not teams_already_reported.intersection(teams_found):
            cleaned_headlines.append(headline)
        teams_already_reported.update(teams_found)
    return cleaned_headlines
