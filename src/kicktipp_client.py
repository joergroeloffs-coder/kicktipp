"""Login bei Kicktipp und Setzen von Tipps per Browser-Automation.

Hinweis: Kicktipp bietet keine offizielle API. Die Formularstruktur der
Tippabgabe-Seite kann sich aendern -- falls das Setzen fehlschlaegt, zuerst
pruefen, ob sich die Feld-/Zeilenstruktur auf kicktipp.de geaendert hat.
"""
from __future__ import annotations

from playwright.sync_api import sync_playwright

from src.teamnames import names_match as _names_match

LOGIN_URL = "https://www.kicktipp.de/info/profil/login"


_COOKIE_BUTTON_TEXTS = [
    "Akzeptieren und weiter",
    "Alle akzeptieren",
    "Akzeptieren",
    "Einverstanden",
    "Zustimmen",
    "Accept all",
    "Accept",
]


def _dismiss_cookie_banner(page) -> bool:
    """Best-effort: schliesst Cookie-/Consent-Banner, falls vorhanden.
    Solche Overlays legen sich sonst sichtbar UEBER die Seite und fangen
    Klicks ab (auch erzwungene), obwohl das Zielelement scheinbar getroffen
    wird. Consent-Manager laufen ueblicherweise in einem iframe, daher wird
    ueber alle Frames der Seite gesucht, nicht nur das Hauptdokument.
    Die Seite hat typischerweise viele Werbe-/Tracking-Iframes ohne
    passenden Button -- .count() prueft schnell (ohne Warten), ob ein Text
    ueberhaupt vorkommt, bevor der eigentliche (wartende) Klick versucht
    wird; das verhindert, dass jeder Frame x jeder Text-Kandidat mit
    vollem Timeout durchlaufen wird. Gibt True zurueck, wenn tatsaechlich
    etwas geklickt wurde."""
    for frame in page.frames:
        for text in _COOKIE_BUTTON_TEXTS:
            try:
                button = frame.get_by_role("button", name=text, exact=False)
                if button.count() == 0:
                    continue
                button.first.click(timeout=1000)
                return True
            except Exception:
                continue
    return False


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
        self.page.wait_for_load_state("load")

        self.page.goto(f"https://www.kicktipp.de/{self.group}/tippabgabe")
        _dismiss_cookie_banner(self.page)
        self.page.wait_for_load_state("load")
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
                        "odds": self._read_odds(tr),
                    }
                )

    @staticmethod
    def _read_odds(tr) -> dict | None:
        """Liest die von Kicktipp mitgelieferten Buchmacher-Quoten (Sieg
        Heim/Remis/Sieg Gast) aus der Quoten-Spalte -- ein starkes, bereits
        vorhandenes Signal, das bisher ungenutzt blieb."""
        quote_cell = tr.query_selector("td.quoten") or tr.query_selector("td.col4")
        if not quote_cell:
            return None
        texts = quote_cell.query_selector_all(".quote-text")
        if len(texts) != 3:
            return None
        try:
            home, draw, away = (float(t.inner_text().strip().replace(",", ".")) for t in texts)
        except ValueError:
            return None
        return {"home": home, "draw": draw, "away": away}

    def reload_rows(self) -> None:
        """Laedt die Tippabgabe-Seite neu und baut self._rows neu auf --
        genutzt, um nach dem Absenden zu verifizieren, dass Werte wirklich
        gespeichert wurden."""
        self.page.reload()
        _dismiss_cookie_banner(self.page)
        self.page.wait_for_load_state("load")
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

    def list_all_matches(self) -> list[dict]:
        """Liefert alle von Kicktipp angezeigten Spiele mit ihrem aktuellen
        Tipp (falls schon gesetzt) -- fuer die Uebersicht in der manuellen UI."""
        result = []
        for row in self._rows:
            existing = self.read_tip(row["element"])
            home_existing, away_existing = existing if existing else ("", "")
            result.append(
                {
                    "home_team": row["home_text"],
                    "away_team": row["away_text"],
                    "existing_home_goals": home_existing or None,
                    "existing_away_goals": away_existing or None,
                    "odds": row["odds"],
                }
            )
        return result

    def is_locked(self, row) -> bool:
        """True, wenn die Tipp-Felder nicht mehr editierbar sind (Kicktipp
        sperrt sie bei Anpfiff) -- solche Spiele duerfen nicht mehr
        korrigiert werden."""
        inputs = self._tip_inputs(row)
        return len(inputs) < 2 or any(i.is_disabled() for i in inputs)

    def fill_tip(self, row, home_goals: int, away_goals: int) -> bool:
        inputs = self._tip_inputs(row)
        if len(inputs) < 2 or any(i.is_disabled() for i in inputs):
            return False
        inputs[0].fill(str(home_goals))
        inputs[1].fill(str(away_goals))
        return True

    def submit_form(self) -> tuple[bool, str]:
        """Klickt den Speichern-Button und beobachtet dabei die tatsaechliche
        Netzwerkantwort, um zweifelsfrei zu sehen, ob (und wie) der Server
        auf den Klick reagiert hat."""
        # Das Consent-/Werbe-Overlay kann zwischen dem initialen Laden und
        # dem Absenden erneut auftauchen und liegt sichtbar UEBER dem
        # Speichern-Button -- daher hier nochmal explizit pruefen/wegklicken.
        _dismiss_cookie_banner(self.page)

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

        self.page.wait_for_load_state("load")
        return True, info

    def screenshot(self, path: str) -> None:
        """Speichert einen Screenshot der aktuellen Seite -- nur zur
        visuellen Fehlersuche, wenn Logs allein nicht mehr aufschlussreich sind."""
        try:
            self.page.screenshot(path=path, full_page=True)
        except Exception:
            pass

    def screenshot_base64(self, max_chars: int = 180_000) -> str | None:
        """Liefert einen komprimierten Screenshot (JPEG) als Base64-String,
        gedacht zum Ausgeben in CI-Logs, wenn ein Artifact-Download nicht
        moeglich ist. Gibt None zurueck, wenn es fehlschlaegt oder zu gross ist."""
        import base64

        try:
            data = self.page.screenshot(type="jpeg", quality=40, full_page=False)
            encoded = base64.b64encode(data).decode("ascii")
            return encoded if len(encoded) <= max_chars else None
        except Exception:
            return None

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


