"""Einfache statistische Tipp-Heuristik auf Basis der letzten Spieltage."""
from __future__ import annotations

from dataclasses import dataclass

from src.openliga import Match

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
        and team in (m.home_team, m.away_team)
    ]
    played.sort(key=lambda m: m.kickoff, reverse=True)
    recent = played[:n]
    if not recent:
        return TeamForm(goals_scored_avg=1.3, goals_conceded_avg=1.3)

    scored, conceded = [], []
    for m in recent:
        if m.home_team == team:
            scored.append(m.home_goals or 0)
            conceded.append(m.away_goals or 0)
        else:
            scored.append(m.away_goals or 0)
            conceded.append(m.home_goals or 0)
    return TeamForm(
        goals_scored_avg=sum(scored) / len(scored),
        goals_conceded_avg=sum(conceded) / len(conceded),
    )


def predict_score(all_matches: list[Match], match: Match) -> tuple[int, int]:
    """Liefert einen (Heim, Gast)-Tipp basierend auf Torform der letzten Spiele."""
    home_form = team_form(all_matches, match.home_team, match.kickoff)
    away_form = team_form(all_matches, match.away_team, match.kickoff)

    home_expected = (home_form.goals_scored_avg + away_form.goals_conceded_avg) / 2 * HOME_ADVANTAGE
    away_expected = (away_form.goals_scored_avg + home_form.goals_conceded_avg) / 2 * AWAY_PENALTY

    home_goals = max(0, round(home_expected))
    away_goals = max(0, round(away_expected))
    return home_goals, away_goals
