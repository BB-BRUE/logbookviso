"""Logbook track map – serves API + static frontend from logbook.sqlite."""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from flask import Flask, jsonify, send_from_directory

from google_photos import clusters_to_json, load_config, load_photos_for_toern

ROOT = Path(__file__).resolve().parent
DB_PATH = Path(os.environ.get("LOGBOOK_DB", str(ROOT / "data/logbook.sqlite")))
PHOTOS_CONFIG = Path(os.environ.get("GOOGLE_PHOTOS_CONFIG", str(ROOT / "data/google-photos.json")))
PHOTOS_CACHE = Path(os.environ.get("GOOGLE_PHOTOS_CACHE", str(ROOT / "data/photos-cache")))
STATIC = ROOT / "static"

STATUS_LABELS = {
    0: "Segeln",
    1: "Festgemacht",
    2: "Motor",
    3: "Anker",
}

app = Flask(__name__, static_folder=str(STATIC), static_url_path="")


def get_db() -> sqlite3.Connection:
    """Open SQLite read-only (works with Docker :ro volume mounts)."""
    path = DB_PATH.expanduser()
    if not path.is_file():
        hint = (
            "Pfad ist ein Verzeichnis (Docker hat oft einen Ordner angelegt, "
            "wenn die Host-Datei fehlte)."
            if path.is_dir()
            else "Datei fehlt – Volume-Mount prüfen."
        )
        raise FileNotFoundError(f"Datenbank nicht nutzbar: {path} – {hint}")

    # mode=ro: SQLite braucht keinen Schreibzugriff auf Datei/Verzeichnis
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
    if n < 0 and n > -1.5:  # sentinel values like -1
        return None
    if digits is not None:
        return round(n, digits)
    return n


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


@app.get("/api/photos/<int:toern_id>")
def api_photos(toern_id: int):
    config = load_config(PHOTOS_CONFIG)
    with get_db() as conn:
        track = track_timeline(conn, toern_id)

    try:
        clusters, warnings, meta = load_photos_for_toern(
            toern_id, config, track, PHOTOS_CACHE
        )
    except Exception as exc:  # noqa: BLE001
        return jsonify({"error": str(exc), "toernId": toern_id}), 502

    return jsonify(
        {
            "toernId": toern_id,
            "meta": meta,
            "warnings": warnings,
            "clusters": clusters_to_json(clusters),
        }
    )


@app.get("/api/status-legend")
def api_status_legend():
    return jsonify(
        [
            {"status": k, "label": v}
            for k, v in sorted(STATUS_LABELS.items())
        ]
    )


if __name__ == "__main__":
    if not DB_PATH.exists():
        raise SystemExit(f"Datenbank nicht gefunden: {DB_PATH}")
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "5000"))
    print(f"Logbook Map -> http://{host}:{port}  (DB: {DB_PATH})")
    app.run(host=host, port=port, debug=os.environ.get("FLASK_DEBUG") == "1")
