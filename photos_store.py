"""Uploaded trip photos: files under PHOTOS_DIR, metadata in SYSTEM_DB."""

from __future__ import annotations

import math
import re
import sqlite3
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

CLUSTER_RADIUS_M = 250
ALLOWED_EXT = {".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif", ".mp4", ".mov", ".m4v"}
VIDEO_EXT = {".mp4", ".mov", ".m4v"}


@dataclass
class StoredPhoto:
    id: int
    toern: int
    filename: str
    original_name: str
    title: str
    lat: float | None
    lon: float | None
    taken_at_ms: int | None
    uploaded_by_user_id: int | None = None


def photo_has_coordinates(p: StoredPhoto) -> bool:
    if p.lat is None or p.lon is None:
        return False
    return abs(p.lat) > 0.01 and abs(p.lon) > 0.01


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


from logbook_store import init_logbook_schema
from users_store import init_app_db as _init_users_schema


def init_system_db(db_path: Path) -> None:
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
                lat REAL,
                lon REAL,
                taken_at_ms INTEGER,
                created_at_ms INTEGER NOT NULL,
                uploaded_by_user_id INTEGER
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_photos_toern ON photos(toern)"
        )
        _migrate_photos_nullable_coords(conn)
        conn.commit()
    init_logbook_schema(db_path)
    _init_users_schema(db_path)


def _migrate_photos_nullable_coords(conn: sqlite3.Connection) -> None:
    cols = conn.execute("PRAGMA table_info(photos)").fetchall()
    lat_col = next((c for c in cols if c[1] == "lat"), None)
    if lat_col is None or lat_col[3] == 0:
        return
    conn.executescript(
        """
        CREATE TABLE photos_new (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            toern INTEGER NOT NULL,
            filename TEXT NOT NULL,
            original_name TEXT,
            title TEXT,
            lat REAL,
            lon REAL,
            taken_at_ms INTEGER,
            created_at_ms INTEGER NOT NULL,
            uploaded_by_user_id INTEGER
        );
        INSERT INTO photos_new
        SELECT id, toern, filename, original_name, title, lat, lon, taken_at_ms,
               created_at_ms, uploaded_by_user_id
        FROM photos;
        DROP TABLE photos;
        ALTER TABLE photos_new RENAME TO photos;
        CREATE INDEX IF NOT EXISTS idx_photos_toern ON photos(toern);
        """
    )


def get_photos_conn(db_path: Path) -> sqlite3.Connection:
    init_system_db(db_path)
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
    """Read GPS and capture time from EXIF when available (images)."""
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


def _parse_iso6709(text: str) -> tuple[float | None, float | None]:
    """GPS aus ISO-6709-String (typisch iPhone/Android in MP4/MOV)."""
    s = text.strip().strip("\x00")
    if not s:
        return None, None
    m = re.search(r"([+-]\d+(?:\.\d+)?)([+-]\d+(?:\.\d+)?)", s)
    if not m:
        return None, None
    try:
        return float(m.group(1)), float(m.group(2))
    except ValueError:
        return None, None


def _parse_mp4_date(raw: str) -> int | None:
    from datetime import datetime, timezone

    s = str(raw).strip()
    if not s:
        return None
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    m = re.match(r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})([+-]\d{2})(\d{2})$", s)
    if m:
        s = m.group(1) + m.group(2) + ":" + m.group(3)
    try:
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return int(dt.timestamp() * 1000)
    except ValueError:
        return None


