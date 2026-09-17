"""Zeigt die einzelnen Rechenschritte hinter dem Tipp fuer ein konkretes
Spiel -- zum Nachvollziehen, warum die Heuristik zu diesem Ergebnis kommt.

Nutzung: python explain_tip.py "Holstein Kiel" "VfL Osnabrueck"

Die Quoten werden live von Kicktipps Tippabgabe-Seite gelesen (falls
KICKTIPP_GROUP/USERNAME/PASSWORD gesetzt sind), sonst nur aus OpenLigaDB
berechnet (ohne Quoten-Signal)."""
from __future__ import annotations

import os
import sys

from src.openliga import LEAGUES, get_season_matches, get_table
from src.predictor import predict_score_explained
from src.kicktipp_client import KicktippSession


def main() -> int:
    if len(sys.argv) != 3:
        print('Nutzung: python explain_tip.py "Heimteam" "Gastteam"', file=sys.stderr)
        return 1
    home_team, away_team = sys.argv[1], sys.argv[2]

    group = os.environ.get("KICKTIPP_GROUP")
    username = os.environ.get("KICKTIPP_USERNAME")
    password = os.environ.get("KICKTIPP_PASSWORD")

    odds = None
    if group and username and password:
        with KicktippSession(group, username, password) as session:
            for m in session.list_all_matches():
                if home_team.lower() in m["home_team"].lower() and away_team.lower() in m["away_team"].lower():
                    odds = m["odds"]
                    home_team, away_team = m["home_team"], m["away_team"]
                    break

    all_matches = [m for league in LEAGUES for m in get_season_matches(league)]
    table = [entry for league in LEAGUES for entry in get_table(league)]

    result = predict_score_explained(all_matches, home_team, away_team, table=table, odds=odds)
    for key, value in result.items():
        print(f"{key}: {value}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
