"""
Unit tests for Multi-Source Web Scraping and Viewpoint Harvesting Pipeline
with Scrapy (Static) and Playwright (Dynamic) in-memory engines.
"""

import os
import io
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
        from unittest.mock import patch
        with patch("services.scraper_service.harvest_search_images_playwright", return_value=["https://example.com/img1.jpg"]):
            urls = scrape_images_scrapy("Alfa Laval Heat Exchanger")
            self.assertIsInstance(urls, list)
            self.assertGreater(len(urls), 0)
            print(f"[OK] scrape_images_scrapy executed cleanly, extracted {len(urls)} URLs.")

    def test_02_playwright_function_signature(self):
        """Test Playwright dynamic scraper function availability."""
        self.assertTrue(callable(scrape_images_playwright))
        print("[OK] scrape_images_playwright callable verified.")

    def test_03_scraping_pipeline_end_to_end_in_memory(self):
        """Test full pipeline: in-memory streaming, DINOv2 scoring, noise filtering, and PCA layout."""
        from unittest.mock import patch
        from services.scraper_service import PlaywrightSearchEngine
        seed_img = self.create_seed_image()
        target_queries = [
            "Alfa Laval Heat Exchanger rear view connection ports",
            "Alfa Laval Heat Exchanger plate pack tightening bolts",
            "Alfa Laval Heat Exchanger side profile"
        ]

        # Provide synthetic sample images for pipeline testing
        sample_img_1 = self.create_seed_image()
        # Non-identical candidate image with rich features (passes prefilter, distinct from seed)
        sample_img_2 = Image.new("RGB", (300, 300), color=(240, 240, 245))
        d2 = ImageDraw.Draw(sample_img_2)
        d2.rectangle([40, 40, 260, 260], fill=(200, 50, 50), outline=(20, 20, 20), width=4)
        d2.ellipse([80, 80, 220, 220], fill=(240, 200, 50))
        buf1 = io.BytesIO()
        sample_img_1.save(buf1, format="JPEG")
        raw1 = buf1.getvalue()
        buf2 = io.BytesIO()
        sample_img_2.save(buf2, format="JPEG")
        raw2 = buf2.getvalue()

        def mock_fetch(url, timeout=5):
            if "mock_1" in url:
                return sample_img_1, raw1
            return sample_img_2, raw2

        mock_search_results = [
            {"url": "https://example.com/mock_1.jpg", "source_page_url": "https://example.com/page1", "source_domain": "example.com", "source_engine": "bing", "source_tier": "Pass 1", "priority": 1.0, "target_evidence": "EXACT_MATCH", "branch_angle": "Front Reference", "title": "Alfa Laval Front", "query": "Alfa Laval Heat Exchanger", "query_family": "EXACT_PRODUCT", "expected_information": "Exact product"},
            {"url": "https://example.com/mock_2.jpg", "source_page_url": "https://example.com/page2", "source_domain": "example.com", "source_engine": "bing", "source_tier": "Pass 2", "priority": 0.9, "target_evidence": "SIDE", "branch_angle": "Side Profile", "title": "Alfa Laval Side", "query": "Alfa Laval Heat Exchanger side", "query_family": "PRODUCT_VIEWPOINT", "expected_information": "Side view"}
        ]

        with patch.object(PlaywrightSearchEngine, "search_queries_batch", return_value=mock_search_results), \
             patch.object(ScrapingPipelineManager, "_fetch_image_in_memory", side_effect=mock_fetch):

            result = harvest_and_filter(
                seed_image=seed_img,
                product_title="Alfa Laval Heat Exchanger",
                part_number="AL-HEX-9000",
                brand="Alfa Laval",
                category="Industrial Equipment",
                max_candidates=10,
                similarity_threshold=0.60
            )

            self.assertIn("candidates", result)
            self.assertIn("seed_coordinates", result)
            self.assertIn("total_prefilter_accepted", result)
            self.assertGreater(len(result["candidates"]), 0)

            # Seed coordinates must be (0.0, 0.0)
            self.assertEqual(result["seed_coordinates"]["x"], 0.0)
            self.assertEqual(result["seed_coordinates"]["y"], 0.0)

            # Top candidate checks
            top_cand = result["candidates"][0]
            self.assertIn("angle", top_cand)
            self.assertIn("coordinates", top_cand)
            self.assertIn("source", top_cand)

            print(f"[OK] Pipeline verified: {len(result['candidates'])} candidates returned (Prefilter accepted={result['total_prefilter_accepted']}).")


if __name__ == "__main__":
    unittest.main()