def extract_video_metadata(file_path: Path) -> tuple[float | None, float | None, int | None]:
    """GPS/Zeit aus QuickTime-Metadaten (MP4/MOV), z. B. location.ISO6709."""
    try:
        from mutagen.mp4 import MP4
    except ImportError:
        return None, None, None

    try:
        mp4 = MP4(file_path)
    except Exception:
        return None, None, None

    tags = mp4.tags
    if not tags:
        return None, None, None

    lat = lon = None
    for key, values in tags.items():
        key_l = key.lower()
        if "location" not in key_l and key not in ("\xa9xyz",):
            continue
        items = values if isinstance(values, list) else [values]
        for val in items:
            if isinstance(val, bytes):
                val = val.decode("utf-8", errors="replace")
            la, lo = _parse_iso6709(str(val))
            if la is not None and lo is not None:
                lat, lon = la, lo
                break
        if lat is not None:
            break

    taken_ms = None
    if "\xa9day" in tags:
        raw = tags["\xa9day"][0]
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8", errors="replace")
        taken_ms = _parse_mp4_date(str(raw))

    return lat, lon, taken_ms


def extract_media_metadata(file_path: Path) -> tuple[float | None, float | None, int | None]:
    ext = file_path.suffix.lower()
    if ext in VIDEO_EXT:
        return extract_video_metadata(file_path)
    return extract_exif(file_path)


def is_video_filename(name: str) -> bool:
    return Path(name).suffix.lower() in VIDEO_EXT


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
    uploaded_by_user_id: int | None = None,
) -> tuple[StoredPhoto | None, str | None]:
    ext = Path(original_name).suffix.lower()
    if ext not in ALLOWED_EXT:
        return None, f"Dateityp nicht erlaubt: {ext}"

    toern_dir = photos_dir / str(toern)
    toern_dir.mkdir(parents=True, exist_ok=True)
    stored_name = f"{uuid.uuid4().hex}{ext}"
    dest = toern_dir / stored_name
    dest.write_bytes(file_bytes)

    exif_lat, exif_lon, taken_ms = extract_media_metadata(dest)
    use_lat = lat if lat is not None else exif_lat
    use_lon = lon if lon is not None else exif_lon

    if (use_lat is None or use_lon is None) and taken_ms and track:
        pt = nearest_track_point(taken_ms, track)
        if pt:
            use_lat, use_lon = pt

    if use_lat is None or use_lon is None:
        use_lat, use_lon = None, None

    photo = _insert_photo_row(
        db_path,
        toern,
        stored_name,
        original_name,
        title,
        float(use_lat) if use_lat is not None else None,
        float(use_lon) if use_lon is not None else None,
        taken_ms,
        uploaded_by_user_id,
    )
    return photo, None


def _resolve_photo_coords(
    file_path: Path,
    track: list[tuple[int, float, float]] | None,
) -> tuple[float | None, float | None, int | None]:
    exif_lat, exif_lon, taken_ms = extract_media_metadata(file_path)
    use_lat, use_lon = exif_lat, exif_lon
    if (use_lat is None or use_lon is None) and taken_ms and track:
        pt = nearest_track_point(taken_ms, track)
        if pt:
            use_lat, use_lon = pt
    if use_lat is not None and use_lon is not None:
        return float(use_lat), float(use_lon), taken_ms
    return None, None, taken_ms


def _insert_photo_row(
    db_path: Path,
    toern: int,
    filename: str,
    original_name: str,
    title: str,
    lat: float | None,
    lon: float | None,
    taken_at_ms: int | None,
    uploaded_by_user_id: int | None = None,
) -> StoredPhoto:
    now_ms = int(time.time() * 1000)
    with get_photos_conn(db_path) as conn:
        cur = conn.execute(
            """
            INSERT INTO photos
                (toern, filename, original_name, title, lat, lon, taken_at_ms,
                 created_at_ms, uploaded_by_user_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                toern,
                filename,
                original_name,
                title,
                lat,
                lon,
                taken_at_ms,
                now_ms,
                uploaded_by_user_id,
            ),
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
        uploaded_by_user_id=uploaded_by_user_id,
    )


def import_photos_from_folder(
    db_path: Path,
    photos_dir: Path,
    toern: int,
    track: list[tuple[int, float, float]] | None = None,
    *,
    refresh_existing: bool = False,
    uploaded_by_user_id: int | None = None,
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
            lat, lon, taken_ms = _resolve_photo_coords(file_path, track)
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

        lat, lon, taken_ms = _resolve_photo_coords(file_path, track)
        if lat is None or lon is None:
            warnings.append(
                f"{file_path.name}: ohne Koordinaten importiert (später unter Fotos bearbeiten)."
            )

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
            uploaded_by_user_id,
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
                   created_at_ms, uploaded_by_user_id
            FROM photos
            WHERE toern = ?
            ORDER BY COALESCE(taken_at_ms, created_at_ms), id
            """,
            (toern,),
        ).fetchall()
    return [_row_to_photo(r) for r in rows]


