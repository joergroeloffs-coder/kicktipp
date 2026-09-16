# kicktipp

Automatischer Tippagent fuer Bundesliga (1. + 2.) Ergebnisse.

## Was es tut

Jede Woche (Cron: freitags 13:00 UTC, siehe `.github/workflows/weekly-tips.yml`):

1. Holt anstehende Spiele der naechsten Tage von [OpenLigaDB](https://api.openligadb.de) (1. + 2. Bundesliga).
2. Berechnet einen Tipp je Spiel aus der Torform der letzten 5 Spiele beider Teams (`src/predictor.py`).
3. Loggt sich per Browser-Automation (Playwright) bei Kicktipp ein und traegt die Tipps auf der Tippabgabe-Seite ein.

## Setup

1. In den GitHub-Repo-Settings unter **Secrets and variables > Actions** anlegen:
   - `KICKTIPP_GROUP` – der Community-Name aus deiner Kicktipp-URL (`kicktipp.de/DEIN-GRUPPENNAME`)
   - `KICKTIPP_USERNAME` – dein Kicktipp-Login (E-Mail)
   - `KICKTIPP_PASSWORD` – dein Kicktipp-Passwort
2. Workflow laeuft automatisch freitags, oder manuell ueber "Run workflow" (Tab *Actions*) testen.

## Lokal testen

```bash
pip install -r requirements.txt
playwright install chromium

export KICKTIPP_GROUP=deine-gruppe
export KICKTIPP_USERNAME=deine@email.de
export KICKTIPP_PASSWORD=deinpasswort
python main.py
```

## Bekannte Einschraenkungen

- Kicktipp hat keine offizielle API; die Formularstruktur der Tippabgabe-Seite wird per Textabgleich
  der Mannschaftsnamen erkannt. Aendert Kicktipp sein Seitenlayout, muss `src/kicktipp_client.py`
  angepasst werden.
- Die Tipp-Heuristik ist bewusst einfach (Torform-Durchschnitt + Heimvorteil), kein ML-Modell.
