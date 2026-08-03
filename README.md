# Logbook Viso

Interaktive Karte für Segel-/Motorboot-Logbuch-Tracks aus `logbook.sqlite`.

## Lokal starten

```bash
pip install -r requirements.txt
python server.py
```

Dann im Browser: [http://127.0.0.1:5000](http://127.0.0.1:5000)

## Docker

Die SQLite-Datei wird per Volume gemountet und liegt **nicht** im Image.

```bash
docker compose up --build
```

App: [http://127.0.0.1:5000](http://127.0.0.1:5000)

Volume-Mapping in `docker-compose.yml`:

```yaml
volumes:
  - ./logbook.sqlite:/data/logbook.sqlite:ro
```

Andere DB-Datei z. B. so:

```bash
docker compose run --rm -p 5000:5000 \
  -v /pfad/zu/meiner.sqlite:/data/logbook.sqlite:ro \
  logbookviso
```

Oder direkt mit Docker:

```bash
docker build -t logbookviso .
docker run --rm -p 5000:5000 \
  -e LOGBOOK_DB=/data/logbook.sqlite \
  -v "%CD%\logbook.sqlite:/data/logbook.sqlite:ro" \
  logbookviso
```

## Funktionen

- Zoom und Verschieben der Karte (Leaflet / OpenStreetMap)
- Törn-Auswahl (Filter über Spalte `toern`)
- Track als farbige Linie + Punkte
- Hover-Popup mit Time, COG, LAT, LON, SOG, M/H, LOG, GEO, Freitext und Wetterdaten
- `recordtype = 1` → größere Punkte (manuelle Einträge)
- Status-Farben: 0 Segeln, 1 Festgemacht, 2 Motor, 3 Anker
