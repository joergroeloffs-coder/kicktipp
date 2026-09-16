"""Lokale Oberflaeche: Spiele + Form + vorgeschlagene Tipps anzeigen,
manuell anpassen und per Knopfdruck an Kicktipp senden.

Die Spieleliste kommt direkt von Kicktipps eigener Tippabgabe-Seite (nicht
aus einer selbst erratenen OpenLigaDB-Kandidatenliste), damit die UI immer
exakt zeigt, was diese Kicktipp-Gruppe tatsaechlich tippt."""
from __future__ import annotations

import datetime as dt
import os

from flask import Flask, jsonify, request
from dotenv import load_dotenv

from src.openliga import LEAGUES, get_season_matches, get_table
from src.predictor import team_form, predict_score
from src.kicktipp_client import KicktippSession, submit_tips

load_dotenv()

app = Flask(__name__, static_folder="static", static_url_path="/static")


def _kicktipp_credentials():
    return (
        os.environ.get("KICKTIPP_GROUP"),
        os.environ.get("KICKTIPP_USERNAME"),
        os.environ.get("KICKTIPP_PASSWORD"),
    )


@app.get("/")
def index():
    return app.send_static_file("index.html")


@app.get("/api/matches")
def api_matches():
    group, username, password = _kicktipp_credentials()
    if not group or not username or not password:
        return jsonify({"error": "KICKTIPP_GROUP/USERNAME/PASSWORD nicht gesetzt (.env pruefen)."}), 400

    all_matches = [m for league in LEAGUES for m in get_season_matches(league)]
    table = [entry for league in LEAGUES for entry in get_table(league)]

    with KicktippSession(group, username, password) as session:
        kicktipp_matches = session.list_all_matches()

    now = dt.datetime.now(dt.timezone.utc)
    result = []
    for m in kicktipp_matches:
        home_form = team_form(all_matches, m["home_team"], now, venue="home")
        away_form = team_form(all_matches, m["away_team"], now, venue="away")
        if m["existing_home_goals"] is not None:
            home_goals, away_goals = int(m["existing_home_goals"]), int(m["existing_away_goals"])
        else:
            home_goals, away_goals = predict_score(
                all_matches, m["home_team"], m["away_team"], table=table, odds=m["odds"]
            )
        result.append(
            {
                "home_team": m["home_team"],
                "away_team": m["away_team"],
                "already_tipped": m["existing_home_goals"] is not None,
                "predicted_home_goals": home_goals,
                "predicted_away_goals": away_goals,
                "home_form": {
                    "goals_scored_avg": round(home_form.goals_scored_avg, 2),
                    "goals_conceded_avg": round(home_form.goals_conceded_avg, 2),
                },
                "away_form": {
                    "goals_scored_avg": round(away_form.goals_scored_avg, 2),
                    "goals_conceded_avg": round(away_form.goals_conceded_avg, 2),
                },
            }
        )
    return jsonify(result)


@app.post("/api/submit")
def api_submit():
    group, username, password = _kicktipp_credentials()
    if not group or not username or not password:
        return jsonify({"error": "KICKTIPP_GROUP/USERNAME/PASSWORD nicht gesetzt (.env pruefen)."}), 400

    tips = request.get_json(force=True)
    if not isinstance(tips, list) or not tips:
        return jsonify({"error": "Keine Tipps im Request."}), 400

    messages = submit_tips(group, username, password, tips)
    return jsonify({"messages": messages})


if __name__ == "__main__":
    app.run(debug=True, port=5000)
