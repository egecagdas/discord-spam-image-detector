from __future__ import annotations

from spam_detector.hasher import hamming_distance, phash_bytes, phash_image
from spam_detector.images import InvalidImageError, image_from_bytes

from helpers import bars_image, circle_image, image_to_jpeg_bytes, image_to_png_bytes

MAX_PIXELS = 1_000_000


def test_identical_images_have_zero_distance() -> None:
    image = bars_image()
    left = phash_image(image)
    right = phash_image(image.copy())
    assert hamming_distance(left, right) == 0


def test_jpeg_recompress_stays_within_threshold() -> None:
    original = bars_image()
    png_hash = phash_bytes(image_to_png_bytes(original), max_pixels=MAX_PIXELS)
    jpeg_hash = phash_bytes(image_to_jpeg_bytes(original, quality=35), max_pixels=MAX_PIXELS)
    assert hamming_distance(png_hash, jpeg_hash) <= 10


def test_unrelated_images_exceed_threshold() -> None:
    bars_hash = phash_image(bars_image())
    circle_hash = phash_image(circle_image())
    assert hamming_distance(bars_hash, circle_hash) > 10


def test_phash_bytes_round_trip() -> None:
    data = image_to_png_bytes(bars_image())
    assert phash_bytes(data, max_pixels=MAX_PIXELS) == phash_image(image_from_bytes(data, MAX_PIXELS))


def test_invalid_bytes_raise() -> None:
    try:
        phash_bytes(b"not-an-image", max_pixels=MAX_PIXELS)
    except InvalidImageError:
        return
    raise AssertionError("expected InvalidImageError")
