"""Load geotagged photos from public Google Photos share albums."""

from __future__ import annotations

import hashlib
import json
import logging
import math
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests

logger = logging.getLogger(__name__)

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)

GOOGLE_PHOTO_URL = re.compile(
    r"https://lh3\.googleusercontent\.com/[a-zA-Z0-9\-_=/]+"
)
# Unix ms in embedded album JSON (photo taken / added time)
EPOCH_MS = re.compile(r"\[\s*(\d{13})\s*\]")


@dataclass
class PhotoItem:
    id: str
    url: str
    taken_at_ms: int | None = None
    title: str = ""
    lat: float | None = None
    lon: float | None = None
    location_source: str = ""
    album_url: str = ""


@dataclass
class PhotoCluster:
    id: str
    lat: float
    lon: float
    photos: list[PhotoItem] = field(default_factory=list)


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def thumb_url(url: str, size: int = 240) -> str:
    base = url.split("=")[0]
    return f"{base}=w{size}-h{size}-c"


def display_url(url: str, width: int = 1200) -> str:
    base = url.split("=")[0]
    return f"{base}=w{width}"


def _photo_id(url: str) -> str:
    return hashlib.sha256(url.encode()).hexdigest()[:16]


def _normalize_album_url(url: str) -> str:
    url = url.strip()
    if not url:
        raise ValueError("Leerer Album-Link")
    parsed = urlparse(url)
    if "google" not in parsed.netloc and "goo.gl" not in parsed.netloc:
        raise ValueError(f"Kein Google-Photos-Link: {url}")
    return url


def fetch_shared_album(album_url: str, session: requests.Session | None = None) -> list[PhotoItem]:
    """Extract image URLs (+ timestamps wenn in der Seite vorhanden) aus einem Teilen-Link."""
    album_url = _normalize_album_url(album_url)
    sess = session or requests.Session()
    resp = sess.get(
        album_url,
        headers={"User-Agent": USER_AGENT, "Accept-Language": "de-DE,de;q=0.9,en;q=0.8"},
        timeout=45,
        allow_redirects=True,
    )
    resp.raise_for_status()
    html = resp.text

    raw_urls = GOOGLE_PHOTO_URL.findall(html)
    # Dedupe preserving order; drop very short noise
    seen: set[str] = set()
    urls: list[str] = []
    for u in raw_urls:
        u = u.rstrip("\\")
        if len(u) < 80 or u in seen:
            continue
        seen.add(u)
        urls.append(u)

    if len(urls) >= 2:
        # Erstes/letztes Bild ist oft Album-Cover
        urls = urls[1:-1] if len(urls) > 2 else urls

    epochs = [int(m) for m in EPOCH_MS.findall(html)]
    # Plausible photo timestamps (2000–2035)
    epochs = [e for e in epochs if 946_684_800_000 <= e <= 2_050_000_000_000]
    epochs = sorted(set(epochs))

    items: list[PhotoItem] = []
    for i, url in enumerate(urls):
        taken = epochs[i] if i < len(epochs) else None
        items.append(
            PhotoItem(
                id=_photo_id(url),
                url=url,
                taken_at_ms=taken,
                album_url=album_url,
            )
        )

    logger.info("Album %s: %d Bilder gefunden", album_url, len(items))
    return items


def load_config(config_path: Path) -> dict[str, Any]:
    if not config_path.is_file():
        return {"clusterRadiusMeters": 250, "toerns": {}, "manualPhotos": []}
    with config_path.open(encoding="utf-8") as f:
        return json.load(f)


def cache_path(cache_dir: Path, album_url: str) -> Path:
    key = hashlib.sha256(album_url.encode()).hexdigest()[:20]
    return cache_dir / f"album_{key}.json"


