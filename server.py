"""Logbook track map – API + static frontend; App-Daten in system DB (SYSTEM_DB)."""

from __future__ import annotations

import json
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

from flask import Flask, jsonify, redirect, request, send_from_directory

from auth_helpers import (
    current_user,
    login_user,
    logout_user,
    require_admin_api,
    require_login_api,
    require_photo_edit,
    require_toern_access,
)
from logbook_store import (
    import_toerns_from_file,
    list_imported_toern_ids,
    list_toerns_in_logbook,
    list_toerns_summary,
    fetch_track_rows,
    track_timeline,
    validate_logbook_file,
)
from photos_store import (
    VIDEO_EXT,
    clusters_to_json,
    cluster_photos,
    delete_photo,
    get_photo,
    import_photos_from_folder,
    init_system_db,
    list_photos,
    list_photos_manage,
    photo_manage_dict,
    save_upload,
    update_photo,
)
from users_store import (
    ROLE_ADMIN,
    authenticate,
    can_edit_photo,
    create_user,
    delete_user,
    ensure_bootstrap_admin,
    list_users,
    update_user,
    user_to_public_dict,
    username_for_id,
)

ROOT = Path(__file__).resolve().parent
# Zentrale App-DB: Törns, Tracks, Fotos-Metadaten, Benutzer
SYSTEM_DB = Path(os.environ.get("SYSTEM_DB", str(ROOT / "data/system.sqlite")))
PHOTOS_DIR = Path(os.environ.get("PHOTOS_DIR", str(ROOT / "data/photos")))
LOGBOOK_UPLOAD_DIR = Path(
    os.environ.get("LOGBOOK_UPLOAD_DIR", str(SYSTEM_DB.parent / "logbook_uploads"))
)
STATIC = ROOT / "static"
MAX_UPLOAD_MB = int(os.environ.get("MAX_UPLOAD_MB", "256"))
SECRET_KEY = os.environ.get("SECRET_KEY", "dev-change-me-in-production")
INIT_ADMIN_USER = os.environ.get("INIT_ADMIN_USER", "admin")
INIT_ADMIN_PASSWORD = os.environ.get("INIT_ADMIN_PASSWORD", "admin")

STATUS_LABELS = {
    0: "Segeln",
    1: "Festgemacht",
    2: "Motor",
    3: "Anker",
}

app = Flask(__name__, static_folder=str(STATIC), static_url_path="")
app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_MB * 1024 * 1024
app.config["SECRET_KEY"] = SECRET_KEY
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

ensure_bootstrap_admin(SYSTEM_DB, INIT_ADMIN_USER, INIT_ADMIN_PASSWORD)
init_system_db(SYSTEM_DB)
LOGBOOK_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


@app.errorhandler(413)
def request_entity_too_large(_exc):
    return (
        jsonify(
            {
                "error": (
                    f"Upload zu groß (max. {MAX_UPLOAD_MB} MB pro Anfrage). "
                    "Weniger Dateien auf einmal oder MAX_UPLOAD_MB erhöhen."
                )
            }
        ),
        413,
    )


def parse_revier(raw: str | None) -> str:
    if not raw:
        return ""
    raw = raw.strip()
    if raw.startswith("{"):
        try:
            data = json.loads(raw)
            return str(data.get("jToernRevier") or "")
        except json.JSONDecodeError:
            return ""
    return raw


def fmt_time(ms: int | None) -> str | None:
    if ms is None:
        return None
    try:
        return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime(
            "%Y-%m-%d %H:%M:%S UTC"
        )
    except (OSError, OverflowError, ValueError):
        return str(ms)


def clean_num(value, digits: int | None = None):
    if value is None:
        return None
    try:
        n = float(value)
    except (TypeError, ValueError):
        return None
    if n < 0 and n > -1.5:
        return None
    if digits is not None:
        return round(n, digits)
    return n


def _upload_path(upload_id: str) -> Path | None:
    if not upload_id or not all(c in "0123456789abcdef" for c in upload_id):
        return None
    path = LOGBOOK_UPLOAD_DIR / f"{upload_id}.sqlite"
    return path if path.is_file() else None


