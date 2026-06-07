import logging
from datetime import datetime, timezone

import requests

from plugins.base_plugin.base_plugin import BasePlugin


logger = logging.getLogger(__name__)


class FootballNightBoard(BasePlugin):
    ESPN_BASE = "https://site.api.espn.com/apis/site/v2/sports/football/nfl"

    TEAM_DATA = {
        "ARI": {"id": "22", "name": "Arizona Cardinals"},
        "ATL": {"id": "1", "name": "Atlanta Falcons"},
        "BAL": {"id": "33", "name": "Baltimore Ravens"},
        "BUF": {"id": "2", "name": "Buffalo Bills"},
        "CAR": {"id": "29", "name": "Carolina Panthers"},
        "CHI": {"id": "3", "name": "Chicago Bears"},
        "CIN": {"id": "4", "name": "Cincinnati Bengals"},
        "CLE": {"id": "5", "name": "Cleveland Browns"},
        "DAL": {"id": "6", "name": "Dallas Cowboys"},
        "DEN": {"id": "7", "name": "Denver Broncos"},
        "DET": {"id": "8", "name": "Detroit Lions"},
        "GB": {"id": "9", "name": "Green Bay Packers"},
        "HOU": {"id": "34", "name": "Houston Texans"},
        "IND": {"id": "11", "name": "Indianapolis Colts"},
        "JAX": {"id": "30", "name": "Jacksonville Jaguars"},
        "KC": {"id": "12", "name": "Kansas City Chiefs"},
        "LV": {"id": "13", "name": "Las Vegas Raiders"},
        "LAC": {"id": "24", "name": "Los Angeles Chargers"},
        "LAR": {"id": "14", "name": "Los Angeles Rams"},
        "MIA": {"id": "15", "name": "Miami Dolphins"},
        "MIN": {"id": "16", "name": "Minnesota Vikings"},
        "NE": {"id": "17", "name": "New England Patriots"},
        "NO": {"id": "18", "name": "New Orleans Saints"},
        "NYG": {"id": "19", "name": "New York Giants"},
        "NYJ": {"id": "20", "name": "New York Jets"},
        "PHI": {"id": "21", "name": "Philadelphia Eagles"},
        "PIT": {"id": "23", "name": "Pittsburgh Steelers"},
        "SEA": {"id": "26", "name": "Seattle Seahawks"},
        "SF": {"id": "25", "name": "San Francisco 49ers"},
        "TB": {"id": "27", "name": "Tampa Bay Buccaneers"},
        "TEN": {"id": "10", "name": "Tennessee Titans"},
        "WAS": {"id": "28", "name": "Washington Commanders"},
    }

    def __init__(self, plugin):
        super().__init__(plugin)
        self.plugin = plugin

    def _get_settings_template_params(self, plugin_settings):
        plugin_settings = plugin_settings or {}
        return {
            "plugin_settings": plugin_settings,
            "style_settings": True,
            "title": plugin_settings.get("title", ""),
            "nflTeam": plugin_settings.get("nflTeam", "ARI"),
        }

    def generate_image(self, settings, device_config):
        template_params = self.get_template_context(settings, device_config)

        try:
            width, height = device_config.get_resolution()
        except Exception as e:
            raise RuntimeError(f"Failed to get display resolution: {e}")

        return self.render_image(
            dimensions=(width, height),
            html_file="nfl_team_schedule.html",
            css_file="nfl_team_schedule.css",
            template_params=template_params,
        )

    def get_template_context(self, settings, device_config):
        settings = settings or {}
        team_code = str(settings.get("nflTeam", "ARI")).strip().upper()
        custom_title = str(settings.get("title", "")).strip()
        now_utc = datetime.now(timezone.utc)

        context = {
            "plugin_settings": settings,
            "style_settings": True,
            "title": custom_title,
            "nfl_team_code": team_code,
            "nfl_team_name": self._team_name_from_code(team_code),
            "display_mode": "next",
            "display_label": "Today",
            "display_time": "TBD",
            "time": "TBD",
            "day": "Today",
            "game_mode": "next",
            "networks": [],
            "venue": "",
            "week_label": "",
            "status_text": "",
            "away_team": {},
            "home_team": {},
            "away_team_logo": "",
            "home_team_logo": "",
            "away_team_stats": {
                "wins": 0,
                "losses": 0,
                "ties": 0,
                "pointsFor": "N/A",
                "pointsAgainst": "N/A",
            },
            "home_team_stats": {
                "wins": 0,
                "losses": 0,
                "ties": 0,
                "pointsFor": "N/A",
                "pointsAgainst": "N/A",
            },
            "error": None,
        }

        try:
            selected_game = self._get_preferred_game_for_team(team_code, now_utc)
            if not selected_game:
                context["error"] = f"No upcoming games found for {team_code}"
                return context

            is_last_game = self._is_last_game(selected_game, now_utc)
            game_context = self._build_game_context(selected_game, is_last_game)

            away_abbrev = ((game_context["away_team"] or {}).get("abbrev") or "").upper()
            home_abbrev = ((game_context["home_team"] or {}).get("abbrev") or "").upper()

            standings = self._get_standings_map()
            game_context["away_team_logo"] = self._logo_filename(away_abbrev)
            game_context["home_team_logo"] = self._logo_filename(home_abbrev)
            game_context["away_team_stats"] = standings.get(
                away_abbrev,
                {"wins": 0, "losses": 0, "ties": 0, "pointsFor": "N/A", "pointsAgainst": "N/A"},
            )
            game_context["home_team_stats"] = standings.get(
                home_abbrev,
                {"wins": 0, "losses": 0, "ties": 0, "pointsFor": "N/A", "pointsAgainst": "N/A"},
            )

            if not custom_title:
                if is_last_game:
                    game_context["title"] = "Last Game"
                elif game_context.get("day") == "Today":
                    game_context["title"] = "Today's Matchup"
                else:
                    game_context["title"] = f"{game_context.get('day', 'Upcoming')} Matchup"

            game_context["plugin_settings"] = settings
            game_context["style_settings"] = True
            game_context["nfl_team_name"] = context["nfl_team_name"]

            context.update(game_context)
            return context

        except requests.RequestException:
            logger.exception("NFL Team Schedule request error")
            context["error"] = "NFL schedule could not be loaded"
            return context
        except Exception:
            logger.exception("NFL Team Schedule unexpected error")
            context["error"] = "Unable to load NFL schedule"
            return context

    def _request_json(self, url):
        response = requests.get(
            url,
            timeout=(5, 20),
            headers={"User-Agent": "InkyPi NFL Schedule/1.0"},
        )
        response.raise_for_status()
        return response.json()

    def _current_season_year(self, now_utc):
        return now_utc.year if now_utc.month >= 8 else now_utc.year - 1

    def _game_start_dt(self, game):
        date_str = game.get("date")
        if not date_str:
            return None
        try:
            return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        except Exception:
            return None

    def _get_preferred_game_for_team(self, team_code, now_utc):
        team_info = self.TEAM_DATA.get(team_code)
        if not team_info:
            return None

        season = self._current_season_year(now_utc)
        team_id = team_info["id"]
        data = self._request_json(f"{self.ESPN_BASE}/teams/{team_id}/schedule?season={season}")

        events = data.get("events", [])
        if not events:
            return None

        future_games = []
        past_games = []

        for game in events:
            start_dt = self._game_start_dt(game)
            if not start_dt:
                continue

            status_type = (((game.get("status") or {}).get("type")) or {})
            state = (status_type.get("state") or "").lower()
            completed = bool(status_type.get("completed"))

            if completed or state == "post":
                past_games.append((start_dt, game))
            elif start_dt >= now_utc:
                future_games.append((start_dt, game))
            else:
                past_games.append((start_dt, game))

        future_games.sort(key=lambda item: item[0])
        past_games.sort(key=lambda item: item[0], reverse=True)

        if future_games:
            return future_games[0][1]
        if past_games:
            return past_games[0][1]
        return events[0]

    def _is_last_game(self, game, now_utc):
        start_dt = self._game_start_dt(game)
        if not start_dt:
            return False

        status_type = (((game.get("status") or {}).get("type")) or {})
        if bool(status_type.get("completed")):
            return True

        state = (status_type.get("state") or "").lower()
        if state == "post":
            return True

        return start_dt < now_utc

    def _team_from_competitor(self, competitor):
        competitor = competitor or {}
        team = competitor.get("team") or {}
        record_items = competitor.get("records") or []

        summary_record = ""
        for record in record_items:
            if (record.get("type") or "").lower() == "total":
                summary_record = record.get("summary") or ""
                break
        if not summary_record and record_items:
            summary_record = (record_items[0] or {}).get("summary") or ""

        return {
            "id": team.get("id"),
            "abbrev": (team.get("abbreviation") or "").upper(),
            "displayName": team.get("displayName") or "",
            "shortDisplayName": team.get("shortDisplayName") or "",
            "location": team.get("location") or "",
            "name": team.get("name") or "",
            "record": summary_record,
            "score": competitor.get("score"),
            "winner": competitor.get("winner"),
            "homeAway": competitor.get("homeAway"),
        }

    def _build_game_context(self, game, is_last_game=False):
        competitions = game.get("competitions") or []
        competition = competitions[0] if competitions else {}

        competitors = competition.get("competitors") or []
        away_raw = next((c for c in competitors if (c.get("homeAway") or "").lower() == "away"), {})
        home_raw = next((c for c in competitors if (c.get("homeAway") or "").lower() == "home"), {})

        away_team = self._team_from_competitor(away_raw)
        home_team = self._team_from_competitor(home_raw)

        start_dt = self._game_start_dt(game)
        local_dt = start_dt.astimezone() if start_dt else None

        if local_dt:
            display_time = local_dt.strftime("%-I:%M %p")
            local_today = datetime.now().astimezone().date()
            day_label = "Today" if local_dt.date() == local_today else local_dt.strftime("%A")
        else:
            display_time = "TBD"
            day_label = "Upcoming"

        status = game.get("status") or {}
        status_type = status.get("type") or {}
        status_text = status_type.get("shortDetail") or status.get("displayClock") or ""

        venue = ((competition.get("venue") or {}).get("fullName")) or ""
        broadcasts = competition.get("broadcasts") or []

        networks = []
        for item in broadcasts:
            names = item.get("names") or []
            for name in names:
                if name and name not in networks:
                    networks.append(name)

        week = game.get("week") or {}
        week_label = week.get("text") or ""

        return {
            "display_mode": "previous" if is_last_game else "next",
            "display_label": "Last Game" if is_last_game else day_label,
            "display_time": display_time,
            "time": display_time,
            "day": day_label,
            "game_mode": "last" if is_last_game else "next",
            "networks": networks,
            "venue": venue,
            "week_label": week_label,
            "status_text": status_text,
            "away_team": away_team,
            "home_team": home_team,
        }

    def _get_standings_map(self):
        data = self._request_json(f"{self.ESPN_BASE}/standings")
        standings_map = {}

        children = (data.get("children") or [])
        for conference in children:
            standings = ((conference.get("standings") or {}).get("entries")) or []
            for entry in standings:
                team = entry.get("team") or {}
                abbrev = (team.get("abbreviation") or "").upper()
                stats = entry.get("stats") or []

                stat_map = {}
                for stat in stats:
                    key = stat.get("name") or stat.get("abbreviation")
                    if key:
                        stat_map[key] = stat.get("value")
                        if stat.get("displayValue") is not None:
                            stat_map[f"{key}_display"] = stat.get("displayValue")

                standings_map[abbrev] = {
                    "wins": int(stat_map.get("wins", 0) or 0),
                    "losses": int(stat_map.get("losses", 0) or 0),
                    "ties": int(stat_map.get("ties", 0) or 0),
                    "pointsFor": stat_map.get("pointsFor_display", stat_map.get("pointsFor", "N/A")),
                    "pointsAgainst": stat_map.get("pointsAgainst_display", stat_map.get("pointsAgainst", "N/A")),
                }

        return standings_map

    def _team_name_from_code(self, team_code):
        return (self.TEAM_DATA.get(team_code) or {}).get("name", team_code)

    def _logo_filename(self, team_abbrev):
        return f"{team_abbrev.lower()}.png" if team_abbrev else ""