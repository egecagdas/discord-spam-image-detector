from __future__ import annotations

import io
import threading
from dataclasses import dataclass

from PIL import Image, ImageFile, UnidentifiedImageError

_IMAGE_LOCK = threading.Lock()

ImageFile.LOAD_TRUNCATED_IMAGES = False

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".avif"}
IMAGE_CONTENT_TYPES = {
    "image/png",
    "image/jpeg",
    "image/jpg",
    "image/webp",
    "image/gif",
    "image/bmp",
    "image/avif",
}


class ImageTooLargeError(Exception):
    """Image exceeded configured pixel or byte limits."""


class InvalidImageError(Exception):
    """Bytes could not be decoded as an image."""


@dataclass(frozen=True)
class ImageCandidate:
    source: str
    filename: str
    data: bytes


def is_image_filename(filename: str) -> bool:
    lower = filename.lower()
    return any(lower.endswith(ext) for ext in IMAGE_EXTENSIONS)


def is_image_content_type(content_type: str | None) -> bool:
    if not content_type:
        return False
    return content_type.split(";")[0].strip().lower() in IMAGE_CONTENT_TYPES


def image_from_bytes(data: bytes, max_pixels: int) -> Image.Image:
    if not data:
        raise InvalidImageError("empty image payload")

    with _IMAGE_LOCK:
        previous = Image.MAX_IMAGE_PIXELS
        Image.MAX_IMAGE_PIXELS = max_pixels
        try:
            with Image.open(io.BytesIO(data)) as img:
                img.load()
                return img.convert("RGB")
        except Image.DecompressionBombError as exc:
            raise ImageTooLargeError(str(exc)) from exc
        except UnidentifiedImageError as exc:
            raise InvalidImageError("not a recognized image") from exc
        except ImageTooLargeError:
            raise
        except Exception as exc:
            raise InvalidImageError(str(exc)) from exc
        finally:
            Image.MAX_IMAGE_PIXELS = previous


def jpeg_thumbnail(data: bytes, max_pixels: int, max_side: int = 320) -> bytes:
    image = image_from_bytes(data, max_pixels)
    image.thumbnail((max_side, max_side))
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=85)
    return buffer.getvalue()
