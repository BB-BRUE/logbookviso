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


def _resolve_photo_coords(
    file_path: Path,
    track: list[tuple[int, float, float]] | None,
) -> tuple[float | None, float | None, int | None, str | None]:
    exif_lat, exif_lon, taken_ms = extract_exif(file_path)
    use_lat, use_lon = exif_lat, exif_lon
    if (use_lat is None or use_lon is None) and taken_ms and track:
        pt = nearest_track_point(taken_ms, track)
        if pt:
            use_lat, use_lon = pt
    if use_lat is None or use_lon is None:
        return None, None, taken_ms, "Keine Koordinaten (EXIF) und kein Track-Treffer."
    return float(use_lat), float(use_lon), taken_ms, None


def _insert_photo_row(
    db_path: Path,
    toern: int,
    filename: str,
    original_name: str,
    title: str,
    lat: float,
    lon: float,
    taken_at_ms: int | None,
) -> StoredPhoto:
    now_ms = int(time.time() * 1000)
    with get_photos_conn(db_path) as conn:
        cur = conn.execute(
            """
            INSERT INTO photos
                (toern, filename, original_name, title, lat, lon, taken_at_ms, created_at_ms)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (toern, filename, original_name, title, lat, lon, taken_at_ms, now_ms),
        )
        photo_id = int(cur.lastrowid)
        conn.commit()
    return StoredPhoto(
        id=photo_id,
        toern=toern,
        filename=filename,
        original_name=original_name,
        title=title,
        lat=lat,
        lon=lon,
        taken_at_ms=taken_at_ms,
    )


def import_photos_from_folder(
    db_path: Path,
    photos_dir: Path,
    toern: int,
    track: list[tuple[int, float, float]] | None = None,
    *,
    refresh_existing: bool = False,
) -> tuple[list[StoredPhoto], list[StoredPhoto], list[str], dict[str, Any]]:
    """
    Liest Bilder aus data/photos/<toörn>/ ein.
    - Neue Dateien → DB-Eintrag (EXIF-GPS oder Track-Zeit)
    - refresh_existing: GPS/Zeit für vorhandene DB-Einträge aus EXIF aktualisieren
    """
    toern_dir = photos_dir / str(toern)
    warnings: list[str] = []
    imported: list[StoredPhoto] = []
    updated: list[StoredPhoto] = []

    if not toern_dir.is_dir():
        warnings.append(f"Ordner nicht gefunden: {toern_dir}")
        return imported, updated, warnings, {"folder": str(toern_dir), "scanned": 0}

    with get_photos_conn(db_path) as conn:
        db_rows = conn.execute(
            """
            SELECT id, filename, original_name, title, lat, lon, taken_at_ms
            FROM photos WHERE toern = ?
            """,
            (toern,),
        ).fetchall()

    known_by_filename = {r["filename"]: r for r in db_rows}
    disk_names: set[str] = set()
    scanned = 0

    for file_path in sorted(toern_dir.iterdir()):
        if not file_path.is_file():
            continue
        if file_path.suffix.lower() not in ALLOWED_EXT:
            continue
        scanned += 1
        disk_names.add(file_path.name)

        if file_path.name in known_by_filename:
            if not refresh_existing:
                continue
            lat, lon, taken_ms, err = _resolve_photo_coords(file_path, track)
            if err:
                warnings.append(f"{file_path.name}: {err}")
                continue
            row = known_by_filename[file_path.name]
            with get_photos_conn(db_path) as conn:
                conn.execute(
                    """
                    UPDATE photos SET lat = ?, lon = ?, taken_at_ms = ?
                    WHERE id = ?
                    """,
                    (lat, lon, taken_ms, row["id"]),
                )
                conn.commit()
            updated.append(
                StoredPhoto(
                    id=int(row["id"]),
                    toern=toern,
                    filename=row["filename"],
                    original_name=row["original_name"] or file_path.name,
                    title=row["title"] or "",
                    lat=lat,
                    lon=lon,
                    taken_at_ms=taken_ms,
                )
            )
            continue

        lat, lon, taken_ms, err = _resolve_photo_coords(file_path, track)
        if err:
            warnings.append(f"{file_path.name}: {err}")
            continue

        title = file_path.stem
        photo = _insert_photo_row(
            db_path,
            toern,
            file_path.name,
            file_path.name,
            title,
            lat,
            lon,
            taken_ms,
        )
        imported.append(photo)

    missing_on_disk = [fn for fn in known_by_filename if fn not in disk_names]
    if missing_on_disk:
        warnings.append(
            f"{len(missing_on_disk)} DB-Einträge ohne Datei im Ordner (z. B. {missing_on_disk[0]})."
        )

    meta = {
        "folder": str(toern_dir.resolve()),
        "scanned": scanned,
        "imported": len(imported),
        "updated": len(updated),
        "refreshExisting": refresh_existing,
    }
    return imported, updated, warnings, meta


def list_photos(db_path: Path, toern: int) -> list[StoredPhoto]:
    with get_photos_conn(db_path) as conn:
        rows = conn.execute(
            """
            SELECT id, toern, filename, original_name, title, lat, lon, taken_at_ms,
                   created_at_ms
            FROM photos
            WHERE toern = ?
            ORDER BY COALESCE(taken_at_ms, created_at_ms), id
            """,
            (toern,),
        ).fetchall()
    return [_row_to_photo(r) for r in rows]


def _row_to_photo(r: sqlite3.Row) -> StoredPhoto:
    return StoredPhoto(
        id=int(r["id"]),
        toern=int(r["toern"]),
        filename=r["filename"],
        original_name=r["original_name"] or "",
        title=r["title"] or "",
        lat=float(r["lat"]),
        lon=float(r["lon"]),
        taken_at_ms=r["taken_at_ms"],
    )


def photo_manage_dict(p: StoredPhoto, created_at_ms: int | None = None) -> dict[str, Any]:
    return {
        "id": p.id,
        "toern": p.toern,
        "title": p.title,
        "originalName": p.original_name,
        "lat": p.lat,
        "lon": p.lon,
        "takenAtMs": p.taken_at_ms,
        "createdAtMs": created_at_ms,
        "thumbUrl": f"/api/photos/file/{p.id}?thumb=1",
        "url": f"/api/photos/file/{p.id}",
    }


def list_photos_manage(db_path: Path, toern: int) -> list[dict[str, Any]]:
    with get_photos_conn(db_path) as conn:
        rows = conn.execute(
            """
            SELECT id, toern, filename, original_name, title, lat, lon, taken_at_ms,
                   created_at_ms
            FROM photos
            WHERE toern = ?
            ORDER BY COALESCE(taken_at_ms, created_at_ms) DESC, id DESC
            """,
            (toern,),
        ).fetchall()
    out: list[dict[str, Any]] = []
    for r in rows:
        p = _row_to_photo(r)
        out.append(photo_manage_dict(p, r["created_at_ms"]))
    return out


def update_photo(
    db_path: Path,
    photo_id: int,
    *,
    title: str | None = None,
    lat: float | None = None,
    lon: float | None = None,
) -> StoredPhoto | None:
    fields: list[str] = []
    values: list[Any] = []
    if title is not None:
        fields.append("title = ?")
        values.append(title)
    if lat is not None:
        fields.append("lat = ?")
        values.append(float(lat))
    if lon is not None:
        fields.append("lon = ?")
        values.append(float(lon))
    if not fields:
        photo, _ = get_photo(db_path, Path("."), photo_id)
        return photo

    values.append(photo_id)
    with get_photos_conn(db_path) as conn:
        conn.execute(
            f"UPDATE photos SET {', '.join(fields)} WHERE id = ?",
            values,
        )
        conn.commit()
    photo, _ = get_photo(db_path, Path("."), photo_id)
    return photo


def delete_photo(db_path: Path, photos_dir: Path, photo_id: int) -> bool:
    photo, path = get_photo(db_path, photos_dir, photo_id)
    if photo is None:
        return False
    with get_photos_conn(db_path) as conn:
        conn.execute("DELETE FROM photos WHERE id = ?", (photo_id,))
        conn.commit()
    if path and path.is_file():
        path.unlink()
    return True


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
    photo = _row_to_photo(row)
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
