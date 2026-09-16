"""Login bei Kicktipp und automatisches Setzen von Tipps per Browser-Automation.

Hinweis: Kicktipp bietet keine offizielle API. Die Formularstruktur der
Tippabgabe-Seite kann sich aendern -- falls das Setzen fehlschlaegt, zuerst
pruefen, ob sich die Feld-/Zeilenstruktur auf kicktipp.de geaendert hat.
"""
from __future__ import annotations

import re

from playwright.sync_api import sync_playwright

LOGIN_URL = "https://www.kicktipp.de/info/profil/login"


def _normalize(name: str) -> str:
    name = name.lower()
    name = re.sub(r"[^a-z0-9]", "", name)
    return name


def _names_match(openliga_name: str, kicktipp_name: str) -> bool:
    a, b = _normalize(openliga_name), _normalize(kicktipp_name)
    if not a or not b:
        return False
    return a in b or b in a


def submit_tips(group: str, username: str, password: str, tips: list[dict]) -> list[str]:
    """tips: Liste von {"home_team", "away_team", "home_goals", "away_goals"}.

    Gibt eine Liste von Log-/Warnmeldungen zurueck (z.B. nicht gefundene Spiele).
    """
    messages: list[str] = []

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()

        page.goto(LOGIN_URL)
        page.fill('input[name="kennung"]', username)
        page.fill('input[name="passwort"]', password)
        page.click('button[type="submit"], input[type="submit"]')
        page.wait_for_load_state("networkidle")

        page.goto(f"https://www.kicktipp.de/{group}/tippabgabe")
        page.wait_for_load_state("networkidle")

        rows = page.query_selector_all("table.tippabgabe tr, form#tippabgabeForm tr")
        if not rows:
            rows = page.query_selector_all("tr")

        for tip in tips:
            row = None
            for r in rows:
                text = r.inner_text()
                if _names_match(tip["home_team"], text) and _names_match(tip["away_team"], text):
                    row = r
                    break

            if row is None:
                messages.append(
                    f"Spiel nicht auf Tippabgabe-Seite gefunden: "
                    f"{tip['home_team']} - {tip['away_team']}"
                )
                continue

            inputs = row.query_selector_all('input[type="text"], input[type="number"]')
            if len(inputs) < 2:
                messages.append(
                    f"Keine Tipp-Eingabefelder gefunden fuer: "
                    f"{tip['home_team']} - {tip['away_team']}"
                )
                continue

            inputs[0].fill(str(tip["home_goals"]))
            inputs[1].fill(str(tip["away_goals"]))
            messages.append(
                f"Tipp gesetzt: {tip['home_team']} {tip['home_goals']}:"
                f"{tip['away_goals']} {tip['away_team']}"
            )

        submit_btn = page.query_selector('button[type="submit"], input[type="submit"]')
        if submit_btn:
            submit_btn.click()
            page.wait_for_load_state("networkidle")
            messages.append("Tipps abgeschickt.")
        else:
            messages.append("WARNUNG: Absenden-Button nicht gefunden, Tipps evtl. nicht gespeichert.")

        browser.close()

    return messages
