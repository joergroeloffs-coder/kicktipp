"""Einfache statistische Tipp-Heuristik auf Basis der letzten Spieltage."""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from src.openliga import Match
from src.teamnames import names_match

HOME_ADVANTAGE = 1.15
AWAY_PENALTY = 0.92
FORM_MATCHES = 5


@dataclass
class TeamForm:
    goals_scored_avg: float
    goals_conceded_avg: float


def team_form(all_matches: list[Match], team: str, before, n: int = FORM_MATCHES) -> TeamForm:
    played = [
        m
        for m in all_matches
        if m.finished
        and m.kickoff
        and m.kickoff < before
        and (names_match(team, m.home_team) or names_match(team, m.away_team))
    ]
    played.sort(key=lambda m: m.kickoff, reverse=True)
    recent = played[:n]
    if not recent:
        return TeamForm(goals_scored_avg=1.3, goals_conceded_avg=1.3)

    scored, conceded = [], []
    for m in recent:
        if names_match(team, m.home_team):
            scored.append(m.home_goals or 0)
            conceded.append(m.away_goals or 0)
        else:
            scored.append(m.away_goals or 0)
            conceded.append(m.home_goals or 0)
    return TeamForm(
        goals_scored_avg=sum(scored) / len(scored),
        goals_conceded_avg=sum(conceded) / len(conceded),
    )


def predict_score(
    all_matches: list[Match], home_team: str, away_team: str, before: dt.datetime | None = None
) -> tuple[int, int]:
    """Liefert einen (Heim, Gast)-Tipp basierend auf Torform der letzten Spiele.
    home_team/away_team koennen auch Kicktipps eigene (abgekuerzte)
    Anzeigenamen sein -- der Abgleich mit OpenLigaDB laeuft ueber
    Tokenvergleich, nicht exakte Gleichheit."""
    before = before or dt.datetime.now(dt.timezone.utc)
    home_form = team_form(all_matches, home_team, before)
    away_form = team_form(all_matches, away_team, before)

    home_expected = (home_form.goals_scored_avg + away_form.goals_conceded_avg) / 2 * HOME_ADVANTAGE
    away_expected = (away_form.goals_scored_avg + home_form.goals_conceded_avg) / 2 * AWAY_PENALTY

    home_goals = max(0, round(home_expected))
    away_goals = max(0, round(away_expected))
    return home_goals, away_goals