def _cleanup_old_logbook_uploads(keep_id: str | None = None) -> None:
    for p in LOGBOOK_UPLOAD_DIR.glob("*.sqlite"):
        if keep_id and p.stem == keep_id:
            continue
        try:
            p.unlink(missing_ok=True)
        except OSError:
            pass


@app.get("/admin/logbook")
def admin_logbook_page():
    user = current_user(SYSTEM_DB)
    if user is None:
        return redirect("/login?next=/admin/logbook")
    if user.role != ROLE_ADMIN:
        return redirect("/")
    return send_from_directory(STATIC, "logbook-import.html")


@app.get("/login")
def login_page():
    if current_user(SYSTEM_DB):
        return redirect("/")
    return send_from_directory(STATIC, "login.html")


@app.get("/admin")
def admin_page():
    user = current_user(SYSTEM_DB)
    if user is None:
        return redirect("/login?next=/admin")
    if user.role != ROLE_ADMIN:
        return redirect("/")
    return send_from_directory(STATIC, "admin.html")


@app.get("/")
def index():
    if current_user(SYSTEM_DB) is None:
        return redirect("/login")
    return send_from_directory(STATIC, "index.html")


@app.get("/photos")
def photos_manage_page():
    if current_user(SYSTEM_DB) is None:
        return redirect("/login?next=/photos")
    return send_from_directory(STATIC, "photos-manage.html")


@app.post("/api/auth/login")
def api_auth_login():
    body = request.get_json(silent=True) or {}
    username = (body.get("username") or "").strip()
    password = body.get("password") or ""
    user = authenticate(SYSTEM_DB, username, password)
    if user is None:
        return jsonify({"error": "Benutzername oder Passwort ungültig."}), 401
    login_user(user)
    return jsonify(user_to_public_dict(user))


@app.post("/api/auth/logout")
def api_auth_logout():
    logout_user()
    return jsonify({"ok": True})


@app.get("/api/auth/me")
def api_auth_me():
    user = current_user(SYSTEM_DB)
    if user is None:
        return jsonify({"error": "Nicht angemeldet."}), 401
    return jsonify(user_to_public_dict(user))


@app.get("/api/toerns")
@require_login_api(SYSTEM_DB)
def api_toerns(user):
    rows = list_toerns_summary(SYSTEM_DB)

    result = []
    for r in rows:
        tid = r["id"]
        if user.role != ROLE_ADMIN and tid not in user.toern_ids:
            continue
        result.append(
            {
                "id": r["id"],
                "name": r["name"] or f"Törn {r['id']}",
                "revier": parse_revier(r["revier_raw"]),
                "ship": r["ship"] or "",
                "points": r["points"] or 0,
                "pointsWithCoords": r["points_with_coords"] or 0,
                "from": fmt_time(r["t_min"]),
                "to": fmt_time(r["t_max"]),
            }
        )
    return jsonify(result)


@app.get("/api/track/<int:toern_id>")
@require_login_api(SYSTEM_DB)
def api_track(toern_id: int, user):
    denied = require_toern_access(toern_id, user)
    if denied:
        return denied
    rows = fetch_track_rows(SYSTEM_DB, toern_id)

    points = []
    for r in rows:
        status = r["status"]
        point_id = r["source_id"] if r["source_id"] is not None else r["id"]
        points.append(
            {
                "id": point_id,
                "time": fmt_time(r["zeitstempel"]),
                "ts": r["zeitstempel"],
                "lat": r["cl_lat"],
                "lon": r["cl_lon"],
                "cog": r["cl_course"],
                "sog": clean_num(r["cl_speed"], 2),
                "engineHrs": clean_num(r["engine_op_hrs1"], 1),
                "log": clean_num(r["logge"], 2),
                "geo": r["ort_text"] or "",
                "text": r["freitext"] or "",
                "pressure": clean_num(r["luftdruck"], 1),
                "windTws": clean_num(r["wind_tws"], 1),
                "windTwd": None if r["wind_twd"] is None or r["wind_twd"] < 0 else int(r["wind_twd"]),
                "windGusts": clean_num(r["wind_tws_gusts"], 1),
                "wave": clean_num(r["wwo_welle"], 1),
                "recordtype": r["recordtype"] or 0,
                "status": status,
                "statusLabel": STATUS_LABELS.get(status, f"Status {status}"),
            }
        )

    return jsonify({"toernId": toern_id, "count": len(points), "points": points})