def sync_tips(
    group: str,
    username: str,
    password: str,
    predict_fn,
    screenshot_dir: str | None = None,
) -> list[str]:
    """Taeglicher Abgleich: liest ALLE auf Kicktipp angezeigten Spiele
    direkt von der Seite -- offene wie bereits getippte -- und berechnet
    fuer jedes neu, was die Heuristik aktuell vorschlaegt.
    - Noch leere Felder werden gefuellt.
    - Bereits gesetzte Tipps werden UEBERSCHRIEBEN, wenn die Neuberechnung
      (neue Formdaten, Tabelle, Quoten) ein anderes Ergebnis liefert.
    - Spiele, deren Anpfiff vorbei ist (Felder von Kicktipp gesperrt),
      werden nie angefasst.
    predict_fn(home_team, away_team, odds) -> (home_goals, away_goals).
    screenshot_dir: wenn gesetzt, werden Screenshots vor/nach dem Absenden
    dorthin gespeichert -- nur zur visuellen Fehlersuche."""
    messages: list[str] = []
    changed_tips = []
    with KicktippSession(group, username, password) as session:
        matches = session.list_all_matches()
        if not matches:
            return ["Keine Spiele auf der Tippabgabe-Seite gefunden."]

        for match in matches:
            home_team, away_team = match["home_team"], match["away_team"]
            row = session.find_row(home_team, away_team)
            if row is None or session.is_locked(row):
                continue

            home_goals, away_goals = predict_fn(home_team, away_team, match["odds"])
            existing_home, existing_away = match["existing_home_goals"], match["existing_away_goals"]
            tip = {
                "home_team": home_team,
                "away_team": away_team,
                "home_goals": home_goals,
                "away_goals": away_goals,
            }

            if existing_home is None:
                if session.fill_tip(row, home_goals, away_goals):
                    changed_tips.append(tip)
                    messages.append(f"Tipp gesetzt: {home_team} {home_goals}:{away_goals} {away_team}")
            elif str(home_goals) != existing_home or str(away_goals) != existing_away:
                if session.fill_tip(row, home_goals, away_goals):
                    changed_tips.append(tip)
                    messages.append(
                        f"Tipp korrigiert: {home_team} {existing_home}:{existing_away} -> "
                        f"{home_goals}:{away_goals} {away_team}"
                    )

        if changed_tips:
            if screenshot_dir:
                session.screenshot(f"{screenshot_dir}/vor_absenden.png")
            ok, info = session.submit_form()
            if screenshot_dir:
                session.screenshot(f"{screenshot_dir}/nach_absenden.png")
            if ok:
                messages.append(f"Tipps abgeschickt. ({info})")
                problems = session.verify_saved(changed_tips)
                messages.extend(problems)
                if problems:
                    messages.append("DEBUG Button-/Submit-Elemente auf der Seite:")
                    messages.extend(f"  DEBUG-BTN: {b}" for b in session.debug_buttons())
                    if screenshot_dir:
                        session.screenshot(f"{screenshot_dir}/nach_verify.png")
                    b64 = session.screenshot_base64()
                    if b64:
                        messages.append("DEBUG-SCREENSHOT-B64-START")
                        messages.append(b64)
                        messages.append("DEBUG-SCREENSHOT-B64-END")
            else:
                messages.append(f"WARNUNG: Absenden-Button nicht gefunden, Tipps evtl. nicht gespeichert. ({info})")
        else:
            messages.append("Nichts zu tun: alle Tipps stimmen bereits mit der Neuberechnung ueberein.")

    return messages
