"""Gemeinsame SQLite-Verbindungs-Hilfe.

Mehrere Gunicorn-Worker/Threads greifen auf dieselbe SYSTEM_DB-Datei zu.
``connect()`` setzt daher konsistent WAL-Modus (bessere Nebenläufigkeit von
Lesen/Schreiben) und einen Busy-Timeout (kurze Wartezeit statt sofortigem
``database is locked``-Fehler bei gleichzeitigen Schreibzugriffen).
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

BUSY_TIMEOUT_MS = 5000


def connect(db_path: Path | str, *, row_factory: bool = False) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    if row_factory:
        conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute(f"PRAGMA busy_timeout = {BUSY_TIMEOUT_MS}")
    return conn
