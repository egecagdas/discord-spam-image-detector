from __future__ import annotations

import io

from PIL import Image, ImageDraw


def bars_image(size: tuple[int, int] = (128, 128)) -> Image.Image:
    image = Image.new("RGB", size, "white")
    draw = ImageDraw.Draw(image)
    for y in range(0, size[1], 8):
        draw.rectangle([0, y, size[0], y + 3], fill="black")
    draw.rectangle([8, 8, 40, 40], fill="red")
    return image


def circle_image(size: tuple[int, int] = (128, 128)) -> Image.Image:
    image = Image.new("RGB", size, "navy")
    draw = ImageDraw.Draw(image)
    draw.ellipse([16, 16, size[0] - 16, size[1] - 16], fill="yellow")
    draw.polygon([(64, 10), (90, 110), (20, 80)], fill="magenta")
    return image


def image_to_png_bytes(image: Image.Image) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def image_to_jpeg_bytes(image: Image.Image, quality: int = 40) -> bytes:
    buffer = io.BytesIO()
    image.convert("RGB").save(buffer, format="JPEG", quality=quality)
    return buffer.getvalue()
