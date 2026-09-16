"""Login bei Kicktipp und Setzen von Tipps per Browser-Automation.

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


_COOKIE_BUTTON_TEXTS = [
    "Alle akzeptieren",
    "Akzeptieren",
    "Einverstanden",
    "Zustimmen",
    "Accept all",
    "Accept",
]


def _dismiss_cookie_banner(page) -> None:
    """Best-effort: schliesst Cookie-/Consent-Banner, falls vorhanden.
    Solche Overlays verschieben sonst das Layout und lassen Formularfelder
    ausserhalb des sichtbaren Viewports landen."""
    for text in _COOKIE_BUTTON_TEXTS:
        try:
            button = page.get_by_role("button", name=text, exact=False)
            button.click(timeout=2000)
            return
        except Exception:
            continue


def _click(page, selector: str) -> bool:
    """Robuster Klick: erst in den sichtbaren Bereich scrollen, dann klicken;
    falls das (z.B. wegen eines Overlays) haengen bleibt, erzwungen klicken."""
    locator = page.locator(selector).first
    try:
        locator.scroll_into_view_if_needed(timeout=5000)
        locator.click(timeout=10000)
        return True
    except Exception:
        try:
            locator.click(timeout=5000, force=True)
            return True
        except Exception:
            return False


class KicktippSession:
    """Haelt eine eingeloggte Browser-Session auf der Tippabgabe-Seite offen,
    damit Lesen (bereits vorhandene Tipps) und Schreiben in einem Lauf
    passieren koennen."""

    def __init__(self, group: str, username: str, password: str):
        self.group = group
        self.username = username
        self.password = password
        self._pw = None
        self._browser = None
        self.page = None
        self._rows = []

    def __enter__(self) -> "KicktippSession":
        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch()
        self.page = self._browser.new_page(viewport={"width": 1366, "height": 2200})

        self.page.goto(LOGIN_URL)
        _dismiss_cookie_banner(self.page)
        self.page.fill('input[name="kennung"]', self.username)
        self.page.fill('input[name="passwort"]', self.password)
        if not _click(self.page, 'button[type="submit"], input[type="submit"]'):
            raise RuntimeError("Login-Button konnte nicht geklickt werden.")
        self.page.wait_for_load_state("networkidle")

        self.page.goto(f"https://www.kicktipp.de/{self.group}/tippabgabe")
        _dismiss_cookie_banner(self.page)
        self.page.wait_for_load_state("networkidle")

        self._rows = self.page.query_selector_all(
            "table.tippabgabe tr, form#tippabgabeForm tr"
        )
        if not self._rows:
            self._rows = self.page.query_selector_all("tr")
        return self

    def __exit__(self, *exc):
        if self._browser:
            self._browser.close()
        if self._pw:
            self._pw.stop()

    def find_row(self, home_team: str, away_team: str):
        for row in self._rows:
            text = row.inner_text()
            if _names_match(home_team, text) and _names_match(away_team, text):
                return row
        return None

    def debug_row_texts(self, limit: int = 60) -> list[str]:
        """Liefert die Rohtexte aller gefundenen Tabellenzeilen -- nur zur
        Fehlersuche, wenn find_row unerwartet nichts findet."""
        texts = []
        for row in self._rows[:limit]:
            text = " ".join(row.inner_text().split())
            if text:
                texts.append(text)
        return texts

    def debug_row_html(self, limit: int = 3) -> list[str]:
        """Liefert das rohe HTML der ersten Zeilen mit Tipp-Eingabefeldern --
        nur zur Fehlersuche der genauen Tabellenstruktur."""
        html_rows = []
        for row in self._rows:
            if len(self._tip_inputs(row)) >= 2:
                html_rows.append(row.inner_html()[:2000])
            if len(html_rows) >= limit:
                break
        return html_rows

    @staticmethod
    def _tip_inputs(row):
        return row.query_selector_all('input[type="text"], input[type="number"]')

    def read_tip(self, row) -> tuple[str, str] | None:
        """Liest vorhandene Werte; (None, None)-artig wird als leer interpretiert."""
        inputs = self._tip_inputs(row)
        if len(inputs) < 2:
            return None
        return inputs[0].input_value().strip(), inputs[1].input_value().strip()

    def fill_tip(self, row, home_goals: int, away_goals: int) -> bool:
        inputs = self._tip_inputs(row)
        if len(inputs) < 2:
            return False
        inputs[0].fill(str(home_goals))
        inputs[1].fill(str(away_goals))
        return True

    def submit_form(self) -> bool:
        if not _click(self.page, 'button[type="submit"], input[type="submit"]'):
            return False
        self.page.wait_for_load_state("networkidle")
        return True


def submit_tips(group: str, username: str, password: str, tips: list[dict]) -> list[str]:
    """Setzt alle uebergebenen Tipps (ueberschreibt vorhandene Werte).
    Fuer den manuellen UI-Flow, bei dem der Nutzer die Werte explizit bestaetigt hat.
    """
    messages: list[str] = []
    with KicktippSession(group, username, password) as session:
        for tip in tips:
            row = session.find_row(tip["home_team"], tip["away_team"])
            if row is None:
                messages.append(
                    f"Spiel nicht auf Tippabgabe-Seite gefunden: "
                    f"{tip['home_team']} - {tip['away_team']}"
                )
                continue
            if not session.fill_tip(row, tip["home_goals"], tip["away_goals"]):
                messages.append(
                    f"Keine Tipp-Eingabefelder gefunden fuer: "
                    f"{tip['home_team']} - {tip['away_team']}"
                )
                continue
            messages.append(
                f"Tipp gesetzt: {tip['home_team']} {tip['home_goals']}:"
                f"{tip['away_goals']} {tip['away_team']}"
            )

        if session.submit_form():
            messages.append("Tipps abgeschickt.")
        else:
            messages.append("WARNUNG: Absenden-Button nicht gefunden, Tipps evtl. nicht gespeichert.")

    return messages


def submit_missing_tips(group: str, username: str, password: str, candidate_tips: list[dict]) -> list[str]:
    """Backup-Modus: setzt nur Tipps fuer Spiele, die auf Kicktipp noch leer sind.
    Bereits (z.B. manuell per UI) gesetzte Tipps werden nicht ueberschrieben."""
    messages: list[str] = []
    filled_any = False
    debug_dumped = False
    with KicktippSession(group, username, password) as session:
        for tip in candidate_tips:
            row = session.find_row(tip["home_team"], tip["away_team"])
            if row is None:
                messages.append(
                    f"Spiel nicht auf Tippabgabe-Seite gefunden: "
                    f"{tip['home_team']} - {tip['away_team']}"
                )
                if not debug_dumped:
                    messages.append("DEBUG Zeileninhalte auf der Tippabgabe-Seite:")
                    messages.extend(f"  DEBUG: {t}" for t in session.debug_row_texts())
                    messages.append("DEBUG HTML der ersten Tipp-Zeilen:")
                    for html in session.debug_row_html():
                        messages.append(f"  DEBUG-HTML: {html}")
                    debug_dumped = True
                continue

            existing = session.read_tip(row)
            if existing is None:
                messages.append(
                    f"Keine Tipp-Eingabefelder gefunden fuer: "
                    f"{tip['home_team']} - {tip['away_team']}"
                )
                continue

            home_existing, away_existing = existing
            if home_existing and away_existing:
                messages.append(
                    f"Bereits getippt, ueberspringe: {tip['home_team']} - {tip['away_team']}"
                )
                continue

            if session.fill_tip(row, tip["home_goals"], tip["away_goals"]):
                filled_any = True
                messages.append(
                    f"Backup-Tipp gesetzt: {tip['home_team']} {tip['home_goals']}:"
                    f"{tip['away_goals']} {tip['away_team']}"
                )

        if filled_any:
            if session.submit_form():
                messages.append("Backup-Tipps abgeschickt.")
            else:
                messages.append("WARNUNG: Absenden-Button nicht gefunden, Tipps evtl. nicht gespeichert.")
        else:
            messages.append("Nichts zu tun: alle Spiele bereits getippt.")

    return messages
