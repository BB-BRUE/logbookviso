# Code Review – Logbook Viso

Stand: Refactoring mit Paket `logbookviso/`, gemeinsames Frontend `common.js`, erweiterte Doku.

## Kurzfassung

| Bereich | Bewertung | Anmerkung |
|--------|-----------|-----------|
| Architektur | Gut | Klare Trennung: Flask-Routen, Stores (SQLite), statisches SPA-Frontend |
| Sicherheit | Solide | Session-Cookies, Törn-/Foto-Rechte, Admin-Gates; `SECRET_KEY` in Prod setzen |
| Wartbarkeit | Verbessert | Python-Paket + `config.py`; JS-Duplikate in `common.js` |
| Tests | Fehlend | Keine automatisierten Tests (manuell / Docker) |
| Skalierung | Single-Node | SQLite + lokale Dateien – passend für kleine Teams |

## Struktur (nach Refactoring)

```
logbookviso/          # Python-Paket (Domain + Persistenz)
  config.py           # ENV → Settings
  api_format.py       # Track/Törn JSON-Hilfen
  auth_helpers.py     # Session, Decorators, HTML-Redirects
  users_store.py      # Benutzer, Passwort-Hashes, user_toerns
  logbook_store.py    # toerns, log_points, Viso-Import
  photos_store.py     # photos-Tabelle, Upload, Cluster, EXIF/GPS
server.py             # Flask app (WSGI: server:app)
static/               # HTML + JS (kein Bundler)
  auth.js, common.js  # API + UI-Hilfen
  app.js              # Karte (Leaflet)
data/                 # Laufzeit (gitignored): system.sqlite, photos/, uploads
docs/                 # CODE_REVIEW.md, ARCHITECTURE.md
```

**Warum kein `src/` auf Root-Ebene?** Das Paket heißt `logbookviso/` (Python-Konvention). `server.py` bleibt bewusst im Root für Gunicorn/Flask-CLI ohne Package-Install. Alternative wäre `pip install -e .` mit `pyproject.toml` – bei dieser Größe optional.

## Behobene Duplikate

### Frontend (vorher 4× identisch)

- `escapeHtml`, `showToast` → `static/common.js`
- Törn-Liste laden → `fetchToerns()`, `fillToernSelect(..., "map"|"manage")`
- Admin-Guard → `requireAdminOrRedirect()`

### Backend

- HTML-Admin/Login-Checks → `redirect_if_not_logged_in`, `redirect_if_not_admin`
- `parse_revier`, `fmt_time`, `clean_num`, `STATUS_LABELS` → `api_format.py`
- Konfiguration → `config.Settings`
- `created_at_ms` nach PATCH → `photos_store.photo_created_at_ms()` statt ad-hoc SQL in `server.py`

## Verbleibende bewusste Wiederholungen

- **Leaflet-Karte** nur in `app.js` (seiten-spezifisch).
- **Admin-Törn-Checkboxen** in `admin.js` vs. Logbook-Pickliste in `logbook-import.js` (unterschiedliches Markup/ Datenquelle).
- **Thumbnail-Erzeugung** inline in `server.py` (Pillow) – Auslagern in `photos_store` wäre möglich, aber stärker an Flask gekoppelt.

## Empfehlungen (optional, nicht umgesetzt)

1. **Tests:** pytest für `logbook_store.validate_logbook_file`, `photos_store.photo_has_coordinates`, Auth-Decorators.
2. **API-Doku:** OpenAPI aus Routen oder kleines `docs/API.md`.
3. **server.py aufteilen:** Blueprints `auth`, `photos`, `admin` wenn Routen weiter wachsen.
4. **login.js:** `auth.js` einbinden und `apiFetch` nutzen (Login-Seite hat bewusst keinen 401-Redirect während Login).
5. **Type hints** in Stores durchgängig für öffentliche Funktionen.

## Sicherheitshinweise

- Default-Passwort `admin`/`admin` nur für Erststart – in Produktion sofort ändern.
- Upload-Größe: Flask `MAX_CONTENT_LENGTH` + Reverse-Proxy `client_max_body_size`.
- Keine Secrets in Git; `data/` und echte SQLite nicht committen.

## Checkliste nach Deploy

- [ ] `SECRET_KEY` gesetzt
- [ ] `SESSION_COOKIE_SECURE=1` gesetzt (nur bei HTTPS-Erreichbarkeit, z. B. hinter SWAG)
- [ ] Admin-Passwort geändert
- [ ] Volume `./data` persistent
- [ ] SWAG/Nginx Upload-Limit ≥ 256 MB (falls große Videos)
