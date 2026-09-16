"""Backup-Lauf: liest die auf Kicktipp tatsaechlich offenen (noch nicht
getippten) Spiele direkt von der Tippabgabe-Seite und fuellt sie -- statt
eine eigene Kandidatenliste zu erraten. Gedacht als Sicherheitsnetz kurz
vor Spielbeginn via GitHub Actions."""
from __future__ import annotations

import os
import sys

from src.openliga import LEAGUES, get_season_matches, get_table
from src.predictor import predict_score
from src.kicktipp_client import submit_missing_tips


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

    all_matches = [m for league in LEAGUES for m in get_season_matches(league)]
    table = [entry for league in LEAGUES for entry in get_table(league)]

    def predict_fn(home_team: str, away_team: str, odds: dict | None) -> tuple[int, int]:
        return predict_score(all_matches, home_team, away_team, table=table, odds=odds)

    screenshot_dir = os.environ.get("KICKTIPP_SCREENSHOT_DIR")
    if screenshot_dir:
        os.makedirs(screenshot_dir, exist_ok=True)

    messages = submit_missing_tips(group, username, password, predict_fn, screenshot_dir=screenshot_dir)
    for msg in messages:
        print(msg)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
