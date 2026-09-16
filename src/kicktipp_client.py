"""Login bei Kicktipp und Setzen von Tipps per Browser-Automation.

Hinweis: Kicktipp bietet keine offizielle API. Die Formularstruktur der
Tippabgabe-Seite kann sich aendern -- falls das Setzen fehlschlaegt, zuerst
pruefen, ob sich die Feld-/Zeilenstruktur auf kicktipp.de geaendert hat.
"""
from __future__ import annotations

import re
import unicodedata

from playwright.sync_api import sync_playwright

LOGIN_URL = "https://www.kicktipp.de/info/profil/login"

# OpenLigaDB nutzt volle Vereinsnamen ("SV Werder Bremen", "Borussia
# Moenchengladbach"), Kicktipp zeigt oft kuerzere/abgekuerzte Varianten
# ("Werder Bremen", "Bor. Moenchengladbach"). Diese generischen Vereins-
# praefixe/-suffixe werden beim Vergleich ignoriert, damit der Abgleich
# ueber den eigentlichen (unterscheidenden) Vereinsnamen funktioniert.
_CLUB_STOPWORDS = {
    "fc", "sv", "sc", "sg", "vfl", "vfb", "tsv", "tsg", "fsv", "bsc",
    "spvgg", "borussia", "bor", "dynamo", "fk", "fka", "vfr", "ssv",
}


def _fold(text: str) -> str:
    """Entfernt Umlaute/Akzente (ae/oe/ue-Umschrift waere zu riskant,
    daher einfach diakritische Zeichen entfernen -- solange das auf beiden
    Vergleichsseiten passiert, bleibt es konsistent)."""
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def _tokens(name: str) -> set[str]:
    folded = _fold(name.lower())
    raw = re.split(r"[^a-z0-9]+", folded)
    return {t for t in raw if t and t not in _CLUB_STOPWORDS and len(t) >= 3}


