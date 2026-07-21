"""Safe, portable processing for logos, samples, and authorized signatures."""

from __future__ import annotations

import base64
import hashlib
import io
from typing import Literal

from PIL import Image, ImageOps, UnidentifiedImageError

from .constants import (
    MAX_IMAGE_PIXELS,
    MAX_ORIGINAL_IMAGE_BYTES,
    MAX_PROCESSED_IMAGE_BYTES,
)
from .models import PortableImage


class ImageValidationError(ValueError):
    pass


Purpose = Literal["logo", "sample", "signature"]


def _detected_media_type(image: Image.Image) -> str:
    formats = {"PNG": "image/png", "JPEG": "image/jpeg", "WEBP": "image/webp"}
    try:
        return formats[image.format or ""]
    except KeyError as exc:
        raise ImageValidationError("Only decoded PNG, JPEG, and WebP images are supported") from exc


def _has_alpha(image: Image.Image) -> bool:
    return image.mode in ("RGBA", "LA") or (
        image.mode == "P" and "transparency" in image.info
    )


def _save_processed(image: Image.Image, prefer_png: bool) -> tuple[bytes, str]:
    longest = 1600
    working = image.copy()
    working.thumbnail((longest, longest), Image.Resampling.LANCZOS)

    for max_dimension in (1600, 1400, 1200, 1000, 800, 640):
        candidate = working.copy()
        candidate.thumbnail((max_dimension, max_dimension), Image.Resampling.LANCZOS)
        if prefer_png:
            if candidate.mode not in ("RGB", "RGBA"):
                candidate = candidate.convert("RGBA")
            buffer = io.BytesIO()
            candidate.save(buffer, format="PNG", optimize=True, compress_level=9)
            payload = buffer.getvalue()
            media_type = "image/png"
        else:
            if candidate.mode != "RGB":
                background = Image.new("RGB", candidate.size, "white")
                if _has_alpha(candidate):
                    background.paste(candidate.convert("RGBA"), mask=candidate.convert("RGBA").getchannel("A"))
                else:
                    background.paste(candidate.convert("RGB"))
                candidate = background
            payload = b""
            for quality in (90, 84, 76, 68):
                buffer = io.BytesIO()
                candidate.save(buffer, format="JPEG", quality=quality, optimize=True, progressive=True)
                payload = buffer.getvalue()
                if len(payload) <= MAX_PROCESSED_IMAGE_BYTES:
                    break
            media_type = "image/jpeg"
        if len(payload) <= MAX_PROCESSED_IMAGE_BYTES:
            return payload, media_type
    raise ImageValidationError("Image cannot be processed below the 1 MB portable-scenario limit")


def process_image_upload(
    content: bytes,
    filename: str,
    purpose: Purpose,
    *,
    caption: str | None = None,
    crop_position: Literal["center", "top", "bottom", "left", "right"] = "center",
) -> PortableImage:
    """Decode, orient, resize, strip metadata, hash, and embed an upload."""

    if not content:
        raise ImageValidationError("The uploaded image is empty")
    if len(content) > MAX_ORIGINAL_IMAGE_BYTES:
        raise ImageValidationError("Original image exceeds the 10 MB upload limit")

    previous_limit = Image.MAX_IMAGE_PIXELS
    Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS
    try:
        with Image.open(io.BytesIO(content)) as opened:
            detected_media = _detected_media_type(opened)
            if purpose == "signature" and detected_media != "image/png":
                raise ImageValidationError("Signature images must decode as PNG")
            width, height = opened.size
            if width * height > MAX_IMAGE_PIXELS:
                raise ImageValidationError("Decoded image exceeds the 20 megapixel limit")
            if width > 20_000 or height > 20_000:
                raise ImageValidationError("Decoded image dimensions are unsafe")
            opened.load()
            oriented = ImageOps.exif_transpose(opened)
            transparent = _has_alpha(oriented)
            normalized = oriented.convert("RGBA" if transparent or purpose in {"logo", "signature"} else "RGB")
    except Image.DecompressionBombError as exc:
        raise ImageValidationError("Image dimensions trigger decompression-bomb protection") from exc
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        if isinstance(exc, ImageValidationError):
            raise
        raise ImageValidationError("Image is corrupt or uses an unsupported encoding") from exc
    finally:
        Image.MAX_IMAGE_PIXELS = previous_limit

    prefer_png = purpose in {"logo", "signature"} or transparent
    payload, media_type = _save_processed(normalized, prefer_png)
    with Image.open(io.BytesIO(payload)) as checked:
        processed_width, processed_height = checked.size

    return PortableImage(
        filename=filename,
        media_type=media_type,
        width=processed_width,
        height=processed_height,
        content_base64=base64.b64encode(payload).decode("ascii"),
        sha256=hashlib.sha256(payload).hexdigest(),
        caption=caption,
        crop_position=crop_position,
    )


def validate_portable_image(image: PortableImage, purpose: Purpose) -> None:
    """Re-decode embedded bytes so scenario import never trusts metadata alone."""

    try:
        with Image.open(io.BytesIO(image.bytes())) as decoded:
            media_type = _detected_media_type(decoded)
            if purpose == "signature" and media_type != "image/png":
                raise ImageValidationError("Signature images must decode as PNG")
            if media_type != image.media_type:
                raise ImageValidationError("Embedded image media type does not match decoded content")
            if decoded.size != (image.width, image.height):
                raise ImageValidationError("Embedded image dimensions do not match decoded content")
            if decoded.width * decoded.height > MAX_IMAGE_PIXELS:
                raise ImageValidationError("Embedded image exceeds the 20 megapixel limit")
            decoded.load()
    except (UnidentifiedImageError, OSError) as exc:
        raise ImageValidationError("Embedded image is corrupt") from exc
