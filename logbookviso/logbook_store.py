"""Logbook Törns + Track-Punkte in der App-DB (SYSTEM_DB). Import aus uploadbarer logbook.sqlite."""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path
from typing import Any

from logbookviso import db

REQUIRED_LOGBOOK_TABLES = ("Toernrecord", "Logrecord")


def init_logbook_schema(db_path: Path | str) -> None:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with db.connect(path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS toerns (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                revier_raw TEXT,
                ship TEXT,
                create_date_ms INTEGER,
                imported_at_ms INTEGER NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS log_points (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                toern_id INTEGER NOT NULL,
                source_id INTEGER,
                zeitstempel INTEGER,
                cl_lat REAL,
                cl_lon REAL,
                cl_course REAL,
                cl_speed REAL,
                engine_op_hrs1 REAL,
                logge REAL,
                ort_text TEXT,
                freitext TEXT,
                luftdruck REAL,
                wind_tws REAL,
                wind_twd REAL,
                wind_tws_gusts REAL,
                wwo_welle REAL,
                recordtype INTEGER,
                status INTEGER,
                geloescht INTEGER,
                FOREIGN KEY (toern_id) REFERENCES toerns(id) ON DELETE CASCADE
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_log_points_toern ON log_points(toern_id)"
        )
        conn.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_log_points_source
            ON log_points(toern_id, source_id)
            """
        )


def open_app_db(db_path: Path | str) -> sqlite3.Connection:
    init_logbook_schema(db_path)
    conn = db.connect(db_path, row_factory=True)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def open_logbook_file(path: Path) -> sqlite3.Connection:
    """Read-only connection to an uploaded Viso logbook.sqlite."""
    uri = f"file:{path.resolve().as_posix()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def validate_logbook_file(path: Path) -> tuple[bool, str | None]:
    if not path.is_file():
        return False, "Datei nicht gefunden."
    try:
        with open_logbook_file(path) as conn:
            tables = {
                r[0]
                for r in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
            for t in REQUIRED_LOGBOOK_TABLES:
                if t not in tables:
                    return False, f"Keine gültige Logbook-DB (Tabelle „{t}“ fehlt)."
        return True, None
    except sqlite3.Error as e:
        return False, f"SQLite-Fehler: {e}"


def list_toerns_in_logbook(path: Path) -> list[dict[str, Any]]:
    with open_logbook_file(path) as conn:
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
                ) AS points_with_coords
            FROM Toernrecord t
            LEFT JOIN Logrecord l
                ON l.toern = t.toernId
               AND (l.geloescht IS NULL OR l.geloescht = 0)
            GROUP BY t.toernId
            ORDER BY t.toernId
            """
        ).fetchall()
    return [dict(r) for r in rows]


def _row_get(row: sqlite3.Row, *keys: str) -> Any:
    for k in keys:
        if k in row.keys():
            return row[k]
    return None


def import_toerns_from_file(
    app_db_path: Path | str,
    logbook_path: Path,
    toern_ids: list[int],
) -> tuple[list[int], list[str]]:
    """Copy selected Törns + Logrecords into app DB. Replaces existing track for those IDs."""
    imported: list[int] = []
    errors: list[str] = []
    now = int(time.time() * 1000)

    with open_logbook_file(logbook_path) as src:
        with open_app_db(app_db_path) as dst:
            for tid in toern_ids:
                try:
                    trow = src.execute(
                        """
                        SELECT toernId, toernName, toernRevier, schiffName, toernCreateDate
                        FROM Toernrecord WHERE toernId = ?
                        """,
                        (tid,),
                    ).fetchone()
                    if trow is None:
                        errors.append(f"Törn {tid}: nicht in Logbook gefunden.")
                        continue

                    lrows = src.execute(
                        """
                        SELECT *
                        FROM Logrecord
                        WHERE toern = ?
                        ORDER BY id
                        """,
                        (tid,),
                    ).fetchall()

                    dst.execute("DELETE FROM log_points WHERE toern_id = ?", (tid,))
                    dst.execute(
                        """
                        INSERT INTO toerns (id, name, revier_raw, ship, create_date_ms, imported_at_ms)
                        VALUES (?, ?, ?, ?, ?, ?)
                        ON CONFLICT(id) DO UPDATE SET
                            name = excluded.name,
                            revier_raw = excluded.revier_raw,
                            ship = excluded.ship,
                            create_date_ms = excluded.create_date_ms,
                            imported_at_ms = excluded.imported_at_ms
                        """,
                        (
                            int(trow["toernId"]),
                            trow["toernName"] or f"Törn {tid}",
                            trow["toernRevier"],
                            trow["schiffName"],
                            trow["toernCreateDate"],
                            now,
                        ),
                    )

                    for lr in lrows:
                        dst.execute(
                            """
                            INSERT INTO log_points (
                                toern_id, source_id, zeitstempel, cl_lat, cl_lon,
                                cl_course, cl_speed, engine_op_hrs1, logge,
                                ort_text, freitext, luftdruck, wind_tws, wind_twd,
                                wind_tws_gusts, wwo_welle, recordtype, status, geloescht
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """,
                            (
                                tid,
                                _row_get(lr, "id"),
                                _row_get(lr, "zeitstempel"),
                                _row_get(lr, "cl_lat"),
                                _row_get(lr, "cl_lon"),
                                _row_get(lr, "cl_course"),
                                _row_get(lr, "cl_speed"),
                                _row_get(lr, "engine_op_hrs1"),
                                _row_get(lr, "logge"),
                                _row_get(lr, "ortText"),
                                _row_get(lr, "freitext"),
                                _row_get(lr, "luftdruck"),
                                _row_get(lr, "wind_tws"),
                                _row_get(lr, "wind_twd"),
                                _row_get(lr, "wind_tws_gusts"),
                                _row_get(lr, "wwo_welle"),
                                _row_get(lr, "recordtype"),
                                _row_get(lr, "status"),
                                _row_get(lr, "geloescht"),
                            ),
                        )
                    dst.commit()
                    imported.append(tid)
                except sqlite3.Error as e:
                    dst.rollback()
                    errors.append(f"Törn {tid}: {e}")

    return imported, errors


def list_toerns_summary(app_db_path: Path | str) -> list[sqlite3.Row]:
    with open_app_db(app_db_path) as conn:
        return conn.execute(
            """
            SELECT
                t.id AS id,
                t.name AS name,
                t.revier_raw AS revier_raw,
                t.ship AS ship,
                t.create_date_ms AS created,
                COUNT(l.id) AS points,
                SUM(
                    CASE
                        WHEN l.cl_lat IS NOT NULL
                         AND l.cl_lon IS NOT NULL
                         AND ABS(l.cl_lat) > 0.01
                         AND ABS(l.cl_lon) > 0.01
                         AND (l.geloescht IS NULL OR l.geloescht = 0)
                        THEN 1 ELSE 0
                    END
                ) AS points_with_coords,
                MIN(
                    CASE
                        WHEN l.zeitstempel IS NOT NULL AND l.zeitstempel < 7000000000000
                         AND (l.geloescht IS NULL OR l.geloescht = 0)
                        THEN l.zeitstempel
                    END
                ) AS t_min,
                MAX(
                    CASE
                        WHEN l.zeitstempel IS NOT NULL AND l.zeitstempel < 7000000000000
                         AND (l.geloescht IS NULL OR l.geloescht = 0)
                        THEN l.zeitstempel
                    END
                ) AS t_max
            FROM toerns t
            LEFT JOIN log_points l ON l.toern_id = t.id
            GROUP BY t.id
            ORDER BY t.id
            """
        ).fetchall()


def fetch_track_rows(app_db_path: Path | str, toern_id: int) -> list[sqlite3.Row]:
    with open_app_db(app_db_path) as conn:
        return conn.execute(
            """
            SELECT
                id,
                source_id,
                zeitstempel,
                cl_lat,
                cl_lon,
                cl_course,
                cl_speed,
                engine_op_hrs1,
                logge,
                ort_text,
                freitext,
                luftdruck,
                wind_tws,
                wind_twd,
                wind_tws_gusts,
                wwo_welle,
                recordtype,
                status
            FROM log_points
            WHERE toern_id = ?
              AND (geloescht IS NULL OR geloescht = 0)
              AND cl_lat IS NOT NULL
              AND cl_lon IS NOT NULL
              AND ABS(cl_lat) > 0.01
              AND ABS(cl_lon) > 0.01
            ORDER BY zeitstempel ASC, id ASC
            """,
            (toern_id,),
        ).fetchall()


def track_timeline(app_db_path: Path | str, toern_id: int) -> list[tuple[int, float, float]]:
    with open_app_db(app_db_path) as conn:
        rows = conn.execute(
            """
            SELECT zeitstempel, cl_lat, cl_lon
            FROM log_points
            WHERE toern_id = ?
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
    return [
        (int(r["zeitstempel"]), float(r["cl_lat"]), float(r["cl_lon"]))
        for r in rows
        if r["zeitstempel"] is not None
    ]


def list_imported_toern_ids(app_db_path: Path | str) -> set[int]:
    with open_app_db(app_db_path) as conn:
        rows = conn.execute("SELECT id FROM toerns").fetchall()
    return {int(r["id"]) for r in rows}
