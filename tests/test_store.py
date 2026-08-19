from __future__ import annotations

from pathlib import Path

from spam_detector.hasher import phash_bytes
from spam_detector.images import InvalidImageError, image_from_bytes
from spam_detector.store import HashStore

from helpers import bars_image, circle_image, image_to_jpeg_bytes, image_to_png_bytes

MAX_PIXELS = 1_000_000


def _store(tmp_path: Path) -> HashStore:
    store = HashStore(tmp_path / "hashes.json", tmp_path / "spam_images")
    store.ensure_dirs()
    return store


def test_add_and_match_identical(tmp_path: Path) -> None:
    store = _store(tmp_path)
    data = image_to_png_bytes(bars_image())
    phash = phash_bytes(data, max_pixels=MAX_PIXELS)
    store.add("bars", "bars.png", phash, data)

    match = store.find_match(phash, threshold=10)
    assert store.closest(phash) is not None
    assert match is not None
    assert match.entry.name == "bars"
    assert match.distance == 0


def test_match_jpeg_recompress(tmp_path: Path) -> None:
    store = _store(tmp_path)
    original = bars_image()
    png = image_to_png_bytes(original)
    store.add("bars", "bars.png", phash_bytes(png, max_pixels=MAX_PIXELS), png)

    jpeg_hash = phash_bytes(image_to_jpeg_bytes(original, quality=35), max_pixels=MAX_PIXELS)
    match = store.find_match(jpeg_hash, threshold=10)
    assert match is not None
    assert match.entry.name == "bars"


def test_unrelated_image_does_not_match(tmp_path: Path) -> None:
    store = _store(tmp_path)
    bars = image_to_png_bytes(bars_image())
    store.add("bars", "bars.png", phash_bytes(bars, max_pixels=MAX_PIXELS), bars)

    other = phash_bytes(image_to_png_bytes(circle_image()), max_pixels=MAX_PIXELS)
    assert store.find_match(other, threshold=10) is None


def test_remove_and_reload(tmp_path: Path) -> None:
    store = _store(tmp_path)
    bars = image_to_png_bytes(bars_image())
    circles = image_to_png_bytes(circle_image())
    store.add("bars", "bars.png", phash_bytes(bars, max_pixels=MAX_PIXELS), bars)
    store.add("circles", "circles.png", phash_bytes(circles, max_pixels=MAX_PIXELS), circles)

    removed = store.remove("bars")
    assert removed is not None
    assert len(store.entries) == 1
    assert not (store.images_dir / removed.filename).exists()

    (store.images_dir / "dropped.png").write_bytes(bars)
    count = store.reload_from_disk(lambda path: phash_bytes(path.read_bytes(), max_pixels=MAX_PIXELS))
    names = {entry.name for entry in store.entries}
    assert count == 2
    assert "dropped" in names
    assert "circles" in names


def test_load_persists(tmp_path: Path) -> None:
    store = _store(tmp_path)
    data = image_to_png_bytes(bars_image())
    store.add("bars", "bars.png", phash_bytes(data, max_pixels=MAX_PIXELS), data)

    reloaded = HashStore(store.hashes_path, store.images_dir)
    reloaded.load()
    assert len(reloaded.entries) == 1
    assert reloaded.entries[0].name == "bars"


def test_image_from_bytes_rejects_garbage() -> None:
    try:
        image_from_bytes(b"nope", max_pixels=MAX_PIXELS)
    except InvalidImageError:
        return
    raise AssertionError("expected InvalidImageError")
