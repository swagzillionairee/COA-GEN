from __future__ import annotations

import io

from PIL import Image, ImageDraw

from coa.image_processing import process_image_upload
from coa.models import PortableImage


def png_bytes(size: tuple[int, int] = (320, 180), transparent: bool = False) -> bytes:
    mode = "RGBA" if transparent else "RGB"
    background = (255, 255, 255, 0) if transparent else "#E8EEF1"
    image = Image.new(mode, size, background)
    draw = ImageDraw.Draw(image)
    draw.rectangle((20, 20, size[0] - 20, size[1] - 20), fill="#F6E7A5", outline="#173F4F", width=4)
    output = io.BytesIO()
    image.save(output, format="PNG", pnginfo=None)
    return output.getvalue()


def jpeg_bytes(size: tuple[int, int] = (320, 180)) -> bytes:
    image = Image.new("RGB", size, "#DCE7EA")
    output = io.BytesIO()
    image.save(output, format="JPEG", quality=85)
    return output.getvalue()


def portable_sample() -> PortableImage:
    return process_image_upload(png_bytes(), "sample.png", "sample", caption="Sample as received")


def portable_logo() -> PortableImage:
    return process_image_upload(png_bytes((420, 120), transparent=True), "logo.png", "logo")


def portable_signature() -> PortableImage:
    return process_image_upload(png_bytes((420, 100), transparent=True), "signature.png", "signature")
