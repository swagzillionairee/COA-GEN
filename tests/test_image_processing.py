from __future__ import annotations

import io
import unittest
from unittest.mock import patch

from PIL import Image

from coa.image_processing import ImageValidationError, process_image_upload, validate_portable_image
from tests.helpers import jpeg_bytes, png_bytes


class ImageProcessingTests(unittest.TestCase):
    def test_transparent_logo_round_trip(self) -> None:
        image = process_image_upload(png_bytes(transparent=True), "wide.logo.png", "logo")
        self.assertEqual(image.media_type, "image/png")
        validate_portable_image(image, "logo")
        with Image.open(io.BytesIO(image.bytes())) as decoded:
            self.assertEqual(decoded.mode, "RGBA")

    def test_sample_jpeg_is_portable_and_small(self) -> None:
        image = process_image_upload(jpeg_bytes((1600, 1200)), "sample.jpg", "sample")
        self.assertLessEqual(len(image.bytes()), 1024 * 1024)
        self.assertEqual(image.caption, None)
        validate_portable_image(image, "sample")

    def test_signature_rejects_jpeg_content_despite_extension(self) -> None:
        with self.assertRaisesRegex(ImageValidationError, "decode as PNG"):
            process_image_upload(jpeg_bytes(), "signature.png", "signature")

    def test_corrupt_image_rejected(self) -> None:
        with self.assertRaises(ImageValidationError):
            process_image_upload(b"not an image", "bad.png", "logo")

    def test_original_size_limit_enforced(self) -> None:
        with self.assertRaisesRegex(ImageValidationError, "10 MB"):
            process_image_upload(b"0" * (10 * 1024 * 1024 + 1), "huge.png", "sample")

    def test_exif_orientation_is_applied_and_metadata_removed(self) -> None:
        source = Image.new("RGB", (80, 40), "#DCE7EA")
        exif = Image.Exif()
        exif[274] = 6
        buffer = io.BytesIO()
        source.save(buffer, format="JPEG", exif=exif)
        processed = process_image_upload(buffer.getvalue(), "rotated.jpg", "sample")
        self.assertEqual((processed.width, processed.height), (40, 80))
        with Image.open(io.BytesIO(processed.bytes())) as decoded:
            self.assertNotIn("exif", decoded.info)

    def test_decoded_pixel_limit_is_enforced(self) -> None:
        source = Image.new("RGB", (20, 20), "white")
        buffer = io.BytesIO()
        source.save(buffer, format="PNG")
        with patch("coa.image_processing.MAX_IMAGE_PIXELS", 100):
            with self.assertRaises(ImageValidationError):
                process_image_upload(buffer.getvalue(), "oversized.png", "sample")


if __name__ == "__main__":
    unittest.main()