def _names_match(openliga_name: str, kicktipp_name: str) -> bool:
    a, b = _tokens(openliga_name), _tokens(kicktipp_name)
    if not a or not b:
        return False
    return bool(a & b)


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
    falls das (z.B. wegen eines Overlays) haengen bleibt, erzwungen klicken.
    Letzter Fallback: natives JS-.click() direkt auf dem Element -- das
    triggert den Click-Handler unabhaengig von Bildschirmkoordinaten und
    umgeht damit ein Overlay, das einen koordinatenbasierten Klick (auch
    mit force=True) abfangen wuerde."""
    locator = page.locator(selector).first
    try:
        locator.scroll_into_view_if_needed(timeout=5000)
        locator.click(timeout=10000)
        return True
    except Exception:
        pass
    try:
        locator.click(timeout=5000, force=True)
        return True
    except Exception:
        pass
    try:
        locator.evaluate("el => el.click()")
        return True
    except Exception:
        return False


class KicktippSession:
    """Haelt eine eingeloggte Browser-Session auf der Tippabgabe-Seite offen,
    damit Lesen (bereits vorhandene Tipps) und Schreiben in einem Lauf
    passieren koennen.

    Kicktipps Tippabgabe-Tabelle hat je Spielzeile die Spalten
    td.col0 (Anpfiff), td.col1 (Heimteam), td.col2 (Gastteam),
    td.col3 (die beiden Tipp-Eingabefelder)."""

    def __init__(self, group: str, username: str, password: str):
        self.group = group
        self.username = username
        self.password = password
        self._pw = None
        self._browser = None
        self.page = None
        self._rows: list[dict] = []

    def __enter__(self) -> "KicktippSession":
        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch()
        self.page = self._browser.new_page(viewport={"width": 1366, "height": 2200})
        # Ein natives confirm()/alert()-Dialog beim Absenden wuerde die
        # Seite blockieren; ohne Handler dismisst Playwright ihn automatisch
        # (= Abbruch), was wie ein wirkungsloser Klick aussieht. Immer
        # akzeptieren, damit ein etwaiger "Trotz unvollstaendiger Tipps
        # abschicken?"-Dialog die Submission nicht verhindert.
        self.page.on("dialog", lambda dialog: dialog.accept())

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
        self._load_rows()
        return self

    def _load_rows(self) -> None:
        """(Neu-)Aufbau von self._rows aus der aktuellen Tippabgabe-Seite."""
        all_trs = self.page.query_selector_all(
            "table.tippabgabe tr, form#tippabgabeForm tr"
        )
        if not all_trs:
            all_trs = self.page.query_selector_all("tr")

        self._rows = []
        for tr in all_trs:
            home_cell = tr.query_selector("td.col1")
            away_cell = tr.query_selector("td.col2")
            inputs = self._tip_inputs(tr)
            if home_cell and away_cell and len(inputs) >= 2:
                self._rows.append(
                    {
                        "element": tr,
                        "home_text": home_cell.inner_text().strip(),
                        "away_text": away_cell.inner_text().strip(),
                    }
                )

    def reload_rows(self) -> None:
        """Laedt die Tippabgabe-Seite neu und baut self._rows neu auf --
        genutzt, um nach dem Absenden zu verifizieren, dass Werte wirklich
        gespeichert wurden."""
        self.page.reload()
        _dismiss_cookie_banner(self.page)
        self.page.wait_for_load_state("networkidle")
        self._load_rows()

    def __exit__(self, *exc):
        if self._browser:
            self._browser.close()
        if self._pw:
            self._pw.stop()

    def find_row(self, home_team: str, away_team: str):
        for row in self._rows:
            if _names_match(home_team, row["home_text"]) and _names_match(
                away_team, row["away_text"]
            ):
                return row["element"]
        return None

    @staticmethod
    def _tip_inputs(row):
        return row.query_selector_all('input[type="text"], input[type="number"]')

    def read_tip(self, row) -> tuple[str, str] | None:
        """Liest vorhandene Werte; leere Strings bedeuten unausgefuellt."""
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

    def submit_form(self) -> tuple[bool, str]:
        """Klickt den Speichern-Button und beobachtet dabei die tatsaechliche
        Netzwerkantwort, um zweifelsfrei zu sehen, ob (und wie) der Server
        auf den Klick reagiert hat."""
        # Andere (von uns nicht ausgefuellte) Tipp-Felder im selben Formular
        # koennen ein "required"-Attribut haben. Dann bricht der Browser die
        # native HTML5-Validierung beim Klick STILL ab -- kein Request, kein
        # Fehler in Playwright. Entfernen, bevor abgeschickt wird.
        try:
            self.page.evaluate(
                "document.querySelectorAll('input[required]')"
                ".forEach(el => el.removeAttribute('required'))"
            )
        except Exception:
            pass

        specific = (
            'form#tippabgabeForm button[type="submit"], '
            'form#tippabgabeForm input[type="submit"], '
            'table.tippabgabe button[type="submit"]'
        )

        def do_click() -> bool:
            if _click(self.page, specific):
                return True
            return _click(self.page, 'button[type="submit"], input[type="submit"]')

        try:
            with self.page.expect_response(
                lambda r: r.request.method == "POST", timeout=8000
            ) as resp_info:
                if not do_click():
                    return False, "Submit-Button konnte nicht geklickt werden."
            resp = resp_info.value
            info = f"POST {resp.url} -> Status {resp.status}"
        except Exception as exc:
            info = f"Kein POST nach dem Klick beobachtet (evtl. AJAX ohne Navigation): {exc}"

        self.page.wait_for_load_state("networkidle")
        return True, info

    def debug_buttons(self, limit: int = 25) -> list[str]:
        """Liefert alle Button-/Submit-artigen Elemente auf der Seite --
        nur zur Fehlersuche, wenn verify_saved ein Speichern-Problem meldet."""
        elements = self.page.query_selector_all(
            "button, input[type='submit'], input[type='button'], a.btn"
        )
        out = []
        for el in elements[:limit]:
            try:
                out.append(el.evaluate("el => el.outerHTML")[:250])
            except Exception:
                continue
        return out

    def verify_saved(self, tips: list[dict]) -> list[str]:
        """Laedt die Seite neu und prueft, ob die uebergebenen Tipps
        tatsaechlich gespeichert wurden (nicht nur im Formular ausgefuellt)."""
        self.reload_rows()
        problems = []
        for tip in tips:
            row = self.find_row(tip["home_team"], tip["away_team"])
            if row is None:
                problems.append(
                    f"Konnte Speichern nicht verifizieren (Zeile verschwunden): "
                    f"{tip['home_team']} - {tip['away_team']}"
                )
                continue
            saved = self.read_tip(row)
            expected = (str(tip["home_goals"]), str(tip["away_goals"]))
            if saved != expected:
                problems.append(
                    f"WARNUNG: Tipp wurde NICHT gespeichert (Seite zeigt "
                    f"{saved} statt {expected}): {tip['home_team']} - {tip['away_team']}"
                )
        return problems


def submit_tips(group: str, username: str, password: str, tips: list[dict]) -> list[str]:
    """Setzt alle uebergebenen Tipps (ueberschreibt vorhandene Werte).
    Fuer den manuellen UI-Flow, bei dem der Nutzer die Werte explizit bestaetigt hat.
    """
    messages: list[str] = []
    filled_tips = []
    with KicktippSession(group, username, password) as session:
        for tip in tips:
            row = session.find_row(tip["home_team"], tip["away_team"])
            if row is None:
                messages.append(
                    f"Wird von dieser Kicktipp-Gruppe nicht getippt, ueberspringe: "
                    f"{tip['home_team']} - {tip['away_team']}"
                )
                continue
            if not session.fill_tip(row, tip["home_goals"], tip["away_goals"]):
                messages.append(
                    f"Keine Tipp-Eingabefelder gefunden fuer: "
                    f"{tip['home_team']} - {tip['away_team']}"
                )
                continue
            filled_tips.append(tip)
            messages.append(
                f"Tipp gesetzt: {tip['home_team']} {tip['home_goals']}:"
                f"{tip['away_goals']} {tip['away_team']}"
            )

        ok, info = session.submit_form()
        if ok:
            messages.append(f"Tipps abgeschickt. ({info})")
            messages.extend(session.verify_saved(filled_tips))
        else:
            messages.append(f"WARNUNG: Absenden-Button nicht gefunden, Tipps evtl. nicht gespeichert. ({info})")

    return messages


def submit_missing_tips(group: str, username: str, password: str, candidate_tips: list[dict]) -> list[str]:
    """Backup-Modus: setzt nur Tipps fuer Spiele, die auf Kicktipp noch leer sind.
    Bereits (z.B. manuell per UI) gesetzte Tipps werden nicht ueberschrieben."""
    messages: list[str] = []
    filled_tips = []
    with KicktippSession(group, username, password) as session:
        for tip in candidate_tips:
            row = session.find_row(tip["home_team"], tip["away_team"])
            if row is None:
                messages.append(
                    f"Wird von dieser Kicktipp-Gruppe nicht getippt, ueberspringe: "
                    f"{tip['home_team']} - {tip['away_team']}"
                )
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
                filled_tips.append(tip)
                messages.append(
                    f"Backup-Tipp gesetzt: {tip['home_team']} {tip['home_goals']}:"
                    f"{tip['away_goals']} {tip['away_team']}"
                )

        if filled_tips:
            ok, info = session.submit_form()
            if ok:
                messages.append(f"Backup-Tipps abgeschickt. ({info})")
                problems = session.verify_saved(filled_tips)
                messages.extend(problems)
                if problems:
                    messages.append("DEBUG Button-/Submit-Elemente auf der Seite:")
                    messages.extend(f"  DEBUG-BTN: {b}" for b in session.debug_buttons())
            else:
                messages.append(f"WARNUNG: Absenden-Button nicht gefunden, Tipps evtl. nicht gespeichert. ({info})")
        else:
            messages.append("Nichts zu tun: alle Spiele bereits getippt.")

    return messages
