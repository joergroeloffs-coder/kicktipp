"""Zugriff auf die offene OpenLigaDB-API fuer 1./2./3. Liga."""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

import requests

API_BASE = "https://api.openligadb.de"
LEAGUES = {
    "bl1": "1. Bundesliga",
    "bl2": "2. Bundesliga",
    "bl3": "3. Liga",
}


@dataclass
class Match:
    match_id: int
    league: str
    matchday: int
    kickoff: dt.datetime | None
    home_team: str
    away_team: str
    finished: bool
    home_goals: int | None
    away_goals: int | None


def _current_season() -> int:
    # OpenLigaDB-Saisons laufen z.B. "2025" fuer Saison 2025/26; Wechsel im Sommer.
    today = dt.date.today()
    return today.year if today.month >= 7 else today.year - 1


def _parse_match(raw: dict, league: str) -> Match:
    kickoff = None
    if raw.get("matchDateTimeUTC"):
        kickoff = dt.datetime.fromisoformat(raw["matchDateTimeUTC"].replace("Z", "+00:00"))
    results = raw.get("matchResults") or []
    final = next((r for r in results if r.get("resultTypeID") == 2), None) or (
        results[-1] if results else None
    )
    return Match(
        match_id=raw["matchID"],
        league=league,
        matchday=raw.get("group", {}).get("groupOrderID", 0),
        kickoff=kickoff,
        home_team=raw["team1"]["teamName"],
        away_team=raw["team2"]["teamName"],
        finished=bool(raw.get("matchIsFinished")),
        home_goals=final["pointsTeam1"] if final else None,
        away_goals=final["pointsTeam2"] if final else None,
    )


def get_season_matches(league: str, season: int | None = None) -> list[Match]:
    """Alle Spiele der Saison (vergangen + kommend) fuer eine Liga."""
    season = season if season is not None else _current_season()
    url = f"{API_BASE}/getmatchdata/{league}/{season}"
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    return [_parse_match(m, league) for m in resp.json()]


@dataclass
class TableEntry:
    team: str
    points: int
    matches: int
    goal_diff: int


def get_table(league: str, season: int | None = None) -> list[TableEntry]:
    """Aktuelle Tabelle einer Liga (Punkte, Tordifferenz) -- als Mass fuer
    die generelle Staerke eines Teams unabhaengig von dessen letzten Spielen."""
    season = season if season is not None else _current_season()
    url = f"{API_BASE}/getbltable/{league}/{season}"
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    entries = []
    for raw in resp.json():
        matches = raw.get("matches") or 0
        entries.append(
            TableEntry(
                team=raw["teamInfoObject"]["teamName"],
                points=raw.get("points", 0),
                matches=matches,
                goal_diff=(raw.get("goals", 0) - raw.get("opponentGoals", 0)),
            )
        )
    return entries
