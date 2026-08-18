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
        log.info("Loaded %s spam hashes", len(self.entries))

    def save(self) -> None:
        self.ensure_dirs()
        payload = {"entries": [asdict(entry) for entry in self.entries]}
        self.hashes_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    def find_match(self, phash: str, threshold: int) -> Match | None:
        best: Match | None = None
        for entry in self.entries:
            try:
                distance = hamming_distance(phash, entry.phash)
            except ValueError:
                log.warning("Skipping invalid stored hash for %s", entry.name)
                continue
            if distance > threshold:
                continue
            if best is None or distance < best.distance:
                best = Match(entry=entry, distance=distance)
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


def _new_id(used: set[str]) -> str:
    for _ in range(16):
        value = uuid.uuid4().hex[:8]
        if value not in used:
            return value
    raise RuntimeError("Could not allocate a unique hash entry id")
