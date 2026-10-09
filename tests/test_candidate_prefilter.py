"""
Comprehensive unit tests for Candidate Pre-Filter.
Verifies:
  1. Valid normal product image -> accepted
  2. Corrupt / unreadable image payload -> rejected (corrupted_or_unreadable)
  3. Very tiny image (< MIN_IMAGE_WIDTH/HEIGHT or area < 20,000) -> rejected (dimensions_below_minimum)
  4. Extreme banner aspect ratio (5:1, 8:1) -> rejected (extreme_aspect_ratio_horizontal_banner)
  5. Normal portrait product image (3:4, 9:16, 1:2.5) -> accepted
  6. Normal landscape product image (4:3, 16:9, 2.5:1) -> accepted
  7. Square product image (1:1) -> accepted
  8. Borderline aspect ratio (3.0:1 landscape, 0.33:1 portrait) -> accepted with shape flags
  9. Extreme vertical skyscraper (1:5, 1:8) -> rejected (extreme_aspect_ratio_vertical_skyscraper)
  10. Solid / blank monochrome image -> rejected (blank_or_solid_monochrome)
  11. Batch pre-filter behavior -> preserves non-destructive metadata and audit log
"""

import os
import sys
import unittest
import io
import numpy as np
from PIL import Image, ImageDraw

backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend"))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from services.candidate_prefilter import (
    evaluate_candidate_image,
    prefilter_candidate_batch,
    PreFilterResult,
    MIN_IMAGE_WIDTH,
    MIN_IMAGE_HEIGHT,
    MAX_ASPECT_RATIO,
    MIN_ASPECT_RATIO
)


