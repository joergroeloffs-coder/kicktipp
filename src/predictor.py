"""Tipp-Heuristik, die mehrere Signale kombiniert:

1. Torform der letzten Spiele je Team, getrennt nach Heim-/Auswaertsspielen
   (ein Team performt oft deutlich unterschiedlich zuhause vs. auswaerts).
2. Aktuelle Ligatabelle (Punkte/Tordifferenz pro Spiel) als Mass fuer die
   generelle Saisonstaerke, unabhaengig von kurzfristiger Form.
3. Direkter Vergleich (letzte Duelle zwischen genau diesen beiden Teams).
4. Buchmacher-Quoten, die Kicktipp auf der Tippabgabe-Seite selbst mit
   anzeigt -- die von Wettanbietern implizierten Siegwahrscheinlichkeiten
   sind ein sehr starkes, bereits vorhandenes Signal.

Kein ML-Modell, aber deutlich mehr als eine reine 5-Spiele-Torschnitt-Regel.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from src.openliga import Match, TableEntry
from src.teamnames import names_match

HOME_ADVANTAGE = 1.15
AWAY_PENALTY = 0.92
FORM_MATCHES = 6
H2H_MATCHES = 5

# Gewichte, mit denen die einzelnen Signale den Basiswert (reine Torform)
# verschieben. Odds bekommen das groesste Gewicht, da sie Marktwissen
# (Verletzungen, Aufstellungen, etc.) einpreisen, das uns sonst fehlt.
TABLE_WEIGHT = 0.4
H2H_WEIGHT = 0.5
ODDS_WEIGHT = 0.6


@dataclass
class TeamForm:
    goals_scored_avg: float
    goals_conceded_avg: float


def _matches_for_team(all_matches: list[Match], team: str, before: dt.datetime) -> list[Match]:
    return [
        m
        for m in all_matches
        if m.finished
        and m.kickoff
        and m.kickoff < before
        and (names_match(team, m.home_team) or names_match(team, m.away_team))
    ]


def team_form(
    all_matches: list[Match], team: str, before: dt.datetime, venue: str | None = None, n: int = FORM_MATCHES
) -> TeamForm:
    """Torform der letzten `n` Spiele. venue="home"/"away" beschraenkt auf
    Heim- bzw. Auswaertsspiele; None nimmt beide Seiten."""
    played = _matches_for_team(all_matches, team, before)
    if venue == "home":
        played = [m for m in played if names_match(team, m.home_team)]
    elif venue == "away":
        played = [m for m in played if names_match(team, m.away_team)]

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


def head_to_head_diff(
    all_matches: list[Match], home_team: str, away_team: str, before: dt.datetime, n: int = H2H_MATCHES
) -> float | None:
    """Durchschnittliche Tordifferenz (aus Sicht des jetzigen Heimteams) in
    den letzten direkten Duellen. None, wenn es keine gibt."""
    duels = [
        m
        for m in all_matches
        if m.finished
        and m.kickoff
        and m.kickoff < before
        and (
            (names_match(home_team, m.home_team) and names_match(away_team, m.away_team))
            or (names_match(home_team, m.away_team) and names_match(away_team, m.home_team))
        )
    ]
    if not duels:
        return None
    duels.sort(key=lambda m: m.kickoff, reverse=True)
    diffs = []
    for m in duels[:n]:
        hg, ag = m.home_goals or 0, m.away_goals or 0
        diffs.append((hg - ag) if names_match(home_team, m.home_team) else (ag - hg))
    return sum(diffs) / len(diffs)


def table_strength(table: list[TableEntry], team: str) -> float | None:
    """Punkte- und Tordifferenz pro Spiel als einzelner Staerke-Wert.
    None, wenn das Team in der Tabelle nicht gefunden wird."""
    for entry in table:
        if names_match(team, entry.team) and entry.matches > 0:
            return entry.points / entry.matches + 0.5 * (entry.goal_diff / entry.matches)
    return None


def _odds_expected_diff(odds: dict) -> float | None:
    """Wandelt Buchmacher-Quoten in eine implizierte erwartete Tordifferenz
    (Heim - Gast) um."""
    try:
        p_home = 1 / odds["home"]
        p_draw = 1 / odds["draw"]
        p_away = 1 / odds["away"]
    except (KeyError, ZeroDivisionError, TypeError):
        return None
    total = p_home + p_draw + p_away
    if total <= 0:
        return None
    p_home, p_away = p_home / total, p_away / total
    # Empirische Skalierung: ein klarer Favorit (p_home - p_away nahe 0.8)
    # entspricht im Schnitt einer Tordifferenz von ca. 2 Toren.
    return (p_home - p_away) * 2.5


def predict_score_explained(
    all_matches: list[Match],
    home_team: str,
    away_team: str,
    before: dt.datetime | None = None,
    table: list[TableEntry] | None = None,
    odds: dict | None = None,
) -> dict:
    """Wie predict_score, aber liefert zusaetzlich alle Zwischenwerte --
    damit sich ein konkreter Tipp nachvollziehen laesst, statt nur das
    Endergebnis zu sehen."""
    before = before or dt.datetime.now(dt.timezone.utc)

    home_form = team_form(all_matches, home_team, before, venue="home")
    away_form = team_form(all_matches, away_team, before, venue="away")

    home_expected = (home_form.goals_scored_avg + away_form.goals_conceded_avg) / 2 * HOME_ADVANTAGE
    away_expected = (away_form.goals_scored_avg + home_form.goals_conceded_avg) / 2 * AWAY_PENALTY
    total_expected = home_expected + away_expected
    diff_after_form = home_expected - away_expected
    diff = diff_after_form

    home_strength = away_strength = None
    diff_after_table = diff
    if table:
        home_strength = table_strength(table, home_team)
        away_strength = table_strength(table, away_team)
        if home_strength is not None and away_strength is not None:
            diff += TABLE_WEIGHT * (home_strength - away_strength)
    diff_after_table = diff

    h2h = head_to_head_diff(all_matches, home_team, away_team, before)
    if h2h is not None:
        diff = diff + H2H_WEIGHT * (h2h - diff) / (1 + H2H_WEIGHT)
    diff_after_h2h = diff

    odds_diff = None
    if odds:
        odds_diff = _odds_expected_diff(odds)
        if odds_diff is not None:
            diff = (1 - ODDS_WEIGHT) * diff + ODDS_WEIGHT * odds_diff

    home_goals = max(0, round((total_expected + diff) / 2))
    away_goals = max(0, round((total_expected - diff) / 2))

    return {
        "home_team": home_team,
        "away_team": away_team,
        "home_form": home_form,
        "away_form": away_form,
        "home_expected_goals_from_form": round(home_expected, 3),
        "away_expected_goals_from_form": round(away_expected, 3),
        "total_expected_goals": round(total_expected, 3),
        "diff_after_form": round(diff_after_form, 3),
        "home_table_strength": round(home_strength, 3) if home_strength is not None else None,
        "away_table_strength": round(away_strength, 3) if away_strength is not None else None,
        "diff_after_table": round(diff_after_table, 3),
        "head_to_head_diff": round(h2h, 3) if h2h is not None else None,
        "diff_after_h2h": round(diff_after_h2h, 3),
        "odds": odds,
        "odds_implied_diff": round(odds_diff, 3) if odds_diff is not None else None,
        "final_diff": round(diff, 3),
        "home_goals": home_goals,
        "away_goals": away_goals,
    }


def predict_score(
    all_matches: list[Match],
    home_team: str,
    away_team: str,
    before: dt.datetime | None = None,
    table: list[TableEntry] | None = None,
    odds: dict | None = None,
) -> tuple[int, int]:
    """Liefert einen (Heim, Gast)-Tipp aus mehreren kombinierten Signalen
    (Torform Heim/Auswaerts, Tabellenstaerke, direkter Vergleich, Quoten).
    home_team/away_team koennen auch Kicktipps eigene (abgekuerzte)
    Anzeigenamen sein -- der Abgleich mit OpenLigaDB laeuft ueber
    Tokenvergleich, nicht exakte Gleichheit."""
    result = predict_score_explained(all_matches, home_team, away_team, before, table, odds)
    return result["home_goals"], result["away_goals"]
