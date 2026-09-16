"""Lokale Oberflaeche: Spiele + Form + vorgeschlagene Tipps anzeigen,
manuell anpassen und per Knopfdruck an Kicktipp senden."""
from __future__ import annotations

import os

from flask import Flask, jsonify, request
from dotenv import load_dotenv

from src.openliga import LEAGUES, get_season_matches, get_upcoming_friday_matches
from src.predictor import team_form, predict_score
from src.kicktipp_client import submit_tips

load_dotenv()

app = Flask(__name__, static_folder="static", static_url_path="/static")

WITHIN_DAYS = int(os.environ.get("MATCH_WINDOW_DAYS", "4"))


@app.get("/")
def index():
    return app.send_static_file("index.html")


@app.get("/api/matches")
def api_matches():
    leagues = list(LEAGUES.keys())
    upcoming = get_upcoming_friday_matches(leagues, within_days=WITHIN_DAYS)
    all_matches_by_league = {league: get_season_matches(league) for league in leagues}

    result = []
    for match in upcoming:
        all_matches = all_matches_by_league[match.league]
        home_goals, away_goals = predict_score(all_matches, match)
        home_form = team_form(all_matches, match.home_team, match.kickoff)
        away_form = team_form(all_matches, match.away_team, match.kickoff)
        result.append(
            {
                "match_id": match.match_id,
                "league": LEAGUES[match.league],
                "kickoff": match.kickoff.isoformat() if match.kickoff else None,
                "home_team": match.home_team,
                "away_team": match.away_team,
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
    group = os.environ.get("KICKTIPP_GROUP")
    username = os.environ.get("KICKTIPP_USERNAME")
    password = os.environ.get("KICKTIPP_PASSWORD")
    if not group or not username or not password:
        return jsonify({"error": "KICKTIPP_GROUP/USERNAME/PASSWORD nicht gesetzt (.env pruefen)."}), 400

    tips = request.get_json(force=True)
    if not isinstance(tips, list) or not tips:
        return jsonify({"error": "Keine Tipps im Request."}), 400

    messages = submit_tips(group, username, password, tips)
    return jsonify({"messages": messages})


if __name__ == "__main__":
    app.run(debug=True, port=5000)