@app.get("/api/photos/<int:toern_id>")
@require_login_api(SYSTEM_DB)
def api_photos(toern_id: int, user):
    denied = require_toern_access(toern_id, user)
    if denied:
        return denied
    photos = list_photos(SYSTEM_DB, toern_id)
    clusters = cluster_photos(photos)
    return jsonify(
        {
            "toernId": toern_id,
            "meta": {
                "photoCount": len(photos),
                "clusterCount": len(clusters),
            },
            "warnings": [],
            "clusters": clusters_to_json(clusters),
        }
    )


@app.post("/api/photos/upload")
@require_login_api(SYSTEM_DB)
def api_photos_upload(user):
    toern_raw = request.form.get("toern")
    if toern_raw is None:
        return jsonify({"error": "Feld 'toern' fehlt."}), 400
    try:
        toern = int(toern_raw)
    except ValueError:
        return jsonify({"error": "Ungültige Törn-ID."}), 400

    denied = require_toern_access(toern, user)
    if denied:
        return denied

    lat = lon = None
    if request.form.get("lat") not in (None, ""):
        try:
            lat = float(request.form.get("lat"))
            lon = float(request.form.get("lon"))
        except (TypeError, ValueError):
            return jsonify({"error": "Ungültige Koordinaten."}), 400

    title = (request.form.get("title") or "").strip()
    files = request.files.getlist("photos")
    if not files:
        single = request.files.get("photo")
        files = [single] if single and single.filename else []

    if not files:
        return jsonify({"error": "Keine Dateien ausgewählt."}), 400

    track = track_timeline(SYSTEM_DB, toern)

    saved = []
    errors = []
    for f in files:
        if not f.filename:
            continue
        data = f.read()
        if not data:
            errors.append(f"{f.filename}: leer")
            continue
        photo, err = save_upload(
            SYSTEM_DB,
            PHOTOS_DIR,
            toern,
            data,
            f.filename,
            lat,
            lon,
            title,
            track,
            uploaded_by_user_id=user.id,
        )
        if err:
            errors.append(f"{f.filename}: {err}")
        elif photo:
            saved.append({"id": photo.id, "filename": photo.original_name})

    if not saved and errors:
        return jsonify({"error": errors[0], "errors": errors}), 400

    return jsonify({"saved": saved, "errors": errors, "count": len(saved)})


@app.get("/api/photos/list/<int:toern_id>")
@require_login_api(SYSTEM_DB)
def api_photos_list(toern_id: int, user):
    denied = require_toern_access(toern_id, user)
    if denied:
        return denied
    rows = list_photos_manage(SYSTEM_DB, toern_id)
    items = []
    for p, created_ms in rows:
        can_edit = can_edit_photo(SYSTEM_DB, user, p.id)
        uname = username_for_id(SYSTEM_DB, p.uploaded_by_user_id)
        items.append(
            photo_manage_dict(
                p,
                created_ms,
                can_edit=can_edit,
                uploaded_by_username=uname,
            )
        )
    return jsonify({"toernId": toern_id, "count": len(items), "photos": items})


@app.post("/api/photos/import/<int:toern_id>")
@require_login_api(SYSTEM_DB)
def api_photos_import(toern_id: int, user):
    denied = require_toern_access(toern_id, user)
    if denied:
        return denied
    body = request.get_json(silent=True) or {}
    refresh = bool(body.get("refreshExisting"))

    track = track_timeline(SYSTEM_DB, toern_id)

    imported, updated, warnings, meta = import_photos_from_folder(
        SYSTEM_DB,
        PHOTOS_DIR,
        toern_id,
        track,
        refresh_existing=refresh,
        uploaded_by_user_id=user.id,
    )

    return jsonify(
        {
            "toernId": toern_id,
            "imported": [{"id": p.id, "filename": p.filename} for p in imported],
            "updated": [{"id": p.id, "filename": p.filename} for p in updated],
            "warnings": warnings,
            "meta": meta,
        }
    )


