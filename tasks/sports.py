"""🏀 Sports! Functions to report and edit sports content"""

import logging
import pandas as pd
import requests
from datetime import date, datetime, timedelta
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


def build_nba_player_table(team_stats):
    """Build an HTML table displaying NBA player statistics for a team's recent game.

    ARGUMENTS
    team_stats (dict): A dictionary containing the team's name, the game's date, and a list of player statistics.

    RETURNS
    HTML table displaying player statistics for the game.
    """

    table = f"""<h5 style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; color: #212529; margin: 10px 0; font-size: 1rem;">{team_stats['teamName']}</h5>
               <table style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen-Sans, Ubuntu, Cantarell, 'Helvetica Neue', sans-serif; 
                      font-size: 0.75rem; 

                      width: auto; 
                      border-collapse: collapse; 
                      background: white; 
                      border-radius: 8px; 
                      overflow: hidden; 
                      box-shadow: 0 1px 3px rgba(0,0,0,0.12);">
               <tr style="background: #f8f9fa; border-bottom: 2px solid #dee2e6;">
                 <th style="padding: 12px 8px; text-align: left; color: #212529; font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px;">Player</th>
                 <th style="padding: 12px 8px; text-align: right; color: #212529; font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px;">Min</th>
                 <th style="padding: 12px 8px; text-align: right; color: #212529; font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px;">Pts</th>
                 <th style="padding: 12px 8px; text-align: right; color: #212529; font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px;">Reb</th>
                 <th style="padding: 12px 8px; text-align: right; color: #212529; font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px;">Ast</th>
                 <th style="padding: 12px 8px; text-align: center; color: #212529; font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px;">FG</th>
                 <th style="padding: 12px 8px; text-align: center; color: #212529; font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px;">3PT</th>
                 <th style="padding: 12px 8px; text-align: center; color: #212529; font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px;">FT</th>
               </tr>"""
    for player in team_stats["players"]:
        stats = player["statistics"]
        minutes = stats["minutesCalculated"].replace("PT", "").replace("M", "")
        minutes = str(int(minutes)) if minutes != "00" else "0"

        if minutes == "0":
            continue

        table += f"""<tr style="border-bottom: 1px solid #dee2e6; transition: background-color 0.2s;">
                    <td style="padding: 12px 8px; text-align: left; color: #212529; font-weight: 500;">{player['name']}</td>
                    <td style="padding: 12px 8px; text-align: right; color: #212529;">{minutes}</td>
                    <td style="padding: 12px 8px; text-align: right; color: #212529;">{stats['points']}</td>
                    <td style="padding: 12px 8px; text-align: right; color: #212529;">{stats['reboundsTotal']}</td>
                    <td style="padding: 12px 8px; text-align: right; color: #212529;">{stats['assists']}</td>
                    <td style="padding: 12px 8px; text-align: center; color: #212529;">{stats['fieldGoalsMade']}-{stats['fieldGoalsAttempted']}</td>
                    <td style="padding: 12px 8px; text-align: center; color: #212529;">{stats['threePointersMade']}-{stats['threePointersAttempted']}</td>
                    <td style="padding: 12px 8px; text-align: center; color: #212529;">{stats['freeThrowsMade']}-{stats['freeThrowsAttempted']}</td>
                    </tr>"""
    return table + "</table>"


