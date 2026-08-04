"""Uploaded trip photos: files under data/photos/, metadata in SQLite."""

from __future__ import annotations

import math
import sqlite3
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

CLUSTER_RADIUS_M = 250
ALLOWED_EXT = {".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif"}


@dataclass
class StoredPhoto:
    id: int
    toern: int
    filename: str
    original_name: str
    title: str
    lat: float
    lon: float
    taken_at_ms: int | None


@dataclass
class PhotoCluster:
    id: str
    lat: float
    lon: float
    photos: list[StoredPhoto]


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def init_photos_db(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS photos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                toern INTEGER NOT NULL,
                filename TEXT NOT NULL,
                original_name TEXT,
                title TEXT,
                lat REAL NOT NULL,
                lon REAL NOT NULL,
                taken_at_ms INTEGER,
                created_at_ms INTEGER NOT NULL
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_photos_toern ON photos(toern)"
        )


def get_photos_conn(db_path: Path) -> sqlite3.Connection:
    init_photos_db(db_path)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def _dms_to_deg(values: Any, ref: str) -> float | None:
    try:
        d, m, s = values
        deg = float(d) + float(m) / 60 + float(s) / 3600
        if ref in ("S", "W"):
            deg = -deg
        return deg
    except (TypeError, ValueError, ZeroDivisionError):
        return None


def extract_exif(file_path: Path) -> tuple[float | None, float | None, int | None]:
    """Read GPS and capture time from EXIF when available."""
    try:
        from PIL import Image
        from PIL.ExifTags import TAGS
    except ImportError:
        return None, None, None

    try:
        with Image.open(file_path) as img:
            exif = img.getexif()
            if not exif:
                return None, None, None

            gps_info: dict[int, Any] = {}
            taken_ms = None
            for tag_id, value in exif.items():
                tag = TAGS.get(tag_id, tag_id)
                if tag == "GPSInfo" and isinstance(value, dict):
                    gps_info = value
                elif tag in ("DateTimeOriginal", "DateTime") and taken_ms is None:
                    try:
                        from datetime import datetime

                        dt = datetime.strptime(str(value), "%Y:%m:%d %H:%M:%S")
                        taken_ms = int(dt.timestamp() * 1000)
                    except ValueError:
                        pass

            lat = lon = None
            if gps_info:
                from PIL.ExifTags import GPSTAGS

                gps: dict[str, Any] = {
                    GPSTAGS.get(k, k): v for k, v in gps_info.items()
                }
                lat = _dms_to_deg(gps.get("GPSLatitude"), str(gps.get("GPSLatitudeRef", "N")))
                lon = _dms_to_deg(gps.get("GPSLongitude"), str(gps.get("GPSLongitudeRef", "E")))

            return lat, lon, taken_ms
    except OSError:
        return None, None, None


def nearest_track_point(
    taken_ms: int,
    track: list[tuple[int, float, float]],
    max_delta_ms: int = 7 * 24 * 3600 * 1000,
) -> tuple[float, float] | None:
    if not track:
        return None
    best = None
    best_dt = None
    for ts, lat, lon in track:
        dt = abs(ts - taken_ms)
        if best_dt is None or dt < best_dt:
            best_dt = dt
            best = (lat, lon)
    if best_dt is not None and best_dt <= max_delta_ms:
        return best
    return None