@app.patch("/api/photos/item/<int:photo_id>")
@require_login_api(SYSTEM_DB)
def api_photos_update(photo_id: int, user):
    denied = require_photo_edit(SYSTEM_DB, photo_id, user)
    if denied:
        return denied
    body = request.get_json(silent=True) or {}
    title = body.get("title")
    lat = body.get("lat")
    lon = body.get("lon")

    if lat is not None or lon is not None:
        if lat is None or lon is None:
            return jsonify({"error": "LAT und LON gemeinsam angeben."}), 400
        try:
            lat = float(lat)
            lon = float(lon)
        except (TypeError, ValueError):
            return jsonify({"error": "Ungültige Koordinaten."}), 400

    if title is not None:
        title = str(title).strip()

    photo = update_photo(
        SYSTEM_DB,
        photo_id,
        title=title if "title" in body else None,
        lat=lat if "lat" in body else None,
        lon=lon if "lon" in body else None,
    )
    if photo is None:
        return jsonify({"error": "Foto nicht gefunden."}), 404

    created_at_ms = None
    conn = sqlite3.connect(SYSTEM_DB)
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            "SELECT created_at_ms FROM photos WHERE id = ?", (photo_id,)
        ).fetchone()
        if row:
            created_at_ms = row["created_at_ms"]
    finally:
        conn.close()

    return jsonify(
        photo_manage_dict(
            photo,
            created_at_ms,
            can_edit=True,
            uploaded_by_username=username_for_id(
                SYSTEM_DB, photo.uploaded_by_user_id
            ),
        )
    )


@app.delete("/api/photos/item/<int:photo_id>")
@require_login_api(SYSTEM_DB)
def api_photos_delete(photo_id: int, user):
    denied = require_photo_edit(SYSTEM_DB, photo_id, user)
    if denied:
        return denied
    if not delete_photo(SYSTEM_DB, PHOTOS_DIR, photo_id):
        return jsonify({"error": "Foto nicht gefunden."}), 404
    return jsonify({"deleted": photo_id})


@app.get("/api/photos/file/<int:photo_id>")
@require_login_api(SYSTEM_DB)
def api_photos_file(photo_id: int, user):
    photo, path = get_photo(SYSTEM_DB, PHOTOS_DIR, photo_id)
    if photo is None or path is None:
        return jsonify({"error": "Foto nicht gefunden."}), 404
    denied = require_toern_access(photo.toern, user)
    if denied:
        return denied

    if request.args.get("thumb") == "1":
        if path.suffix.lower() in VIDEO_EXT:
            import io

            from flask import send_file

            svg = (
                '<svg xmlns="http://www.w3.org/2000/svg" width="320" height="240" viewBox="0 0 320 240">'
                '<rect width="320" height="240" fill="#0a1c26"/>'
                '<circle cx="160" cy="120" r="44" fill="none" stroke="#e8f2f4" stroke-width="4"/>'
                '<polygon points="148,98 148,142 188,120" fill="#2f9e8a"/>'
                "</svg>"
            )
            return send_file(io.BytesIO(svg.encode("utf-8")), mimetype="image/svg+xml")

        try:
            from PIL import Image
            import io

            with Image.open(path) as img:
                img.thumbnail((320, 320))
                buf = io.BytesIO()
                fmt = "JPEG" if path.suffix.lower() in (".jpg", ".jpeg") else "PNG"
                img.save(buf, format=fmt, quality=85)
                buf.seek(0)
                from flask import send_file

                return send_file(buf, mimetype=f"image/{fmt.lower()}")
        except Exception:
            pass

    return send_from_directory(path.parent, path.name)


@app.get("/api/admin/users")
@require_admin_api(SYSTEM_DB)
def api_admin_users(user):
    return jsonify({"users": list_users(SYSTEM_DB)})


@app.post("/api/admin/users")
@require_admin_api(SYSTEM_DB)
def api_admin_users_create(user):
    body = request.get_json(silent=True) or {}
    username = (body.get("username") or "").strip()
    password = body.get("password") or ""
    role = body.get("role") or "user"
    toern_ids = body.get("toernIds") or []
    created, err = create_user(
        SYSTEM_DB,
        username,
        password,
        role=role,
        toern_ids=[int(x) for x in toern_ids],
    )
    if err:
        return jsonify({"error": err}), 400
    return jsonify(created), 201