def fetch_album_cached(
    album_url: str,
    cache_dir: Path,
    ttl_seconds: int = 3600,
) -> list[PhotoItem]:
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = cache_path(cache_dir, album_url)
    now = time.time()
    if path.is_file() and now - path.stat().st_mtime < ttl_seconds:
        data = json.loads(path.read_text(encoding="utf-8"))
        return [
            PhotoItem(
                id=p["id"],
                url=p["url"],
                taken_at_ms=p.get("takenAtMs"),
                title=p.get("title") or "",
                lat=p.get("lat"),
                lon=p.get("lon"),
                location_source=p.get("locationSource") or "",
                album_url=p.get("albumUrl") or album_url,
            )
            for p in data.get("photos", [])
        ]

    photos = fetch_shared_album(album_url)
    payload = {
        "albumUrl": album_url,
        "fetchedAt": int(now),
        "photos": [
            {
                "id": p.id,
                "url": p.url,
                "takenAtMs": p.taken_at_ms,
                "title": p.title,
                "albumUrl": p.album_url,
            }
            for p in photos
        ],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return photos


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


def assign_locations_from_track(
    photos: list[PhotoItem],
    track: list[tuple[int, float, float]],
) -> tuple[list[PhotoItem], list[str]]:
    warnings: list[str] = []
    placed: list[PhotoItem] = []
    for p in photos:
        if p.lat is not None and p.lon is not None:
            placed.append(p)
            continue
        if p.taken_at_ms is None:
            warnings.append(f"Foto ohne Zeitstempel übersprungen ({p.id[:8]}…)")
            continue
        pt = nearest_track_point(p.taken_at_ms, track)
        if pt is None:
            warnings.append(
                f"Kein Track-Punkt nahe Aufnahmezeit ({p.id[:8]}…)"
            )
            continue
        p.lat, p.lon = pt
        p.location_source = "track_time_match"
        placed.append(p)
    return placed, warnings


def cluster_photos(photos: list[PhotoItem], radius_m: float) -> list[PhotoCluster]:
    clusters: list[PhotoCluster] = []
    for photo in photos:
        if photo.lat is None or photo.lon is None:
            continue
        target: PhotoCluster | None = None
        for cluster in clusters:
            if haversine_m(photo.lat, photo.lon, cluster.lat, cluster.lon) <= radius_m:
                target = cluster
                break
        if target is None:
            cid = f"c_{len(clusters) + 1}"
            clusters.append(
                PhotoCluster(id=cid, lat=photo.lat, lon=photo.lon, photos=[photo])
            )
            continue
        target.photos.append(photo)
        n = len(target.photos)
        target.lat = sum(p.lat for p in target.photos if p.lat is not None) / n
        target.lon = sum(p.lon for p in target.photos if p.lon is not None) / n

    return clusters


def load_photos_for_toern(
    toern_id: int,
    config: dict[str, Any],
    track: list[tuple[int, float, float]],
    cache_dir: Path,
) -> tuple[list[PhotoCluster], list[str], dict[str, Any]]:
    radius = float(config.get("clusterRadiusMeters", 250))
    ttl = int(config.get("cacheTtlSeconds", 3600))
    toern_cfg = (config.get("toerns") or {}).get(str(toern_id), {})
    album_urls = toern_cfg.get("albums") or []
    if isinstance(album_urls, str):
        album_urls = [album_urls]

    all_photos: list[PhotoItem] = []
    warnings: list[str] = []
    session = requests.Session()

    for url in album_urls:
        try:
            items = fetch_album_cached(url, cache_dir, ttl_seconds=ttl)
            all_photos.extend(items)
        except Exception as exc:  # noqa: BLE001 - surfaced to client as warning
            warnings.append(f"Album fehlgeschlagen ({url}): {exc}")
            logger.exception("Album fetch failed: %s", url)

    for entry in config.get("manualPhotos") or []:
        if int(entry.get("toern", -1)) != toern_id:
            continue
        lat, lon = entry.get("lat"), entry.get("lon")
        img = entry.get("url") or entry.get("imageUrl")
        if lat is None or lon is None or not img:
            continue
        all_photos.append(
            PhotoItem(
                id=_photo_id(str(img) + str(lat) + str(lon)),
                url=str(img),
                lat=float(lat),
                lon=float(lon),
                title=str(entry.get("title") or ""),
                taken_at_ms=entry.get("takenAtMs"),
                location_source="manual",
            )
        )

    located, loc_warnings = assign_locations_from_track(all_photos, track)
    warnings.extend(loc_warnings)

    clusters = cluster_photos(located, radius)
    meta = {
        "clusterRadiusMeters": radius,
        "photoCount": len(all_photos),
        "placedCount": len(located),
        "clusterCount": len(clusters),
        "albums": album_urls,
    }
    return clusters, warnings, meta


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
                        "url": display_url(p.url),
                        "thumbUrl": thumb_url(p.url),
                        "title": p.title,
                        "takenAtMs": p.taken_at_ms,
                        "locationSource": p.location_source,
                        "albumUrl": p.album_url,
                    }
                    for p in c.photos
                ],
            }
        )
    return out
