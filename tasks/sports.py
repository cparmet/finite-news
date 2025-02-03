"""🏀 Sports! Functions to report and edit sports content"""

import logging
import pandas as pd
import requests
from datetime import date, datetime, timedelta
import pytz

# Scoreboard inline CSS styles
SCOREBOARD_FONT_FAMILY = """
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif
"""
SCOREBOARD_TABLE_FONT_FAMILY = "font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen-Sans, Ubuntu, Cantarell, 'Helvetica Neue', sans-serif"
SCOREBOARD_TABLE_STYLE = """
    font-size: 0.6rem;
    border-collapse: collapse;
    background: white;
    border-radius: 8px;
    overflow: hidden;
    box-shadow: 0 1px 3px rgba(0,0,0,0.12)
"""
SCOREBOARD_HEADER_CELL_STYLE = """
    padding: 8px 6px;
    text-align: left;
    color: #212529;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.5px
"""
SCOREBOARD_DATA_CELL_STYLE = "padding: 8px 6px; text-align: left; color: #212529"


def get_todays_nba_game(team_name, requests_timeout):
    """Call the NBA API to find out if a team is playing today.

    NOTE
    This updated version accounts for the limitation of using the NBA API's current day's scoreboard:
    the scoreboard isn't always updated until a certain hour in the morning, after FN may be run.
    The updated approach here looks at the whole year's schedule, including post-season. Adapted from : https://github.com/swar/nba_api/issues/296

    TODO: Clean and simpify. No need to use Pandas.

    ARGUMENTS
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


def get_recent_completed_nba_game(team_name, requests_timeout):
    """
    Get the last completed NBA game for a given team, if it started within the last 24 hours.

    ARGUMENTS
    team_name (str): The name of the team to check for a recent game
    requests_timeout (int): Number of seconds to wait before giving up on an HTTP request

    RETURNS
    the game ID, or None if no recent completed game was found
    """

    # Get the NBA schedule and game status
    url = "https://cdn.nba.com/static/json/staticData/scheduleLeagueV2.json"
    r = requests.get(url, timeout=requests_timeout)
    schedule = r.json()

    # Find a completed game with our team that started within the last 24 hours
    now_utc = datetime.now(pytz.UTC)
    for gameday in reversed(schedule["leagueSchedule"]["gameDates"]):
        for game in gameday["games"]:
            if (
                game["gameStatus"] == 3  # Game is completed
                and (  # And our team participated
                    game["homeTeam"]["teamName"] == team_name
                    or game["awayTeam"]["teamName"] == team_name
                )
            ):
                game_start_time = datetime.fromisoformat(
                    game["gameDateTimeUTC"].replace("Z", "+00:00")
                )
                # If the completed game started <24 hours ago, it's new to us!
                if now_utc - game_start_time < timedelta(hours=24):
                    return game["gameId"]

    # If we get here, we didn't find any such game
    return None


def get_nba_game_headline(box, team_name):
    """Create headline with final score from a box score with our team

    ARGUMENTS
    box (dict): Box score for a completed NBA game
    team_name (str): Name of team we're tracking

    RETURNS
    str headline with final score
    """

    home_score = box["homeTeam"]["score"]
    away_score = box["awayTeam"]["score"]

    if home_score > away_score:
        if team_name == box["homeTeam"]["teamName"]:
            return f"""<h4>🏀 {team_name} beat {box['awayTeam']['teamName']} {home_score}-{away_score}</h4>"""
        else:
            return f"""<h4>🏀 {team_name} lose to {box['homeTeam']['teamName']} {home_score}-{away_score}</h4>"""
    else:
        if team_name == box["awayTeam"]["teamName"]:
            return f"""<h4>🏀 {team_name} beat {box['homeTeam']['teamName']} {away_score}-{home_score}</h4>"""
        else:
            return f"""<h4>🏀 {team_name} lose to {box['awayTeam']['teamName']} {away_score}-{home_score}</h4>"""


def build_nba_game_quarter_table(box):
    """Build table of quarter-by-quarter scoring totals

    ARGUMENTS
    box (dict): Box score data for the game

    RETURNS
    HTML table of quarter-by-quarter scoring totals as a string
    """

    periods = box["homeTeam"]["periods"]
    quarter_table = f"""
        <table style="{SCOREBOARD_TABLE_FONT_FAMILY}; {SCOREBOARD_TABLE_STYLE}; margin-bottom: 16px;">
            <tr style="background: #f8f9fa; border-bottom: 2px solid #dee2e6;">
                <th style="{SCOREBOARD_HEADER_CELL_STYLE}">Team</th>
    """
    # Add a column for each quarter
    for i in range(len(periods)):
        quarter_table += f'<th style="{SCOREBOARD_HEADER_CELL_STYLE}; text-align: right;">Q{i+1}</th>'
    # Add a column for the final score
    quarter_table += f'<th style="{SCOREBOARD_HEADER_CELL_STYLE}; text-align: right;">Final</th></tr>'

    # Add a row for each team's quarter totals
    for team in [box["awayTeam"], box["homeTeam"]]:
        # Team
        quarter_table += f"""<tr style="border-bottom: 1px solid #dee2e6;">
                        <td style="{SCOREBOARD_DATA_CELL_STYLE}; font-weight: 500;">{team['teamName']}</td>"""
        scores = [p["score"] for p in team["periods"]]
        for score in scores:
            quarter_table += f'<td style="{SCOREBOARD_DATA_CELL_STYLE}; text-align: right;">{score}</td>'
        quarter_table += f'<td style="{SCOREBOARD_DATA_CELL_STYLE}; text-align: right; font-weight: bold;">{team["score"]}</td></tr>'

    return quarter_table + "</table>"


def build_nba_game_player_stats_table(team_stats):
    """Create an HTML table displaying NBA player statistics for a team's recent game.

    ARGUMENTS
    team_stats (dict): A dictionary containing the team's name, the game's date, and a list of player statistics.

    RETURNS
    HTML table displaying player statistics for the game.
    """

    # Set up the table and header row
    table = f"""<h5 style="font-size: 0.8rem; margin: 8px 0;">{team_stats['teamName']}</h5>
               <table style="{SCOREBOARD_TABLE_FONT_FAMILY}; {SCOREBOARD_TABLE_STYLE}; width: auto;">
               <tr style="background: #f8f9fa; border-bottom: 2px solid #dee2e6;">
                 <th style="{SCOREBOARD_HEADER_CELL_STYLE}">Player</th>
                 <th style="{SCOREBOARD_HEADER_CELL_STYLE}; text-align: right;">Min</th>
                 <th style="{SCOREBOARD_HEADER_CELL_STYLE}; text-align: right;">Pts</th>
                 <th style="{SCOREBOARD_HEADER_CELL_STYLE}; text-align: right;">Reb</th>
                 <th style="{SCOREBOARD_HEADER_CELL_STYLE}; text-align: right;">Ast</th>
                 <th style="{SCOREBOARD_HEADER_CELL_STYLE}; text-align: center;">FG</th>
                 <th style="{SCOREBOARD_HEADER_CELL_STYLE}; text-align: center;">3PT</th>
                 <th style="{SCOREBOARD_HEADER_CELL_STYLE}; text-align: center;">FT</th>
               </tr>"""

    # Add a row for each player who played
    for player in team_stats["players"]:
        stats = player["statistics"]
        minutes = stats["minutesCalculated"].replace("PT", "").replace("M", "")
        minutes = str(int(minutes)) if minutes != "00" else "0"

        # Don't add players who didn't play
        if minutes == "0":
            continue

        table += f"""<tr style="border-bottom: 1px solid #dee2e6; transition: background-color 0.2s;">
                    <td style="{SCOREBOARD_DATA_CELL_STYLE}; font-weight: 500;">{player['name']}</td>
                    <td style="{SCOREBOARD_DATA_CELL_STYLE}; text-align: right;">{minutes}</td>
                    <td style="{SCOREBOARD_DATA_CELL_STYLE}; text-align: right;">{stats['points']}</td>
                    <td style="{SCOREBOARD_DATA_CELL_STYLE}; text-align: right;">{stats['reboundsTotal']}</td>
                    <td style="{SCOREBOARD_DATA_CELL_STYLE}; text-align: right;">{stats['assists']}</td>
                    <td style="{SCOREBOARD_DATA_CELL_STYLE}; text-align: center;">{stats['fieldGoalsMade']}-{stats['fieldGoalsAttempted']}</td>
                    <td style="{SCOREBOARD_DATA_CELL_STYLE}; text-align: center;">{stats['threePointersMade']}-{stats['threePointersAttempted']}</td>
                    <td style="{SCOREBOARD_DATA_CELL_STYLE}; text-align: center;">{stats['freeThrowsMade']}-{stats['freeThrowsAttempted']}</td>
                    </tr>"""
    return table + "</table>"


def get_nba_box_score(team_name, requests_timeout):
    """Get box score for a team's most recent completed game within last 24 hours.

    ARGUMENTS:
    team_name (str): NBA team such as "Celtics" or "Lakers"
    requests_timeout (int): Number of seconds to wait before giving up on HTTP request

    RETURNS:
    Dictionary with "teams" as list and "content" as HTML string with formatted box score tables, or None if no recent completed game
    """
    try:
        # Get the id of the completed game with this team in past 24 hours, if any
        game_id = get_recent_completed_nba_game(team_name, requests_timeout)
        if not game_id:
            return None

        # Create HTML elements to describe the game
        box_url = (
            f"https://cdn.nba.com/static/json/liveData/boxscore/boxscore_{game_id}.json"
        )
        box = requests.get(box_url, timeout=requests_timeout).json()["game"]
        game_headline = get_nba_game_headline(box, team_name)
        quarter_table = build_nba_game_quarter_table(box)
        away_table = build_nba_game_player_stats_table(box["awayTeam"])
        home_table = build_nba_game_player_stats_table(box["homeTeam"])

        # Format the results
        return {
            # The names of the teams in the box score, for de-duping
            "teams": [box["homeTeam"]["teamName"], box["awayTeam"]["teamName"]],
            # The headline and box score
            "content": f"""<div style="max-width: 100%; overflow-x: auto;">
                    {game_headline}
                    {quarter_table}
                    <div style="display: flex; gap: 24px; flex-wrap: nowrap; overflow-x: auto;">
                        <div style="flex: 0 0 auto;">{away_table}</div>
                        <div style="flex: 0 0 auto;">{home_table}</div>
                    </div>
                  </div>""".replace("\n", ""),
        }

    except Exception as e:
        logging.warning(
            f"NBA box score error for {team_name}: {str(type(e))}, {str(e)}"
        )
        return None


def get_nba_scoreboard(nba_teams, requests_timeout):
    scoreboard = [
        get_nba_box_score(nba_team, requests_timeout) for nba_team in nba_teams
    ]
    # Remove empty results
    scoreboard = [box_score for box_score in scoreboard if box_score]

    # If we got results, dedupe them.
    # If Lakers played Clippers and a subscriber follows both, only show the box score once
    if scoreboard:
        scoreboard_content_deduped = []
        teams_already_reported = []
        for box_score in scoreboard:
            # If this box score has a team NOT already in the list, add it
            if box_score["teams"][0] not in teams_already_reported:
                # Extract just the content (HTML) from the box score dictionary
                scoreboard_content_deduped.append(box_score["content"])
                teams_already_reported += box_score["teams"]
        return scoreboard_content_deduped

    else:
        return scoreboard  # Empty list []
