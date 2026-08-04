# Logbook Viso

Interaktive Karte für Segel-/Motorboot-Logbuch-Tracks. **Alle App-Daten** (Törns, Track-Punkte, Fotos, Benutzer) liegen in **`data/system.sqlite`** (`SYSTEM_DB`); Bilddateien unter `data/photos/`.

## Lokal starten

```bash
pip install -r requirements.txt
python server.py
```

Dann im Browser: [http://127.0.0.1:5000](http://127.0.0.1:5000)

## Docker

Persistente Daten nur im Volume `./data` (nicht im Image).

```bash
docker compose up --build
```

App: [http://127.0.0.1:5000](http://127.0.0.1:5000)

```yaml
volumes:
  - ./data:/data
```

| Pfad | Inhalt |
| --- | --- |
| `data/system.sqlite` | Törns, Track-Punkte, Fotos-Metadaten, Benutzer |
| `data/photos/<törn-id>/` | Bilddateien |
| `data/logbook_uploads/` | temporäre Logbook-Uploads (Admin) |

## Logbook importieren (Admin)

Es gibt **kein** fest gemountetes `logbook.sqlite` mehr.

1. Als Admin anmelden → [http://127.0.0.1:5000/admin/logbook](http://127.0.0.1:5000/admin/logbook)
2. Viso-**logbook.sqlite** hochladen (temporär)
3. Törns auswählen → **In App-Datenbank übernehmen**
4. Danach Törns auf der Karte sichtbar; unter `/admin` Usern zuordnen

Erneuter Import **ersetzt** Track-Daten für die gewählten Törn-IDs. Die Upload-Datei wird nach erfolgreichem Import gelöscht.

## Anmeldung & Benutzer

Alle Seiten außer `/login` erfordern eine Anmeldung. Beim **ersten Start** (leere Benutzertabelle) wird ein Admin angelegt:

| Umgebungsvariable | Standard |
| --- | --- |
| `INIT_ADMIN_USER` | `admin` |
| `INIT_ADMIN_PASSWORD` | `admin` |
| `SECRET_KEY` | `dev-change-me-in-production` (Session-Cookies; in Produktion setzen!) |
| `SYSTEM_DB` | `data/system.sqlite` |

- **Admin:** `/admin` (Benutzer), `/admin/logbook` (Logbook-Import)
- **User** sehen nur zugeordnete Törns (Karte, Track, Fotos).
- **Foto-Bearbeitung/Löschen:** Uploader oder Admin.

### SWAG Reverse Proxy

Configs unter `swag/`:

| Datei | URL |
| --- | --- |
| `logbookviso.subdomain.conf` | `https://logbookviso.deinedomain.tld` |
| `logbookviso.subfolder.conf` | `https://deinedomain.tld/logbookviso/` |

1. Gewünschte Conf nach SWAG kopieren: `/config/nginx/proxy-confs/`
2. DNS für Subdomain setzen (bei Subdomain-Variante)
3. Container und SWAG im gleichen Docker-Netz (`swag_proxy-net` in `docker-compose.yml`, ggf. anpassen)
4. SWAG neu starten

## Funktionen

- Zoom und Verschieben der Karte (Leaflet / OpenStreetMap)
- Törn-Auswahl aus importierten Törns
- Track als farbige Linie + Punkte
- Hover-Popup mit Time, COG, LAT, LON, SOG, M/H, LOG, GEO, Freitext und Wetterdaten
- `recordtype = 1` → größere Punkte (manuelle Einträge)
- Status-Farben: 0 Segeln, 1 Festgemacht, 2 Motor, 3 Anker
- **Medien-Upload** pro Törn (Bilder + MP4/MOV) mit GPS aus Metadaten oder manuell, Cluster-Marker auf der Karte

### Fotos

**Verwaltung:** [http://127.0.0.1:5000/photos](http://127.0.0.1:5000/photos) – Upload, Metadaten bearbeiten, Ordner einlesen.

Koordinaten: EXIF-GPS (Bilder), QuickTime-GPS in MP4/MOV (Smartphone-Videos), manuelles LAT/LON, oder Track-Zeit-Matching.

Upload-Limit: **256 MB** (`MAX_UPLOAD_MB`). Hinter SWAG/Nginx `client_max_body_size` anpassen (siehe `swag/logbookviso.subdomain.conf`).