def _row_to_photo(r: sqlite3.Row) -> StoredPhoto:
    keys = r.keys()
    uploaded = None
    if "uploaded_by_user_id" in keys and r["uploaded_by_user_id"] is not None:
        uploaded = int(r["uploaded_by_user_id"])
    return StoredPhoto(
        id=int(r["id"]),
        toern=int(r["toern"]),
        filename=r["filename"],
        original_name=r["original_name"] or "",
        title=r["title"] or "",
        lat=float(r["lat"]) if r["lat"] is not None else None,
        lon=float(r["lon"]) if r["lon"] is not None else None,
        taken_at_ms=r["taken_at_ms"],
        uploaded_by_user_id=uploaded,
    )


def photo_to_map_json(p: StoredPhoto) -> dict[str, Any]:
    return {
        "id": p.id,
        "url": f"/api/photos/file/{p.id}",
        "thumbUrl": f"/api/photos/file/{p.id}?thumb=1",
        "title": p.title or p.original_name,
        "takenAtMs": p.taken_at_ms,
        "hasCoordinates": photo_has_coordinates(p),
        "isVideo": is_video_filename(p.filename),
    }


def photo_manage_dict(
    p: StoredPhoto,
    created_at_ms: int | None = None,
    *,
    can_edit: bool = False,
    uploaded_by_username: str | None = None,
) -> dict[str, Any]:
    return {
        "id": p.id,
        "toern": p.toern,
        "title": p.title,
        "originalName": p.original_name,
        "lat": p.lat if p.lat is not None else "",
        "lon": p.lon if p.lon is not None else "",
        "hasCoordinates": photo_has_coordinates(p),
        "takenAtMs": p.taken_at_ms,
        "createdAtMs": created_at_ms,
        "uploadedByUserId": p.uploaded_by_user_id,
        "uploadedBy": uploaded_by_username,
        "canEdit": can_edit,
        "isVideo": is_video_filename(p.filename),
        "thumbUrl": f"/api/photos/file/{p.id}?thumb=1",
        "url": f"/api/photos/file/{p.id}",
    }


def list_photos_manage(db_path: Path, toern: int) -> list[tuple[StoredPhoto, int | None]]:
    with get_photos_conn(db_path) as conn:
        rows = conn.execute(
            """
            SELECT id, toern, filename, original_name, title, lat, lon, taken_at_ms,
                   created_at_ms, uploaded_by_user_id
            FROM photos
            WHERE toern = ?
            ORDER BY COALESCE(taken_at_ms, created_at_ms) DESC, id DESC
            """,
            (toern,),
        ).fetchall()
    return [(_row_to_photo(r), r["created_at_ms"]) for r in rows]


def update_photo(
    db_path: Path,
    photo_id: int,
    *,
    title: str | None = None,
    lat: float | None = None,
    lon: float | None = None,
    clear_coordinates: bool = False,
) -> StoredPhoto | None:
    fields: list[str] = []
    values: list[Any] = []
    if title is not None:
        fields.append("title = ?")
        values.append(title)
    if clear_coordinates:
        fields.append("lat = NULL")
        fields.append("lon = NULL")
    else:
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
            SELECT id, toern, filename, original_name, title, lat, lon, taken_at_ms,
                   uploaded_by_user_id
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
    photos = [p for p in photos if photo_has_coordinates(p)]
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
                "photos": [photo_to_map_json(p) for p in c.photos],
            }
        )
    return out
