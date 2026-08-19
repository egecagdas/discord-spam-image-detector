from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATA_DIR = REPO_ROOT / "data"


def _require(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def _optional_int(name: str) -> int | None:
    raw = os.getenv(name, "").strip()
    if not raw:
        return None
    return int(raw)


@dataclass(frozen=True)
class Config:
    token: str
    hash_threshold: int = 10
    hash_size: int = 8
    max_image_bytes: int = 10 * 1024 * 1024
    max_image_pixels: int = 40_000_000
    download_timeout: float = 15.0
    download_concurrency: int = 4
    admin_role_id: int | None = None
    data_dir: Path = DEFAULT_DATA_DIR

    @property
    def images_dir(self) -> Path:
        return self.data_dir / "spam_images"

    @property
    def hashes_path(self) -> Path:
        return self.data_dir / "hashes.json"

    @property
    def guilds_dir(self) -> Path:
        return self.data_dir / "guilds"

    @property
    def guild_settings_path(self) -> Path:
        return self.data_dir / "guild_settings.json"

    @classmethod
    def from_env(cls, dotenv_path: Path | None = None) -> Config:
        load_dotenv(dotenv_path or REPO_ROOT / ".env")
        data_dir_raw = os.getenv("DATA_DIR", "").strip()
        data_dir = Path(data_dir_raw) if data_dir_raw else DEFAULT_DATA_DIR
        return cls(
            token=_require("DISCORD_TOKEN"),
            hash_threshold=int(os.getenv("HASH_THRESHOLD", "10")),
            hash_size=int(os.getenv("HASH_SIZE", "8")),
            max_image_bytes=int(os.getenv("MAX_IMAGE_BYTES", str(10 * 1024 * 1024))),
            max_image_pixels=int(os.getenv("MAX_IMAGE_PIXELS", str(40_000_000))),
            download_timeout=float(os.getenv("DOWNLOAD_TIMEOUT", "15")),
            download_concurrency=int(os.getenv("DOWNLOAD_CONCURRENCY", "4")),
            admin_role_id=_optional_int("ADMIN_ROLE_ID"),
            data_dir=data_dir,
        )
