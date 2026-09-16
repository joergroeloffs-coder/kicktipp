# kicktipp

Automatischer Tippagent fuer Bundesliga (1. + 2.) Ergebnisse.

## Wie es funktioniert

1. **Manuell (empfohlen):** Lokale Web-Oberflaeche starten, anstehende Spiele mit
   Formanalyse und Tippvorschlag ansehen, bei Bedarf anpassen, per Knopfdruck
   an Kicktipp senden.
2. **Backup:** Ein GitHub-Actions-Job laeuft freitags kurz vor dem fruehesten
   Anpfiff und traegt automatisch Tipps fuer alle Spiele ein, die bis dahin
   noch nicht getippt wurden (z.B. weil der manuelle Schritt vergessen wurde).
   Bereits gesetzte Tipps werden nicht ueberschrieben.

Datenquelle fuer Spielplaene/Ergebnisse: [OpenLigaDB](https://api.openligadb.de)
(1. + 2. Bundesliga). Tippberechnung: Torform der letzten 5 Spiele je Team plus
Heimvorteil-Faktor (`src/predictor.py`) — eine einfache Heuristik, kein ML-Modell.

## Setup

```bash
pip install -r requirements.txt
playwright install chromium
cp .env.example .env   # Werte eintragen
```

Fuer den Backup-Workflow zusaetzlich in den GitHub-Repo-Settings unter
**Secrets and variables > Actions** anlegen:
- `KICKTIPP_GROUP` – Community-Name aus der Kicktipp-URL (`kicktipp.de/DEIN-GRUPPENNAME`)
- `KICKTIPP_USERNAME` – Kicktipp-Login (E-Mail)
- `KICKTIPP_PASSWORD` – Kicktipp-Passwort

## Manuelle Oberflaeche starten

```bash
python app.py
```

Dann `http://localhost:5000` im Browser oeffnen. Zeigt anstehende Spiele
(1. + 2. Bundesliga) mit Formwerten und Tippvorschlag, Werte sind editierbar.
"Tipps an Kicktipp senden" loggt sich per Browser-Automation ein und setzt die
Tipps auf der Tippabgabe-Seite.

## Backup-Workflow

Laeuft automatisch per Cron (`.github/workflows/weekly-tips.yml`, freitags
18:00 UTC), oder manuell testen ueber den *Actions*-Tab ("Run workflow").
Prueft pro Spiel, ob auf Kicktipp bereits ein Tipp eingetragen ist — nur leere
Felder werden befuellt.

## Bekannte Einschraenkungen

- Kicktipp hat keine offizielle API; die Formularstruktur der Tippabgabe-Seite
  wird per Textabgleich der Mannschaftsnamen erkannt. Aendert Kicktipp sein
  Seitenlayout, muss `src/kicktipp_client.py` angepasst werden.
- Die lokale UI ist fuer lokalen Betrieb gedacht (kein Login/Auth). Bei Bedarf
  spaeter hinter einem eigenen Host mit Zugriffsschutz betreiben.
