# Depot-Tracker für Planspiel Börse

Berechnet alle ca. 5 Minuten den Wert deines Depots aus Live-Kursen und zeigt den kompletten Verlauf als Graph auf GitHub Pages. Von überall abrufbar, am Handy genauso wie am PC.

Das ist ein **Nachbau** mit eigenen Kursquellen (Yahoo Finance). Die Werte weichen leicht von Planspiel Börse ab (andere Kurse, Spreads, Gebühren). Es wird nichts bei Planspiel Börse ausgelesen oder eingeloggt.

## Einrichten (einmalig, ca. 5 Minuten)

1. Auf GitHub ein neues Repository anlegen, z. B. `depot-tracker` (public, sonst braucht Pages einen Bezahlplan).
2. Den Inhalt dieses Ordners hochladen (inklusive des versteckten Ordners `.github`).
3. Im Repo: **Settings → Pages → Source: Deploy from a branch → Branch `main`, Ordner `/ (root)`** → Save.
4. Im Repo: **Settings → Actions → General → Workflow permissions → Read and write permissions** → Save.
5. Im Repo: **Actions → „Depot tracken" → Run workflow**, um den ersten Messpunkt zu erzeugen.
6. Deine Seite: `https://<dein-github-name>.github.io/depot-tracker/`

## Depot eintragen

`portfolio.json` anpassen:

```json
{
  "cash": 20000.00,
  "start_value": 50000.00,
  "positions": [
    { "symbol": "SAP.DE", "name": "SAP", "shares": 50, "currency": "EUR" },
    { "symbol": "AAPL",   "name": "Apple", "shares": 30, "currency": "USD" }
  ]
}
```

- `cash`: dein aktueller Kontostand (freies Geld)
- `start_value`: Startkapital, für die Linie „Seit Start" im Graphen
- `symbol`: Yahoo-Finance-Symbol (deutsche Aktien enden auf `.DE`, z. B. `SIE.DE`; US-Aktien ohne Endung)
- `currency`: `EUR` oder `USD` (USD wird per EUR/USD-Kurs umgerechnet)

Nach jedem Kauf/Verkauf `portfolio.json` aktualisieren (direkt auf GitHub im Browser bearbeiten reicht). Ein Commit löst sofort einen neuen Messpunkt aus.

## Wichtig zu wissen

- **Takt:** GitHub-Cron läuft im Idealfall alle 5 Minuten, ist aber oft um einige Minuten verspätet. Kleiner geht es dort nicht. Für echte Sekundendaten bräuchtest du einen eigenen Server oder Raspberry Pi mit `python tracker.py` per Cronjob.
- **Zeiten:** Läuft Mo–Fr 07:00–21:00 UTC (09:00–23:00 Sommerzeit). Außerhalb der Börsenzeiten ändert sich der Wert nicht, es wird dann nichts gespeichert.
- **Verlauf beginnt erst ab dem ersten Lauf.** Rückwirkend wird nichts berechnet.
- **Lokal testen:** `pip install -r requirements.txt && python tracker.py`, dann `python -m http.server` und `http://localhost:8000` öffnen.
- Bei einem privaten Depot-Wert bedenke: Eine öffentliche Pages-Seite ist für jeden mit Link sichtbar.