@app.patch("/api/admin/users/<int:user_id>")
@require_admin_api(SYSTEM_DB)
def api_admin_users_update(user_id: int, user):
    body = request.get_json(silent=True) or {}
    password = body.get("password")
    role = body.get("role")
    toern_ids = body.get("toernIds")
    if toern_ids is not None:
        toern_ids = [int(x) for x in toern_ids]
    updated, err = update_user(
        SYSTEM_DB,
        user_id,
        password=password if password else None,
        role=role,
        toern_ids=toern_ids,
    )
    if err:
        return jsonify({"error": err}), 400
    if updated is None:
        return jsonify({"error": "Benutzer nicht gefunden."}), 404
    return jsonify(updated)


@app.delete("/api/admin/users/<int:user_id>")
@require_admin_api(SYSTEM_DB)
def api_admin_users_delete(user_id: int, user):
    if user_id == user.id:
        return jsonify({"error": "Eigenes Konto nicht löschbar."}), 400
    if not delete_user(SYSTEM_DB, user_id):
        return jsonify({"error": "Benutzer nicht gefunden."}), 404
    return jsonify({"deleted": user_id})


@app.post("/api/admin/logbook/upload")
@require_admin_api(SYSTEM_DB)
def api_admin_logbook_upload(user):
    f = request.files.get("logbook")
    if not f or not f.filename:
        return jsonify({"error": "Datei „logbook“ fehlt."}), 400
    if not f.filename.lower().endswith(".sqlite"):
        return jsonify({"error": "Bitte eine .sqlite-Datei hochladen."}), 400

    upload_id = uuid.uuid4().hex
    dest = LOGBOOK_UPLOAD_DIR / f"{upload_id}.sqlite"
    f.save(dest)
    ok, err = validate_logbook_file(dest)
    if not ok:
        dest.unlink(missing_ok=True)
        return jsonify({"error": err or "Ungültige Datei."}), 400

    _cleanup_old_logbook_uploads(keep_id=upload_id)
    return jsonify({"uploadId": upload_id, "filename": f.filename})


@app.get("/api/admin/logbook/preview")
@require_admin_api(SYSTEM_DB)
def api_admin_logbook_preview(user):
    upload_id = request.args.get("uploadId", "")
    path = _upload_path(upload_id)
    if path is None:
        return jsonify({"error": "Upload nicht gefunden (erneut hochladen)."}), 404

    imported = list_imported_toern_ids(SYSTEM_DB)
    toerns = []
    for r in list_toerns_in_logbook(path):
        tid = int(r["id"])
        toerns.append(
            {
                "id": tid,
                "name": r["name"] or f"Törn {tid}",
                "ship": r["ship"] or "",
                "points": r["points"] or 0,
                "pointsWithCoords": r["points_with_coords"] or 0,
                "alreadyImported": tid in imported,
            }
        )
    return jsonify({"uploadId": upload_id, "toerns": toerns})


@app.post("/api/admin/logbook/import")
@require_admin_api(SYSTEM_DB)
def api_admin_logbook_import(user):
    body = request.get_json(silent=True) or {}
    upload_id = (body.get("uploadId") or "").strip()
    raw_ids = body.get("toernIds") or []
    path = _upload_path(upload_id)
    if path is None:
        return jsonify({"error": "Upload nicht gefunden (erneut hochladen)."}), 404
    if not raw_ids:
        return jsonify({"error": "Mindestens einen Törn auswählen."}), 400

    try:
        toern_ids = [int(x) for x in raw_ids]
    except (TypeError, ValueError):
        return jsonify({"error": "Ungültige Törn-IDs."}), 400

    imported, errors = import_toerns_from_file(SYSTEM_DB, path, toern_ids)
    if imported:
        path.unlink(missing_ok=True)
    return jsonify(
        {
            "imported": imported,
            "errors": errors,
            "message": (
                f"{len(imported)} Törn(s) übernommen."
                if imported
                else "Kein Törn importiert."
            ),
        }
    )


if __name__ == "__main__":
    PHOTOS_DIR.mkdir(parents=True, exist_ok=True)
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "5000"))
    print(f"Logbook Viso -> http://{host}:{port}  (App-DB: {SYSTEM_DB})")
    app.run(host=host, port=port, debug=os.environ.get("FLASK_DEBUG") == "1")
