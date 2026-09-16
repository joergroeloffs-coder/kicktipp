"""Backup-Lauf: fuellt nur Kicktipp-Tipps, die noch nicht (z.B. manuell per UI)
gesetzt wurden. Gedacht als Sicherheitsnetz kurz vor Spielbeginn via GitHub Actions."""
from __future__ import annotations

import os
import sys

from src.openliga import LEAGUES, get_season_matches, get_upcoming_friday_matches
from src.predictor import predict_score
from src.kicktipp_client import submit_missing_tips

WITHIN_DAYS = int(os.environ.get("MATCH_WINDOW_DAYS", "4"))


def main() -> int:
    group = os.environ.get("KICKTIPP_GROUP")
    username = os.environ.get("KICKTIPP_USERNAME")
    password = os.environ.get("KICKTIPP_PASSWORD")

    if not group or not username or not password:
        print(
            "Fehlende Umgebungsvariablen: KICKTIPP_GROUP, KICKTIPP_USERNAME, "
            "KICKTIPP_PASSWORD muessen gesetzt sein (z.B. als GitHub Secrets).",
            file=sys.stderr,
        )
        return 1

    leagues = list(LEAGUES.keys())
    upcoming = get_upcoming_friday_matches(leagues, within_days=WITHIN_DAYS)

    if not upcoming:
        print("Keine anstehenden Spiele im Zeitfenster gefunden.")
        return 0

    all_matches_by_league = {league: get_season_matches(league) for league in leagues}

    tips = []
    for match in upcoming:
        all_matches = all_matches_by_league[match.league]
        home_goals, away_goals = predict_score(all_matches, match)
        tips.append(
            {
                "home_team": match.home_team,
                "away_team": match.away_team,
                "home_goals": home_goals,
                "away_goals": away_goals,
            }
        )
        print(f"Tipp berechnet: {match.home_team} {home_goals}:{away_goals} {match.away_team}")

    screenshot_dir = os.environ.get("KICKTIPP_SCREENSHOT_DIR")
    if screenshot_dir:
        os.makedirs(screenshot_dir, exist_ok=True)

    messages = submit_missing_tips(group, username, password, tips, screenshot_dir=screenshot_dir)
    for msg in messages:
        print(msg)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
