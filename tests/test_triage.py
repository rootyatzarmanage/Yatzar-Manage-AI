"""
Unit tests for Stage 1: Geometric Uncertainty and Viewpoint Triage Service.
"""

import os
import sys
import unittest

backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend"))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from services.triage_service import (
    evaluate_geometric_uncertainty,
    build_vision_llm_prompt,
    TriageResult
)


class TestTriageService(unittest.TestCase):

    def test_01_alfa_laval_heat_exchanger_triage(self):
        """Test industrial equipment asset with high asymmetry and deep scrape requirement."""
        result = evaluate_geometric_uncertainty(
            product_title="Alfa Laval Heat Exchanger",
            product_sku="AL-HEX-9000"
        )

        # Validate schema via Pydantic model
        validated = TriageResult(**result)
        self.assertFalse(validated.rotational_symmetry)
        self.assertGreater(validated.symmetry_confidence, 0.8)
        self.assertFalse(validated.skip_deep_scraping)
        self.assertGreaterEqual(validated.max_scrape_budget, 15)
        self.assertGreater(validated.quad_uncertainty.rear, 0.5)
        self.assertGreater(validated.quad_uncertainty.bottom, 0.5)
        self.assertTrue(any("rear" in q.lower() or "ports" in q.lower() for q in validated.target_search_queries))
        print(f"[OK] Alfa Laval Heat Exchanger Triage verified: budget={validated.max_scrape_budget}, skip={validated.skip_deep_scraping}")

    def test_02_iphone_15_pro_triage(self):
        """Test consumer electronics asset with camera bump asymmetry."""
        result = evaluate_geometric_uncertainty(
            product_title="iPhone 15 Pro Natural Titanium",
            product_sku="A3102"
        )

        validated = TriageResult(**result)
        self.assertFalse(validated.rotational_symmetry)
        self.assertFalse(validated.skip_deep_scraping)
        self.assertGreaterEqual(validated.max_scrape_budget, 10)
        self.assertTrue(any("camera" in q.lower() or "usb" in q.lower() or "button" in q.lower() for q in validated.target_search_queries))
        print(f"[OK] iPhone 15 Pro Triage verified: budget={validated.max_scrape_budget}, skip={validated.skip_deep_scraping}")

    def test_03_rotationally_symmetric_bottle_triage(self):
        """Test radially symmetric asset where deep scraping should be bypassed."""
        result = evaluate_geometric_uncertainty(
            product_title="Stainless Steel Water Bottle 750ml",
            product_sku="HYDRO-BOT-750"
        )

        validated = TriageResult(**result)
        self.assertTrue(validated.rotational_symmetry)
        self.assertTrue(validated.skip_deep_scraping)
        self.assertLessEqual(validated.max_scrape_budget, 5)
        self.assertLessEqual(validated.quad_uncertainty.rear, 0.15)
        self.assertLessEqual(validated.quad_uncertainty.sides, 0.15)
        print(f"[OK] Symmetric Bottle Triage verified: budget={validated.max_scrape_budget}, skip={validated.skip_deep_scraping}")

    def test_04_vision_llm_prompt_structure(self):
        """Test that structured prompt properly formats product metadata."""
        prompt = build_vision_llm_prompt("Test Drill Machine", "SKU-99")
        self.assertIn("Test Drill Machine", prompt)
        self.assertIn("SKU-99", prompt)
        self.assertIn("rotational_symmetry", prompt)
        self.assertIn("quad_uncertainty", prompt)
        self.assertIn("skip_deep_scraping", prompt)
        print("[OK] Vision LLM prompt generation verified.")


if __name__ == "__main__":
    unittest.main()
