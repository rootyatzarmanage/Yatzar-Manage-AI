"""
Unit tests for Multi-Source Web Scraping and Viewpoint Harvesting Pipeline
with Scrapy (Static) and Playwright (Dynamic) in-memory engines.
"""

import os
import sys
import unittest
import numpy as np
from PIL import Image, ImageDraw

backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend"))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from services.scraper_service import (
    scrape_images_scrapy,
    scrape_images_playwright,
    ScrapingPipelineManager,
    harvest_and_filter,
    CACHE_DIR
)


class TestScraperService(unittest.TestCase):

    def create_seed_image(self) -> Image.Image:
        """Creates a realistic industrial heat exchanger seed image."""
        img = Image.new("RGB", (300, 300), color=(235, 235, 240))
        draw = ImageDraw.Draw(img)
        # Blue end-frame
        draw.rectangle([60, 40, 240, 260], fill=(25, 75, 180), outline=(10, 30, 80), width=4)
        # Internal corrugated plate pack
        for y in range(60, 240, 15):
            draw.line([(80, y), (220, y)], fill=(180, 185, 190), width=3)
        # Ports
        draw.ellipse([80, 70, 120, 110], fill=(210, 210, 220), outline=(40, 40, 40), width=3)
        draw.ellipse([180, 70, 220, 110], fill=(210, 210, 220), outline=(40, 40, 40), width=3)
        return img

    def test_01_scrapy_static_extractor(self):
        """Test Scrapy/Parsel static extraction function."""
        # Test against a known static page or fallback URL
        urls = scrape_images_scrapy("https://httpbin.org/html")
        self.assertIsInstance(urls, list)
        print(f"[OK] scrape_images_scrapy executed cleanly, extracted {len(urls)} URLs.")

    def test_02_playwright_function_signature(self):
        """Test Playwright dynamic scraper function availability."""
        self.assertTrue(callable(scrape_images_playwright))
        print("[OK] scrape_images_playwright callable verified.")

    def test_03_scraping_pipeline_end_to_end_in_memory(self):
        """Test full pipeline: in-memory streaming, DINOv2 scoring, noise filtering, and PCA layout."""
        seed_img = self.create_seed_image()
        target_queries = [
            "Alfa Laval Heat Exchanger rear view connection ports",
            "Alfa Laval Heat Exchanger plate pack tightening bolts",
            "Alfa Laval Heat Exchanger side profile"
        ]

        result = harvest_and_filter(
            seed_image=seed_img,
            target_queries=target_queries,
            max_candidates=10,
            similarity_threshold=0.60
        )

        self.assertIn("candidates", result)
        self.assertIn("seed_coordinates", result)
        self.assertGreater(len(result["candidates"]), 0)

        # Seed coordinates must be (0.0, 0.0)
        self.assertEqual(result["seed_coordinates"]["x"], 0.0)
        self.assertEqual(result["seed_coordinates"]["y"], 0.0)

        # Verify candidate scoring and ranking
        scores = [c["score"] for c in result["candidates"]]
        self.assertEqual(scores, sorted(scores, reverse=True), "Candidates should be sorted descending by score")

        # Top candidate checks
        top_cand = result["candidates"][0]
        self.assertGreaterEqual(top_cand["score"], 0.60)
        self.assertIn("angle", top_cand)
        self.assertIn("coordinates", top_cand)
        self.assertIn("source", top_cand)
        self.assertIn(top_cand["source"], ["Scrapy (Static)", "Playwright (Dynamic)"])

        # Check that top candidate local_path was saved in CACHE_DIR
        if top_cand.get("local_path"):
            self.assertTrue(os.path.exists(top_cand["local_path"]))

        print(f"[OK] Pipeline verified: {len(result['candidates'])} ranked candidates returned.")
        print(f"Top Candidate: Title='{top_cand['title']}', Source='{top_cand['source']}', Score={top_cand['score']}, Angle='{top_cand['angle']}', Coords={top_cand['coordinates']}")


if __name__ == "__main__":
    unittest.main()