def save_upload(
    db_path: Path,
    photos_dir: Path,
    toern: int,
    file_bytes: bytes,
    original_name: str,
    lat: float | None,
    lon: float | None,
    title: str = "",
    track: list[tuple[int, float, float]] | None = None,
) -> tuple[StoredPhoto | None, str | None]:
    ext = Path(original_name).suffix.lower()
    if ext not in ALLOWED_EXT:
        return None, f"Dateityp nicht erlaubt: {ext}"

    toern_dir = photos_dir / str(toern)
    toern_dir.mkdir(parents=True, exist_ok=True)
    stored_name = f"{uuid.uuid4().hex}{ext}"
    dest = toern_dir / stored_name
    dest.write_bytes(file_bytes)

    exif_lat, exif_lon, taken_ms = extract_exif(dest)
    use_lat = lat if lat is not None else exif_lat
    use_lon = lon if lon is not None else exif_lon

    if (use_lat is None or use_lon is None) and taken_ms and track:
        pt = nearest_track_point(taken_ms, track)
        if pt:
            use_lat, use_lon = pt

    if use_lat is None or use_lon is None:
        dest.unlink(missing_ok=True)
        return None, "Keine Koordinaten (EXIF/formular) und kein Track-Treffer."

    now_ms = int(time.time() * 1000)
    with get_photos_conn(db_path) as conn:
        cur = conn.execute(
            """
            INSERT INTO photos
                (toern, filename, original_name, title, lat, lon, taken_at_ms, created_at_ms)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                toern,
                stored_name,
                original_name,
                title,
                float(use_lat),
                float(use_lon),
                taken_ms,
                now_ms,
            ),
        )
        photo_id = int(cur.lastrowid)
        conn.commit()

    return (
        StoredPhoto(
            id=photo_id,
            toern=toern,
            filename=stored_name,
            original_name=original_name,
            title=title,
            lat=float(use_lat),
            lon=float(use_lon),
            taken_at_ms=taken_ms,
        ),
        None,
    )


def list_photos(db_path: Path, toern: int) -> list[StoredPhoto]:
    with get_photos_conn(db_path) as conn:
        rows = conn.execute(
            """
            SELECT id, toern, filename, original_name, title, lat, lon, taken_at_ms
            FROM photos
            WHERE toern = ?
            ORDER BY COALESCE(taken_at_ms, created_at_ms), id
            """,
            (toern,),
        ).fetchall()
    return [
        StoredPhoto(
            id=int(r["id"]),
            toern=int(r["toern"]),
            filename=r["filename"],
            original_name=r["original_name"] or "",
            title=r["title"] or "",
            lat=float(r["lat"]),
            lon=float(r["lon"]),
            taken_at_ms=r["taken_at_ms"],
        )
        for r in rows
    ]


def photo_file_path(photos_dir: Path, photo: StoredPhoto) -> Path:
    return photos_dir / str(photo.toern) / photo.filename


def get_photo(db_path: Path, photos_dir: Path, photo_id: int) -> tuple[StoredPhoto | None, Path | None]:
    with get_photos_conn(db_path) as conn:
        row = conn.execute(
            """
            SELECT id, toern, filename, original_name, title, lat, lon, taken_at_ms
            FROM photos WHERE id = ?
            """,
            (photo_id,),
        ).fetchone()
    if row is None:
        return None, None
    photo = StoredPhoto(
        id=int(row["id"]),
        toern=int(row["toern"]),
        filename=row["filename"],
        original_name=row["original_name"] or "",
        title=row["title"] or "",
        lat=float(row["lat"]),
        lon=float(row["lon"]),
        taken_at_ms=row["taken_at_ms"],
    )
    path = photo_file_path(photos_dir, photo)
    if not path.is_file():
        return photo, None
    return photo, path


def cluster_photos(photos: list[StoredPhoto], radius_m: float = CLUSTER_RADIUS_M) -> list[PhotoCluster]:
    clusters: list[PhotoCluster] = []
    for photo in photos:
        target: PhotoCluster | None = None
        for cluster in clusters:
            if haversine_m(photo.lat, photo.lon, cluster.lat, cluster.lon) <= radius_m:
                target = cluster
                break
        if target is None:
            clusters.append(
                PhotoCluster(
                    id=f"c_{len(clusters) + 1}",
                    lat=photo.lat,
                    lon=photo.lon,
                    photos=[photo],
                )
            )
            continue
        target.photos.append(photo)
        n = len(target.photos)
        target.lat = sum(p.lat for p in target.photos) / n
        target.lon = sum(p.lon for p in target.photos) / n
    return clusters


def clusters_to_json(clusters: list[PhotoCluster]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for c in clusters:
        out.append(
            {
                "id": c.id,
                "lat": c.lat,
                "lon": c.lon,
                "count": len(c.photos),
                "photos": [
                    {
                        "id": p.id,
                        "url": f"/api/photos/file/{p.id}",
                        "thumbUrl": f"/api/photos/file/{p.id}?thumb=1",
                        "title": p.title or p.original_name,
                        "takenAtMs": p.taken_at_ms,
                        "locationSource": "upload",
                    }
                    for p in c.photos
                ],
            }
        )
    return out
