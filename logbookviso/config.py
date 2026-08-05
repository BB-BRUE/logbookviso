"""Zentrale Konfiguration aus Umgebungsvariablen (lokal, Docker, Gunicorn)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

# Projektroot (Ordner über logbookviso/)
ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Settings:
    """Laufzeit-Konfiguration; Werte kommen aus ENV oder sinnvolle Dev-Defaults."""

    system_db: Path
    photos_dir: Path
    logbook_upload_dir: Path
    static_dir: Path
    max_upload_mb: int
    secret_key: str
    init_admin_user: str
    init_admin_password: str

    @classmethod
    def from_env(cls) -> Settings:
        system_db = Path(os.environ.get("SYSTEM_DB", str(ROOT / "data/system.sqlite")))
        photos_dir = Path(os.environ.get("PHOTOS_DIR", str(ROOT / "data/photos")))
        upload_default = system_db.parent / "logbook_uploads"
        logbook_upload_dir = Path(
            os.environ.get("LOGBOOK_UPLOAD_DIR", str(upload_default))
        )
        return cls(
            system_db=system_db,
            photos_dir=photos_dir,
            logbook_upload_dir=logbook_upload_dir,
            static_dir=ROOT / "static",
            max_upload_mb=int(os.environ.get("MAX_UPLOAD_MB", "256")),
            secret_key=os.environ.get("SECRET_KEY", "dev-change-me-in-production"),
            init_admin_user=os.environ.get("INIT_ADMIN_USER", "admin"),
            init_admin_password=os.environ.get("INIT_ADMIN_PASSWORD", "admin"),
        )


settings = Settings.from_env()