class TestCandidatePreFilter(unittest.TestCase):

    def _create_test_image(
        self,
        width: int,
        height: int,
        bg_color=(230, 230, 235),
        add_shapes: bool = True
    ) -> Image.Image:
        """Helper to create test images with high pixel variance."""
        img = Image.new("RGB", (width, height), color=bg_color)
        if add_shapes:
            draw = ImageDraw.Draw(img)
            # Add contrasting geometric features
            draw.rectangle([width * 0.15, height * 0.15, width * 0.85, height * 0.85], fill=(30, 80, 200), outline=(10, 20, 50), width=3)
            draw.ellipse([width * 0.3, height * 0.3, width * 0.7, height * 0.7], fill=(240, 180, 20))
        return img

    def test_01_valid_square_product_image_accepted(self):
        """1. Square product image (1:1, 400x400) should be accepted."""
        img = self._create_test_image(400, 400)
        res, pil_img, _ = evaluate_candidate_image(img, "https://example.com/square.jpg")

        self.assertTrue(res.accepted)
        self.assertIsNone(res.rejection_reason)
        self.assertEqual(res.width, 400)
        self.assertEqual(res.height, 400)
        self.assertAlmostEqual(res.aspect_ratio, 1.0, places=2)
        self.assertIn("square", res.quality_flags)
        self.assertIsNotNone(pil_img)
        print(f"[OK] Square image (400x400) accepted: {res}")

    def test_02_corrupt_unreadable_bytes_rejected(self):
        """2. Corrupt or unreadable byte buffer should be rejected cleanly."""
        corrupt_bytes = b"NOT_A_VALID_IMAGE_FILE_RANDOM_GARBAGE_HEADER_1234567890" * 50
        res, pil_img, _ = evaluate_candidate_image(corrupt_bytes, "https://example.com/corrupt.jpg")

        self.assertFalse(res.accepted)
        self.assertEqual(res.rejection_reason, "corrupted_or_unreadable")
        self.assertIsNone(pil_img)
        print(f"[OK] Corrupt bytes rejected with reason='{res.rejection_reason}'")

    def test_03_tiny_icon_image_rejected(self):
        """3. Tiny images (e.g. 64x64 icon, 80x80 thumbnail) should be rejected."""
        img = self._create_test_image(64, 64)
        res, pil_img, _ = evaluate_candidate_image(img, "https://example.com/icon.png")

        self.assertFalse(res.accepted)
        self.assertEqual(res.rejection_reason, "dimensions_below_minimum")
        self.assertIn("tiny_resolution", res.quality_flags)
        self.assertIsNone(pil_img)
        print(f"[OK] Tiny image (64x64) rejected with reason='{res.rejection_reason}'")

    def test_04_extreme_horizontal_banner_rejected(self):
        """4. Extreme horizontal banner (e.g. 800x100 -> 8:1 ratio, 700x140 -> 5:1 ratio) should be rejected."""
        banner_8to1 = self._create_test_image(800, 100)
        res, pil_img, _ = evaluate_candidate_image(banner_8to1, "https://example.com/banner.jpg")

        self.assertFalse(res.accepted)
        self.assertEqual(res.rejection_reason, "extreme_aspect_ratio_horizontal_banner")
        self.assertIn("horizontal_banner", res.quality_flags)
        self.assertGreater(res.aspect_ratio, MAX_ASPECT_RATIO)

        banner_5to1 = self._create_test_image(750, 150)
        res2, _, _ = evaluate_candidate_image(banner_5to1, "https://example.com/banner5.jpg")
        self.assertFalse(res2.accepted)
        self.assertEqual(res2.rejection_reason, "extreme_aspect_ratio_horizontal_banner")
        print(f"[OK] Extreme banners (8:1 and 5:1) rejected with reason='{res.rejection_reason}'")

    def test_05_extreme_vertical_skyscraper_rejected(self):
        """5. Extreme vertical skyscraper (e.g. 100x600 -> 1:6 ratio, 120x800 -> 1:6.67 ratio) should be rejected."""
        skyscraper = self._create_test_image(120, 720)
        res, pil_img, _ = evaluate_candidate_image(skyscraper, "https://example.com/skyscraper.jpg")

        self.assertFalse(res.accepted)
        self.assertEqual(res.rejection_reason, "extreme_aspect_ratio_vertical_skyscraper")
        self.assertIn("vertical_skyscraper", res.quality_flags)
        self.assertLess(res.aspect_ratio, MIN_ASPECT_RATIO)
        print(f"[OK] Extreme skyscraper (120x720) rejected with reason='{res.rejection_reason}'")

    def test_06_normal_portrait_product_image_accepted(self):
        """6. Legitimate portrait product images (3:4, 9:16, 1:2 tall equipment) should be accepted."""
        # 3:4 portrait (e.g. 450x600)
        portrait_3_4 = self._create_test_image(450, 600)
        res_3_4, _, _ = evaluate_candidate_image(portrait_3_4, "https://example.com/portrait_3_4.jpg")
        self.assertTrue(res_3_4.accepted)
        self.assertIn("portrait", res_3_4.quality_flags)

        # Tall product e.g. tall fire extinguisher / bottle (e.g. 240x600 -> 1:2.5)
        tall_prod = self._create_test_image(240, 600)
        res_tall, _, _ = evaluate_candidate_image(tall_prod, "https://example.com/tall_extinguisher.jpg")
        self.assertTrue(res_tall.accepted)
        self.assertIn("tall_vertical", res_tall.quality_flags)
        print("[OK] Normal portrait and tall vertical product images accepted cleanly.")

    def test_07_normal_landscape_product_image_accepted(self):
        """7. Legitimate landscape product images (4:3, 16:9, 2.5:1 wide equipment) should be accepted."""
        # 4:3 landscape (e.g. 800x600)
        landscape_4_3 = self._create_test_image(800, 600)
        res_4_3, _, _ = evaluate_candidate_image(landscape_4_3, "https://example.com/landscape.jpg")
        self.assertTrue(res_4_3.accepted)
        self.assertIn("landscape", res_4_3.quality_flags)

        # 16:9 landscape (e.g. 640x360)
        landscape_16_9 = self._create_test_image(640, 360)
        res_16_9, _, _ = evaluate_candidate_image(landscape_16_9, "https://example.com/landscape16_9.jpg")
        self.assertTrue(res_16_9.accepted)

        # Wide chassis / heat exchanger (e.g. 600x240 -> 2.5:1)
        wide_chassis = self._create_test_image(600, 240)
        res_wide, _, _ = evaluate_candidate_image(wide_chassis, "https://example.com/wide_hex.jpg")
        self.assertTrue(res_wide.accepted)
        self.assertIn("wide_panoramic", res_wide.quality_flags)
        print("[OK] Normal landscape and wide panoramic product images accepted cleanly.")

    def test_08_borderline_aspect_ratio_behavior(self):
        """8. Verify behavior on borderline aspect ratios (3.0:1 and 0.33:1)."""
        # Exactly 3.0:1 (within MAX_ASPECT_RATIO=3.5)
        borderline_wide = self._create_test_image(600, 200)
        res_w, _, _ = evaluate_candidate_image(borderline_wide)
        self.assertTrue(res_w.accepted, "3.0:1 should be accepted within 3.5 ceiling")
        self.assertIn("wide_panoramic", res_w.quality_flags)

        # Exactly 0.33:1 / 1:3 (within MIN_ASPECT_RATIO=0.28)
        borderline_tall = self._create_test_image(200, 600)
        res_t, _, _ = evaluate_candidate_image(borderline_tall)
        self.assertTrue(res_t.accepted, "1:3 (0.33) should be accepted within 0.28 floor")
        self.assertIn("tall_vertical", res_t.quality_flags)
        print("[OK] Borderline aspect ratios (3.0:1 and 0.33:1) safely accepted with descriptive flags.")

    def test_09_blank_solid_monochrome_image_rejected(self):
        """9. Solid monochrome blank images (zero pixel variance) should be rejected."""
        blank_white = Image.new("RGB", (300, 300), color=(255, 255, 255))
        res_white, pil_img, _ = evaluate_candidate_image(blank_white, "https://example.com/blank.png")
        self.assertFalse(res_white.accepted)
        self.assertEqual(res_white.rejection_reason, "blank_or_solid_monochrome")
        self.assertIn("blank_canvas", res_white.quality_flags)
        self.assertLess(res_white.variance_score, 1.0)

        blank_gray = Image.new("RGB", (300, 300), color=(128, 128, 128))
        res_gray, _, _ = evaluate_candidate_image(blank_gray, "https://example.com/gray.png")
        self.assertFalse(res_gray.accepted)
        self.assertEqual(res_gray.rejection_reason, "blank_or_solid_monochrome")
        print("[OK] Solid blank images rejected with reason='blank_or_solid_monochrome'.")

    def test_10_prefilter_candidate_batch_preserves_metadata(self):
        """10. Test batch prefilter execution, metadata preservation, and audit logging."""
        valid_img = self._create_test_image(400, 300)
        tiny_img = self._create_test_image(50, 50)
        banner_img = self._create_test_image(800, 100)
        blank_img = Image.new("RGB", (300, 300), color=(255, 255, 255))

        batch = [
            ({"url": "http://img1.jpg", "title": "Valid Heat Exchanger", "priority": 1, "branch_angle": "Front Reference"}, valid_img, None),
            ({"url": "http://img2.jpg", "title": "Tiny Icon", "priority": 2, "branch_angle": "Side Profile"}, tiny_img, None),
            ({"url": "http://img3.jpg", "title": "Banner Header", "priority": 3, "branch_angle": "Isometric Angle"}, banner_img, None),
            ({"url": "http://img4.jpg", "title": "Blank Spacer", "priority": 4, "branch_angle": "Rear View"}, blank_img, None),
        ]

        accepted, rejected, counts = prefilter_candidate_batch(batch)

        self.assertEqual(len(accepted), 1)
        self.assertEqual(len(rejected), 3)
        self.assertEqual(accepted[0]["title"], "Valid Heat Exchanger")
        self.assertIn("prefilter", accepted[0])
        self.assertTrue(accepted[0]["prefilter"]["accepted"])

        # Check rejection counts
        self.assertIn("dimensions_below_minimum", counts)
        self.assertIn("extreme_aspect_ratio_horizontal_banner", counts)
        self.assertIn("blank_or_solid_monochrome", counts)

        # Verify audit entries contain complete metadata
        for r in rejected:
            self.assertIn("url", r)
            self.assertIn("title", r)
            self.assertIn("prefilter", r)
            self.assertFalse(r["prefilter"]["accepted"])
            self.assertIsNotNone(r["prefilter"]["rejection_reason"])

        print(f"[OK] Batch prefilter verified: 1 accepted, 3 rejected, counts={counts}")


if __name__ == "__main__":
    unittest.main()
