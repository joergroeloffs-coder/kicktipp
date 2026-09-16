# kicktipp

Automatischer Tippagent fuer Bundesliga (1./2./3. Liga) Ergebnisse.

## Wie es funktioniert

Die Spieleliste kommt IMMER direkt von Kicktipps eigener Tippabgabe-Seite
(nicht aus einer selbst erratenen OpenLigaDB-Auswahl) -- so werden garantiert
genau die Spiele getippt, die diese Kicktipp-Gruppe tatsaechlich anbietet,
egal aus welcher Liga.

1. **Manuell:** Lokale Web-Oberflaeche starten, alle auf Kicktipp offenen
   Spiele mit Formanalyse und Tippvorschlag ansehen, bei Bedarf anpassen,
   per Knopfdruck an Kicktipp senden.
2. **Automatisch (taeglich):** Ein GitHub-Actions-Job laeuft einmal pro Tag,
   berechnet ALLE Spiele auf Kicktipps Tippabgabe-Seite neu (Form, Tabelle,
   Quoten koennen sich seit dem letzten Lauf geaendert haben) und
   - fuellt noch leere Felder,
   - **korrigiert bereits gesetzte Tipps**, wenn die Neuberechnung ein
     anderes Ergebnis fuer wahrscheinlicher haelt,
   - fasst Spiele, deren Anpfiff vorbei ist (von Kicktipp gesperrte Felder),
     nie an.

Datenquelle fuer Formwerte: [OpenLigaDB](https://api.openligadb.de)
(1./2./3. Liga). Tippberechnung kombiniert mehrere Signale (`src/predictor.py`):
Torform der letzten 6 Spiele getrennt nach Heim-/Auswaertsspielen, aktuelle
Ligatabelle (Punkte/Tordifferenz pro Spiel), direkter Vergleich der letzten
Duelle und die von Kicktipp selbst mitgelieferten Buchmacher-Quoten (staerkstes
Gewicht) — eine Heuristik, kein ML-Modell. Der Abgleich zwischen OpenLigaDBs
vollen Vereinsnamen und Kicktipps oft abgekuerzten Anzeigenamen laeuft ueber
einen Token-Vergleich (`src/teamnames.py`).

## Setup

```bash
pip install -r requirements.txt
playwright install chromium
cp .env.example .env   # Werte eintragen
```

Fuer den taeglichen Workflow zusaetzlich in den GitHub-Repo-Settings unter
**Secrets and variables > Actions** anlegen:
- `KICKTIPP_GROUP` – Community-Name aus der Kicktipp-URL (`kicktipp.de/DEIN-GRUPPENNAME`)
- `KICKTIPP_USERNAME` – Kicktipp-Login (E-Mail)
- `KICKTIPP_PASSWORD` – Kicktipp-Passwort

## Manuelle Oberflaeche starten

```bash
python app.py
```

Dann `http://localhost:5000` im Browser oeffnen. Zeigt alle auf Kicktipp
offenen Spiele mit Formwerten und Tippvorschlag, Werte sind editierbar.
"Tipps an Kicktipp senden" loggt sich per Browser-Automation ein und setzt die
Tipps auf der Tippabgabe-Seite.

## Taeglicher Workflow

Laeuft automatisch per Cron (`.github/workflows/weekly-tips.yml`, taeglich
06:00 UTC), oder manuell testen ueber den *Actions*-Tab ("Run workflow").
Berechnet jedes Spiel auf der Tippabgabe-Seite neu und gleicht ab: leere
Felder werden gefuellt, abweichende bereits gesetzte Tipps korrigiert,
gesperrte (nach Anpfiff) Felder bleiben unangetastet.

## Bekannte Einschraenkungen

- Kicktipp hat keine offizielle API; die Formularstruktur der Tippabgabe-Seite
  wird per Textabgleich der Mannschaftsnamen erkannt. Aendert Kicktipp sein
  Seitenlayout, muss `src/kicktipp_client.py` angepasst werden.
- Die lokale UI ist fuer lokalen Betrieb gedacht (kein Login/Auth). Bei Bedarf
  spaeter hinter einem eigenen Host mit Zugriffsschutz betreiben.
