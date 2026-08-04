"""Logbook track map – serves API + static frontend from logbook.sqlite."""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory

from photos_store import (
    clusters_to_json,
    cluster_photos,
    get_photo,
    list_photos,
    save_upload,
)

ROOT = Path(__file__).resolve().parent
DB_PATH = Path(os.environ.get("LOGBOOK_DB", str(ROOT / "data/logbook.sqlite")))
PHOTOS_DB = Path(os.environ.get("PHOTOS_DB", str(ROOT / "data/photos.sqlite")))
PHOTOS_DIR = Path(os.environ.get("PHOTOS_DIR", str(ROOT / "data/photos")))
STATIC = ROOT / "static"
MAX_UPLOAD_MB = int(os.environ.get("MAX_UPLOAD_MB", "256"))

STATUS_LABELS = {
    0: "Segeln",
    1: "Festgemacht",
    2: "Motor",
    3: "Anker",
}

app = Flask(__name__, static_folder=str(STATIC), static_url_path="")
app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_MB * 1024 * 1024


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


def get_db() -> sqlite3.Connection:
    """Open SQLite read-only (works with Docker :ro volume mounts for logbook)."""
    path = DB_PATH.expanduser()
    if not path.is_file():
        hint = (
            "Pfad ist ein Verzeichnis (Docker hat oft einen Ordner angelegt, "
            "wenn die Host-Datei fehlte)."
            if path.is_dir()
            else "Datei fehlt – Volume-Mount prüfen."
        )
        raise FileNotFoundError(f"Datenbank nicht nutzbar: {path} – {hint}")

    uri = f"file:{path.resolve().as_posix()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    return conn


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


def track_timeline(conn: sqlite3.Connection, toern_id: int) -> list[tuple[int, float, float]]:
    rows = conn.execute(
        """
        SELECT zeitstempel, cl_lat, cl_lon
        FROM Logrecord
        WHERE toern = ?
          AND (geloescht IS NULL OR geloescht = 0)
          AND zeitstempel IS NOT NULL
          AND zeitstempel < 7000000000000
          AND cl_lat IS NOT NULL
          AND cl_lon IS NOT NULL
          AND ABS(cl_lat) > 0.01
          AND ABS(cl_lon) > 0.01
        ORDER BY zeitstempel ASC
        """,
        (toern_id,),
    ).fetchall()
    return [(int(r["zeitstempel"]), float(r["cl_lat"]), float(r["cl_lon"])) for r in rows]


@app.get("/")
def index():
    return send_from_directory(STATIC, "index.html")


@app.get("/api/toerns")
def api_toerns():
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT
                t.toernId AS id,
                t.toernName AS name,
                t.toernRevier AS revier_raw,
                t.schiffName AS ship,
                t.toernCreateDate AS created,
                COUNT(l.id) AS points,
                SUM(
                    CASE
                        WHEN l.cl_lat IS NOT NULL
                         AND l.cl_lon IS NOT NULL
                         AND ABS(l.cl_lat) > 0.01
                         AND ABS(l.cl_lon) > 0.01
                        THEN 1 ELSE 0
                    END
                ) AS points_with_coords,
                MIN(
                    CASE
                        WHEN l.zeitstempel IS NOT NULL AND l.zeitstempel < 7000000000000
                        THEN l.zeitstempel
                    END
                ) AS t_min,
                MAX(
                    CASE
                        WHEN l.zeitstempel IS NOT NULL AND l.zeitstempel < 7000000000000
                        THEN l.zeitstempel
                    END
                ) AS t_max
            FROM Toernrecord t
            LEFT JOIN Logrecord l
                ON l.toern = t.toernId
               AND (l.geloescht IS NULL OR l.geloescht = 0)
            GROUP BY t.toernId
            ORDER BY t.toernId
            """
        ).fetchall()

    result = []
    for r in rows:
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
def api_track(toern_id: int):
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT
                id,
                zeitstempel,
                cl_lat,
                cl_lon,
                cl_course,
                cl_speed,
                engine_op_hrs1,
                logge,
                ortText,
                freitext,
                luftdruck,
                wind_tws,
                wind_twd,
                wind_tws_gusts,
                wwo_welle,
                recordtype,
                status
            FROM Logrecord
            WHERE toern = ?
              AND (geloescht IS NULL OR geloescht = 0)
              AND cl_lat IS NOT NULL
              AND cl_lon IS NOT NULL
              AND ABS(cl_lat) > 0.01
              AND ABS(cl_lon) > 0.01
            ORDER BY zeitstempel ASC, id ASC
            """,
            (toern_id,),
        ).fetchall()

    points = []
    for r in rows:
        status = r["status"]
        points.append(
            {
                "id": r["id"],
                "time": fmt_time(r["zeitstempel"]),
                "ts": r["zeitstempel"],
                "lat": r["cl_lat"],
                "lon": r["cl_lon"],
                "cog": r["cl_course"],
                "sog": clean_num(r["cl_speed"], 2),
                "engineHrs": clean_num(r["engine_op_hrs1"], 1),
                "log": clean_num(r["logge"], 2),
                "geo": r["ortText"] or "",
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
def api_photos(toern_id: int):
    photos = list_photos(PHOTOS_DB, toern_id)
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
def api_photos_upload():
    toern_raw = request.form.get("toern")
    if toern_raw is None:
        return jsonify({"error": "Feld 'toern' fehlt."}), 400
    try:
        toern = int(toern_raw)
    except ValueError:
        return jsonify({"error": "Ungültige Törn-ID."}), 400

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

    with get_db() as conn:
        track = track_timeline(conn, toern)

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
            PHOTOS_DB,
            PHOTOS_DIR,
            toern,
            data,
            f.filename,
            lat,
            lon,
            title,
            track,
        )
        if err:
            errors.append(f"{f.filename}: {err}")
        elif photo:
            saved.append({"id": photo.id, "filename": photo.original_name})

    if not saved and errors:
        return jsonify({"error": errors[0], "errors": errors}), 400

    return jsonify({"saved": saved, "errors": errors, "count": len(saved)})


@app.get("/api/photos/file/<int:photo_id>")
def api_photos_file(photo_id: int):
    photo, path = get_photo(PHOTOS_DB, PHOTOS_DIR, photo_id)
    if photo is None or path is None:
        return jsonify({"error": "Foto nicht gefunden."}), 404

    if request.args.get("thumb") == "1":
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


@app.get("/api/status-legend")
def api_status_legend():
    return jsonify(
        [
            {"status": k, "label": v}
            for k, v in sorted(STATUS_LABELS.items())
        ]
    )


if __name__ == "__main__":
    PHOTOS_DIR.mkdir(parents=True, exist_ok=True)
    if not DB_PATH.exists():
        raise SystemExit(f"Datenbank nicht gefunden: {DB_PATH}")
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "5000"))
    print(f"Logbook Map -> http://{host}:{port}  (DB: {DB_PATH})")
    app.run(host=host, port=port, debug=os.environ.get("FLASK_DEBUG") == "1")