def get_nba_box_score(team_name, requests_timeout):
    """Get box score for a team's most recent completed game within last 24 hours.

    ARGUMENTS:
    team_name (str): NBA team such as "Celtics" or "Lakers"
    requests_timeout (int): Number of seconds to wait before giving up on HTTP request

    RETURNS:
    HTML string with formatted box score tables, or None if no recent completed game
    """
    try:
        # Get today's scoreboard
        url = "https://cdn.nba.com/static/json/staticData/scheduleLeagueV2.json"
        r = requests.get(url, timeout=requests_timeout)
        schedule = r.json()

        # Find most recent completed game for team
        game_id = None
        game_end_time = None
        now_utc = datetime.now(pytz.UTC)

        for gameday in reversed(schedule["leagueSchedule"]["gameDates"]):
            for game in gameday["games"]:
                if (
                    game["homeTeam"]["teamName"] == team_name
                    or game["awayTeam"]["teamName"] == team_name
                ):
                    if game["gameStatus"] == 3:  # Completed games
                        game_start_time = datetime.fromisoformat(
                            game["gameDateTimeUTC"].replace("Z", "+00:00")
                        )
                        game_end_time = game_start_time + timedelta(hours=3, minutes=30)
                        if now_utc - game_end_time < timedelta(hours=24):
                            game_id = game["gameId"]
                            break
            if game_id:
                break

        if not game_id:
            return None

        # Get detailed box score data
        box_url = (
            f"https://cdn.nba.com/static/json/liveData/boxscore/boxscore_{game_id}.json"
        )
        box = requests.get(box_url, timeout=requests_timeout).json()["game"]

        # Build quarter-by-quarter scoring table
        periods = box["homeTeam"]["periods"]
        home_scores = [p["score"] for p in periods]
        away_scores = [p["score"] for p in box["awayTeam"]["periods"]]

        quarter_table = """<table style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen-Sans, Ubuntu, Cantarell, 'Helvetica Neue', sans-serif; 
                                 font-size: 0.75rem; 
                                 width: fit-content; 
                                 border-collapse: collapse; 
                                 background: white; 
                                 border-radius: 8px; 
                                 overflow: hidden; 
                                 box-shadow: 0 1px 3px rgba(0,0,0,0.12); 
                                 margin-bottom: 20px;">
                          <tr style="background: #f8f9fa; border-bottom: 2px solid #dee2e6;">
                            <th style="padding: 12px 8px; text-align: left; color: #212529; font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px;">Team</th>"""
        for i in range(len(periods)):
            quarter_table += f'<th style="padding: 12px 8px; text-align: right; color: #212529; font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px;">Q{i+1}</th>'
        quarter_table += '<th style="padding: 12px 8px; text-align: right; color: #212529; font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px;">Final</th></tr>'

        quarter_table += f"""<tr style="border-bottom: 1px solid #dee2e6;">
                            <td style="padding: 12px 8px; text-align: left; font-weight: 500; color: #212529;">{box['homeTeam']['teamName']}</td>"""
        for score in home_scores:
            quarter_table += f'<td style="padding: 12px 8px; text-align: right; color: #212529;">{score}</td>'
        quarter_table += f'<td style="padding: 12px 8px; text-align: right; font-weight: bold; color: #212529;">{box["homeTeam"]["score"]}</td></tr>'

        quarter_table += f"""<tr style="border-bottom: 1px solid #dee2e6;">
                            <td style="padding: 12px 8px; text-align: left; font-weight: 500; color: #212529;">{box['awayTeam']['teamName']}</td>"""
        for score in away_scores:
            quarter_table += f'<td style="padding: 12px 8px; text-align: right; color: #212529;">{score}</td>'
        quarter_table += f'<td style="padding: 12px 8px; text-align: right; font-weight: bold; color: #212529;">{box["awayTeam"]["score"]}</td></tr></table>'

        home_table = build_nba_player_table(box["homeTeam"])
        away_table = build_nba_player_table(box["awayTeam"])

        # Determine winner and loser
        home_score = box["homeTeam"]["score"]
        away_score = box["awayTeam"]["score"]
        if home_score > away_score:
            if team_name == box["homeTeam"]["teamName"]:
                game_header = f"""<h4 style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; 
                                        color: #212529; 
                                        margin: 20px 0; 
                                        font-size: 1.2rem;">{team_name} beat {box['awayTeam']['teamName']} {home_score}-{away_score}</h4>"""
            else:
                game_header = f"""<h4 style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; 
                                        color: #212529; 
                                        margin: 20px 0; 
                                        font-size: 1.2rem;">{team_name} lose to {box['homeTeam']['teamName']} {home_score}-{away_score}</h4>"""
        else:
            if team_name == box["awayTeam"]["teamName"]:
                game_header = f"""<h4 style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; 
                                        color: #212529; 
                                        margin: 20px 0; 
                                        font-size: 1.2rem;">{team_name} beat {box['homeTeam']['teamName']} {away_score}-{home_score}</h4>"""
            else:
                game_header = f"""<h4 style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; 
                                        color: #212529; 
                                        margin: 20px 0; 
                                        font-size: 1.2rem;">{team_name} lose to {box['awayTeam']['teamName']} {away_score}-{home_score}</h4>"""

        return f"""<div style="max-width: 100%; overflow-x: auto;">
                    {game_header}
                    <details>
                        <summary style="cursor: pointer; padding: 10px; background-color: #f8f9fa; border: 1px solid #dee2e6; border-radius: 4px; margin-bottom: 10px;">Box score</summary>
                        {quarter_table}
                        {home_table}
                        <div style="margin: 20px 0;"></div>
                        {away_table}
                    </details>
                  </div>""".replace("\n", "")

    except Exception as e:
        logging.warning(
            f"NBA box score error for {team_name}: {str(type(e))}, {str(e)}"
        )
        return None
