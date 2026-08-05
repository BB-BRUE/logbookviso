"""Formatierung von Logbuch-Daten für JSON-API-Antworten (Track-Punkte, Törn-Metadaten)."""

from __future__ import annotations

import json
from datetime import datetime, timezone

STATUS_LABELS = {
    0: "Segeln",
    1: "Festgemacht",
    2: "Motor",
    3: "Anker",
}


def parse_revier(raw: str | None) -> str:
    """Revier aus JSON-Feld (Viso) oder Plaintext extrahieren."""
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
    """Millisekunden-Zeitstempel als UTC-String für die Karte."""
    if ms is None:
        return None
    try:
        return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime(
            "%Y-%m-%d %H:%M:%S UTC"
        )
    except (OSError, OverflowError, ValueError):
        return str(ms)


def clean_num(value, digits: int | None = None):
    """Sensor-Werte bereinigen (Sentinel -1.x → None)."""
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
