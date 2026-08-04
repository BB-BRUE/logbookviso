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
  - ./data:/data
```

Die Datenbank liegt unter `data/logbook.sqlite`. Uploads: `data/photos/` und `data/photos.sqlite`.

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
- **Foto-Upload** pro Törn mit GPS (EXIF oder manuell), Cluster-Marker auf der Karte

### Fotos hochladen

Speicherort (Docker-Volume `./data`):

| Pfad | Inhalt |
| --- | --- |
| `data/photos/<toern>/` | Bilddateien |
| `data/photos.sqlite` | Metadaten (Koordinaten, Törn, Dateiname) |

In der Sidebar: Dateien wählen → **Hochladen** (aktuell gewählter Törn).

Koordinaten:

1. **EXIF-GPS** im Bild (empfohlen), oder
2. **LAT/LON** im Formular (für alle Dateien des Uploads), oder
3. **Track-Zeit**: Aufnahmezeit aus EXIF → nächster Track-Punkt desselben Törns

Marker in der Nähe werden gebündelt (~250 m). Bilder werden nicht in `logbook.sqlite` gespeichert.

Upload-Limit pro Anfrage: **256 MB** (Umgebungsvariable `MAX_UPLOAD_MB`). Hinter SWAG/Nginx ggf. `client_max_body_size` anpassen (siehe `swag/logbookviso.subdomain.conf`).
