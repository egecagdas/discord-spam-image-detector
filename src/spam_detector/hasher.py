from __future__ import annotations

import imagehash
from PIL import Image

from spam_detector.images import image_from_bytes


def phash_image(image: Image.Image, hash_size: int = 8) -> str:
    return str(imagehash.phash(image, hash_size=hash_size))


def phash_bytes(data: bytes, max_pixels: int, hash_size: int = 8) -> str:
    image = image_from_bytes(data, max_pixels=max_pixels)
    return phash_image(image, hash_size=hash_size)


def hamming_distance(left: str, right: str) -> int:
    return imagehash.hex_to_hash(left) - imagehash.hex_to_hash(right)
