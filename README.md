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
  - ./data:/data:ro
```

Die Datenbank liegt unter `data/logbook.sqlite` (nicht als einzelne Datei mounten – Docker legt sonst leicht einen Ordner an).

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

### SWAG Reverse Proxy

Configs unter `swag/`:

| Datei | URL |
| --- | --- |
| `logbookviso.subdomain.conf` | `https://logbookviso.deinedomain.tld` |
| `logbookviso.subfolder.conf` | `https://deinedomain.tld/logbookviso/` |

1. Gewünschte Conf nach SWAG kopieren: `/config/nginx/proxy-confs/`
2. DNS für Subdomain setzen (bei Subdomain-Variante)
3. Container und SWAG im gleichen Docker-Netz (`proxy` in `docker-compose.yml`, ggf. anpassen)
4. SWAG neu starten

```bash
# Netz anlegen, falls noch nicht vorhanden
docker network create proxy
```

## Funktionen

- Zoom und Verschieben der Karte (Leaflet / OpenStreetMap)
- Törn-Auswahl (Filter über Spalte `toern`)
- Track als farbige Linie + Punkte
- Hover-Popup mit Time, COG, LAT, LON, SOG, M/H, LOG, GEO, Freitext und Wetterdaten
- `recordtype = 1` → größere Punkte (manuelle Einträge)
- Status-Farben: 0 Segeln, 1 Festgemacht, 2 Motor, 3 Anker
- **Google Fotos:** öffentliche Teilen-Links pro Törn, Marker mit Galerie (ohne Bilder aus SQLite)

### Google Fotos (Teilen-Link)

Öffentliche Google-Photos-Alben (`photos.app.goo.gl/…` oder `photos.google.com/share/…`) werden serverseitig eingelesen. **GPS-Koordinaten stehen in Teilen-Links nicht zuverlässig zur Verfügung** – die App setzt die Bilder daher per **Aufnahmezeit** dem nächsten Track-Punkt desselben Törns zu (nur Zeit/Koordinaten aus dem Logbuch, keine `bilddata` aus SQLite). Fotos in der Nähe werden unter **einem Marker** gebündelt (`clusterRadiusMeters`).

1. Vorlage kopieren:

```bash
cp data/google-photos.json.example data/google-photos.json
```

2. Pro Törn Album-Links eintragen (`toern`-ID wie in der Datenbank):

```json
{
  "clusterRadiusMeters": 250,
  "toerns": {
    "0": {
      "albums": ["https://photos.app.goo.gl/DEIN_LINK"]
    }
  }
}
```

3. Optional: Einzelbilder mit **festen Koordinaten** (`manualPhotos`), wenn kein Zeitstempel passt.

4. Container neu starten bzw. Seite neu laden. Auf der Karte: gelbe Marker mit Anzahl → Klick öffnet Galerie.

Cache (Album-Inhalte): standardmäßig `/tmp/photos-cache` im Container (Schreibzugriff, da `./data` read-only gemountet ist).
