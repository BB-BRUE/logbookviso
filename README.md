# Logbook Viso

Interaktive Karte für Segel-/Motorboot-Logbuch-Tracks (Viso-Export). **Alle App-Daten** (Törns, Track-Punkte, Medien-Metadaten, Benutzer) liegen in **`data/system.sqlite`** (`SYSTEM_DB`); Bild- und Videodateien unter `data/photos/`.

Weitere Doku:

- [Architektur & Datenfluss](docs/ARCHITECTURE.md)
- [Code Review & Refactoring-Notizen](docs/CODE_REVIEW.md)

## Projektstruktur

```
logbookviso/       Python-Paket (Stores, Auth, Config)
server.py          Flask-App, WSGI-Einstieg (gunicorn server:app)
static/            Frontend (HTML/CSS/JS, ohne Build-Schritt)
data/              Laufzeitdaten (nicht im Repo)
docs/              Architektur & Review
swag/              Beispiel-Nginx-Configs für SWAG
```

## Voraussetzungen

- Python 3.12+
- Optional: Docker & Docker Compose

## Lokal starten

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # Linux/macOS
pip install -r requirements.txt
python server.py
```

Alternativ mit Flask CLI (Debug):

```bash
set FLASK_APP=server.py
set FLASK_DEBUG=1
python -m flask run
```

VS Code: Konfiguration **Python Debugger: Flask** in `.vscode/launch.json` (setzt `PYTHONPATH` auf das Projektroot).

Browser: [http://127.0.0.1:5000](http://127.0.0.1:5000)

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
| `data/photos/<törn-id>/` | Medien-Dateien |
| `data/logbook_uploads/` | temporäre Logbook-Uploads (Admin) |

## Umgebungsvariablen

| Variable | Standard | Bedeutung |
| --- | --- | --- |
| `SYSTEM_DB` | `data/system.sqlite` | Zentrale SQLite-Datei |
| `PHOTOS_DIR` | `data/photos` | Medien auf dem Dateisystem |
| `LOGBOOK_UPLOAD_DIR` | `<DB-Ordner>/logbook_uploads` | Temporäre Viso-Uploads |
| `MAX_UPLOAD_MB` | `256` | Max. Request-Größe (Upload) |
| `SECRET_KEY` | `dev-change-me-in-production` | Flask-Session (in Produktion setzen!) |
| `INIT_ADMIN_USER` | `admin` | Erster Admin, wenn keine User existieren |
| `INIT_ADMIN_PASSWORD` | `admin` | Passwort für Bootstrap-Admin |
| `HOST` / `PORT` | `127.0.0.1` / `5000` | Nur für `python server.py` |

Definition im Code: `logbookviso/config.py`.

## Logbook importieren (Admin)

Es gibt **kein** fest gemountetes `logbook.sqlite` mehr.

1. Als Admin anmelden → [http://127.0.0.1:5000/admin/logbook](http://127.0.0.1:5000/admin/logbook)
2. Viso-**logbook.sqlite** hochladen (temporär)
3. Törns auswählen → **In App-Datenbank übernehmen**
4. Danach Törns auf der Karte sichtbar; unter `/admin` Usern zuordnen

Erneuter Import **ersetzt** Track-Daten für die gewählten Törn-IDs. Die Upload-Datei wird nach erfolgreichem Import gelöscht.

## Anmeldung & Benutzer

Alle Seiten außer `/login` erfordern eine Anmeldung. Beim **ersten Start** (leere Benutzertabelle) wird ein Admin angelegt (`INIT_ADMIN_*`).

- **Admin:** `/admin` (Benutzer), `/admin/logbook` (Logbook-Import)
- **User** sehen nur zugeordnete Törns (Karte, Track, Fotos).
- **Foto-Bearbeitung/Löschen:** Uploader oder Admin.

## HTTP-API (Überblick)

Alle `/api/*`-Routen (außer Login) erwarten eine gültige Session.

| Methode | Pfad | Beschreibung |
| --- | --- | --- |
| POST | `/api/auth/login`, `/api/auth/logout` | Anmeldung |
| GET | `/api/auth/me` | Aktueller User |
| GET | `/api/toerns` | Törn-Liste (gefiltert nach Rechten) |
| GET | `/api/track/<id>` | Track-Punkte |
| GET/POST | `/api/photos/...` | Karte, Upload, Import, CRUD |
| GET/POST/PATCH/DELETE | `/api/admin/users` | Benutzerverwaltung |
| POST/GET | `/api/admin/logbook/...` | Upload, Preview, Import |

Details siehe Routen in `server.py`.

## Funktionen (UI)

- Leaflet-Karte, einklappbare Sidebar (Smartphone: Menü standardmäßig zu)
- Törn-Auswahl, Track-Linie, Status-Farben, Hover-Popup
- Medien mit/ohne GPS, Diashow, Cluster auf der Karte
- Fotoverwaltung unter `/photos`

### Medien & GPS

Koordinaten: EXIF (Bilder), QuickTime-GPS in MP4/MOV, manuelles LAT/LON, oder Matching zur Track-Zeit.

Upload-Limit: **256 MB** (`MAX_UPLOAD_MB`). Hinter SWAG/Nginx `client_max_body_size` anpassen (siehe `swag/logbookviso.subdomain.conf`).

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

## Entwicklungshinweise

- Nach Änderungen an `static/` ggf. Hard-Refresh (Flask `--no-reload` im Debugger).
- Keine Migrations-History: Schema wird bei Start angelegt (`init_system_db`, `init_logbook_schema`, `init_app_db`).
- Gemeinsame JS-Helfer: `static/common.js` (Toast, Törn-Select, Admin-Check).

## Lizenz / Hinweis

Privates Logbuch-Tool; Viso-Export-Format und Tabellen `Toernrecord` / `Logrecord` stammen aus dem Viso-Ökosystem.
