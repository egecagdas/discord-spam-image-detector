from __future__ import annotations

import json
import logging
import re
import uuid
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path

from spam_detector.hasher import hamming_distance
from spam_detector.images import IMAGE_EXTENSIONS

log = logging.getLogger(__name__)

_UNSAFE_NAME = re.compile(r"[^\w.\-]+", re.UNICODE)


@dataclass
class HashEntry:
    id: str
    name: str
    filename: str
    phash: str


@dataclass(frozen=True)
class Match:
    entry: HashEntry
    distance: int
    pool: str = "server"


class HashStore:
    def __init__(self, hashes_path: Path, images_dir: Path) -> None:
        self.hashes_path = hashes_path
        self.images_dir = images_dir
        self.entries: list[HashEntry] = []

    def ensure_dirs(self) -> None:
        self.images_dir.mkdir(parents=True, exist_ok=True)
        self.hashes_path.parent.mkdir(parents=True, exist_ok=True)

    def load(self) -> None:
        self.ensure_dirs()
        if not self.hashes_path.exists():
            self.entries = []
            return
        try:
            payload = json.loads(self.hashes_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            log.exception("Failed to read hash store at %s", self.hashes_path)
            self.entries = []
            return
        raw_entries = payload.get("entries", []) if isinstance(payload, dict) else []
        self.entries = [
            HashEntry(
                id=str(item["id"]),
                name=str(item["name"]),
                filename=str(item["filename"]),
                phash=str(item["phash"]),
            )
            for item in raw_entries
            if isinstance(item, dict) and {"id", "name", "filename", "phash"} <= item.keys()
        ]
        log.info("Loaded %s spam hashes from %s", len(self.entries), self.hashes_path)

    def save(self) -> None:
        self.ensure_dirs()
        payload = {"entries": [asdict(entry) for entry in self.entries]}
        self.hashes_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    def closest(self, phash: str) -> Match | None:
        best: Match | None = None
        for entry in self.entries:
            try:
                distance = hamming_distance(phash, entry.phash)
            except ValueError:
                log.warning("Skipping invalid stored hash for %s", entry.name)
                continue
            if best is None or distance < best.distance:
                best = Match(entry=entry, distance=distance)
        return best

    def find_match(self, phash: str, threshold: int) -> Match | None:
        best = self.closest(phash)
        if best is None or best.distance > threshold:
            return None
        return best

    def add(self, name: str, filename: str, phash: str, data: bytes) -> HashEntry:
        self.ensure_dirs()
        dest_name = unique_filename(self.images_dir, sanitize_filename(filename))
        dest = self.images_dir / dest_name
        dest.write_bytes(data)
        entry = HashEntry(
            id=_new_id({e.id for e in self.entries}),
            name=name or Path(dest_name).stem,
            filename=dest_name,
            phash=phash,
        )
        self.entries.append(entry)
        self.save()
        return entry

    def remove(self, name: str) -> HashEntry | None:
        needle = name.casefold()
        for index, entry in enumerate(self.entries):
            if entry.name.casefold() == needle or entry.filename.casefold() == needle or entry.id == name:
                removed = self.entries.pop(index)
                path = self.images_dir / removed.filename
                if path.exists():
                    path.unlink()
                self.save()
                return removed
        return None

    def reload_from_disk(self, hash_file: Callable[[Path], str]) -> int:
        self.ensure_dirs()
        existing_by_filename = {entry.filename: entry for entry in self.entries}
        rebuilt: list[HashEntry] = []
        used_ids = set()
        for path in sorted(self.images_dir.iterdir()):
            if not path.is_file() or path.suffix.lower() not in IMAGE_EXTENSIONS:
                continue
            phash = hash_file(path)
            previous = existing_by_filename.get(path.name)
            entry_id = previous.id if previous and previous.id not in used_ids else _new_id(used_ids)
            used_ids.add(entry_id)
            rebuilt.append(
                HashEntry(
                    id=entry_id,
                    name=previous.name if previous else path.stem,
                    filename=path.name,
                    phash=phash,
                )
            )
        self.entries = rebuilt
        self.save()
        log.info("Reloaded %s spam hashes from %s", len(self.entries), self.images_dir)
        return len(self.entries)


class StoreManager:
    def __init__(self, data_dir: Path) -> None:
        self.data_dir = data_dir
        self.global_store = HashStore(data_dir / "hashes.json", data_dir / "spam_images")
        self._guild_stores: dict[int, HashStore] = {}

    def load(self) -> None:
        self.global_store.load()
        guilds_dir = self.data_dir / "guilds"
        if not guilds_dir.is_dir():
            return
        for child in guilds_dir.iterdir():
            if child.is_dir() and child.name.isdigit():
                self.guild_store(int(child.name))

    def guild_store(self, guild_id: int) -> HashStore:
        store = self._guild_stores.get(guild_id)
        if store is None:
            root = self.data_dir / "guilds" / str(guild_id)
            store = HashStore(root / "hashes.json", root / "spam_images")
            store.load()
            self._guild_stores[guild_id] = store
        return store

    def has_hashes(self, guild_id: int) -> bool:
        return bool(self.global_store.entries or self.guild_store(guild_id).entries)

    def closest(self, guild_id: int, phash: str) -> Match | None:
        matches: list[Match] = []
        local = self.guild_store(guild_id).closest(phash)
        if local is not None:
            matches.append(Match(entry=local.entry, distance=local.distance, pool="server"))
        shared = self.global_store.closest(phash)
        if shared is not None:
            matches.append(Match(entry=shared.entry, distance=shared.distance, pool="global"))
        if not matches:
            return None
        return min(matches, key=lambda item: (item.distance, 0 if item.pool == "server" else 1))


def sanitize_filename(name: str) -> str:
    cleaned = _UNSAFE_NAME.sub("_", Path(name).name).strip("._")
    return cleaned or "spam.png"


def unique_filename(directory: Path, filename: str) -> str:
    candidate = filename
    stem = Path(filename).stem
    suffix = Path(filename).suffix or ".png"
    index = 1
    while (directory / candidate).exists():
        candidate = f"{stem}_{index}{suffix}"
        index += 1
    return candidate


class GuildSettingsStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._alert_channels: dict[int, int] = {}

    def load(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self._alert_channels = {}
            return
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            log.exception("Failed to read guild settings at %s", self.path)
            self._alert_channels = {}
            return
        raw_guilds = payload.get("guilds", {}) if isinstance(payload, dict) else {}
        alert_channels: dict[int, int] = {}
        if isinstance(raw_guilds, dict):
            for guild_id, settings in raw_guilds.items():
                if not isinstance(settings, dict):
                    continue
                channel_id = settings.get("alert_channel_id")
                try:
                    alert_channels[int(guild_id)] = int(channel_id)
                except (TypeError, ValueError):
                    continue
        self._alert_channels = alert_channels
        log.info("Loaded settings for %s guild(s)", len(self._alert_channels))

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "guilds": {
                str(guild_id): {"alert_channel_id": channel_id}
                for guild_id, channel_id in sorted(self._alert_channels.items())
            }
        }
        self.path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    def get_alert_channel_id(self, guild_id: int) -> int | None:
        return self._alert_channels.get(guild_id)

    def set_alert_channel_id(self, guild_id: int, channel_id: int) -> None:
        self._alert_channels[guild_id] = channel_id
        self.save()


def _new_id(used: set[str]) -> str:
    for _ in range(16):
        value = uuid.uuid4().hex[:8]
        if value not in used:
            return value
    raise RuntimeError("Could not allocate a unique hash entry id")
