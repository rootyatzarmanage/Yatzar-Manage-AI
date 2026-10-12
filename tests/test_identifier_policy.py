"""
Unit tests for Identifier Normalization Policy and Query Generation Cascade.
Verifies:
  TEST 1: Internal product_id ("PROD-IPHONE-08") never leaks into queries; manufacturer model ("A3102") is used.
  TEST 2: Industrial part_number ("AL-HEX-9000") is safely used for Tier 1.
  TEST 3: Internal UUID / hash with no verified manufacturer identifier cleanly SKIPS Tier 1.
  TEST 4: Product name + model + category produces functional Tier 2 & Tier 3 queries.
  TEST 5: Non-PROD prefixed internal IDs (UUIDs, custom DB keys, synthetic slugs) never leak.
"""

import os
import sys
import unittest

backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend"))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from services.identifier_policy import (
    is_safe_manufacturer_identifier,
    extract_verified_manufacturer_identifier,
    extract_brand_or_manufacturer,
    sanitize_query_against_internal_leakage,
    ProductIdentity
)
from services.triage_service import build_prioritized_search_queries


class TestIdentifierPolicyAndQueryCascade(unittest.TestCase):

    def test_01_internal_product_id_never_in_queries(self):
        """
        TEST 1:
        Input:
            product_id = "PROD-IPHONE-08"
            product_name = "iPhone 15 Pro"
            model_number = "A3102"
        Expected:
            "PROD-IPHONE-08" NEVER appears in a search query.
            Manufacturer/model information (A3102) can be used.
        """
        product_id = "PROD-IPHONE-08"
        product_name = "iPhone 15 Pro"
        model_number = "A3102"

        queries = build_prioritized_search_queries(
            product_id=product_id,
            product_name=product_name,
            model_number=model_number
        )

        query_strings = [q["query"] for q in queries]
        self.assertTrue(len(query_strings) > 0, "Should generate queries")

        # Assertion 1: PROD-IPHONE-08 must NEVER appear in ANY query
        for q in query_strings:
            self.assertNotIn("PROD-IPHONE-08", q, f"Internal product ID leaked into query: {q}")
            self.assertNotIn("PROD-", q, f"PROD prefix leaked into query: {q}")

        # Assertion 2: Model A3102 must be used in Tier 1 and/or Tier 2
        tier_1_queries = [q["query"] for q in queries if q["priority"] == 1]
        self.assertTrue(any("A3102" in q for q in tier_1_queries), "Model number A3102 should be used in Tier 1")

        print(f"[OK] Test 1 passed: {len(queries)} queries generated, 'PROD-IPHONE-08' strictly excluded.")

    def test_02_manufacturer_part_number_used_in_tier_1(self):
        """
        TEST 2:
        Input:
            product_id = "PROD-ALFA-01"
            product_name = "Alfa Laval Heat Exchanger"
            part_number = "AL-HEX-9000"
        Expected:
            AL-HEX-9000 can be used for Tier 1.
            PROD-ALFA-01 is never queried.
        """
        product_id = "PROD-ALFA-01"
        product_name = "Alfa Laval Heat Exchanger"
        part_number = "AL-HEX-9000"

        queries = build_prioritized_search_queries(
            product_id=product_id,
            product_name=product_name,
            part_number=part_number
        )

        tier_1_queries = [q["query"] for q in queries if q["priority"] == 1]
        self.assertTrue(len(tier_1_queries) > 0, "Tier 1 should execute when valid part_number is present")
        self.assertTrue(all("AL-HEX-9000" in q for q in tier_1_queries), "Tier 1 queries must reference AL-HEX-9000")

        # Verify internal ID did not leak
        for q in queries:
            self.assertNotIn("PROD-ALFA-01", q["query"])

        print(f"[OK] Test 2 passed: Tier 1 properly utilized 'AL-HEX-9000' -> {tier_1_queries}")

    def test_03_uuid_and_missing_manufacturer_id_skips_tier_1(self):
        """
        TEST 3:
        Input:
            product_id = "8f7b3c2e-4d1a-4f5b-9c12-3e4f5a6b7c8d" (UUID)
            no verified manufacturer identifier
            product_name = "Stainless Steel Water Bottle"
        Expected:
            Tier 1 is SKIPPED (0 queries in Priority 1).
            product_id is NOT searched.
        """
        uuid_id = "8f7b3c2e-4d1a-4f5b-9c12-3e4f5a6b7c8d"
        product_name = "Stainless Steel Water Bottle"

        queries = build_prioritized_search_queries(
            product_id=uuid_id,
            product_name=product_name,
            model_number="",
            part_number="",
            sku=""
        )

        tier_1_queries = [q["query"] for q in queries if q["priority"] == 1]
        self.assertEqual(len(tier_1_queries), 0, "Tier 1 must be skipped when no verified manufacturer ID exists")

        # Ensure UUID is never searched
        for q in queries:
            self.assertNotIn(uuid_id, q["query"], f"UUID leaked into query: {q['query']}")

        # Ensure Tier 2 and Tier 3 still execute
        tier_2_queries = [q["query"] for q in queries if q["priority"] == 2]
        tier_3_queries = [q["query"] for q in queries if q["priority"] == 3]
        self.assertGreater(len(tier_2_queries), 0, "Tier 2 should still generate product name queries")
        self.assertGreater(len(tier_3_queries), 0, "Tier 3 should generate viewpoint queries")

        print(f"[OK] Test 3 passed: Tier 1 successfully skipped (Tier 1 count = {len(tier_1_queries)}), UUID excluded.")

    def test_04_product_name_model_category_tier_2_and_3_functional(self):
        """
        TEST 4:
        Input:
            product name + model + category
        Expected:
            Tier 2 and Tier 3 remain functional and produce viewpoint anchors.
        """
        product_name = "ViewSonic Laser Projector"
        model_number = "LS740HD"
        category = "Electronics"

        queries = build_prioritized_search_queries(
            product_name=product_name,
            model_number=model_number,
            category=category
        )

        tier_1_queries = [q["query"] for q in queries if q["priority"] == 1]
        tier_2_queries = [q["query"] for q in queries if q["priority"] == 2]
        tier_3_queries = [q["query"] for q in queries if q["priority"] == 3]
        tier_4_queries = [q["query"] for q in queries if q["priority"] == 4]

        self.assertGreater(len(tier_1_queries), 0, "Tier 1 should generate exact brand + model queries")
        self.assertGreater(len(tier_2_queries), 0, "Tier 2 should generate viewpoint anchor queries")
        self.assertGreater(len(tier_3_queries), 0, "Tier 3 should generate technical and component queries")
        self.assertGreater(len(tier_4_queries), 0, "Tier 4 should generate category context queries")

        # Viewpoint checks in Tier 2
        tier_2_text = " ".join(tier_2_queries).lower()
        self.assertIn("front", tier_2_text)
        self.assertIn("side", tier_2_text)
        self.assertIn("rear", tier_2_text)

        print(f"[OK] Test 4 passed: Tier 1 ({len(tier_1_queries)}), Tier 2 ({len(tier_2_queries)}), Tier 3 ({len(tier_3_queries)}), Tier 4 ({len(tier_4_queries)}) verified.")

    def test_05_non_prod_internal_ids_do_not_leak(self):
        """
        TEST 5:
        Verify that internal IDs do not leak into any generated search query,
        even when they are not prefixed with "PROD-".
        """
        test_internal_ids = [
            "INTERNAL-99812",
            "db_item_8812_v3",
            "asset-55443",
            "c3f4b8109d7a",
            "ITEM-0092-A",
            "SYS-REC-77341",
            "10492"
        ]

        for internal_id in test_internal_ids:
            queries = build_prioritized_search_queries(
                product_id=internal_id,
                product_name="Electrolux Electric Steam Oven",
                model_number="EOB8S39Z"
            )

            for q in queries:
                self.assertNotIn(internal_id, q["query"], f"Internal ID '{internal_id}' leaked into query: {q['query']}")

        print(f"[OK] Test 5 passed: Tested {len(test_internal_ids)} non-PROD internal IDs, 0 leaked into queries.")

    def test_06_identifier_validation_policy_rules(self):
        """
        Test fine-grained validator unit tests for is_safe_manufacturer_identifier.
        """
        # Safe manufacturer IDs
        self.assertTrue(is_safe_manufacturer_identifier("A3102"))
        self.assertTrue(is_safe_manufacturer_identifier("AL-HEX-9000"))
        self.assertTrue(is_safe_manufacturer_identifier("LS740HD"))
        self.assertTrue(is_safe_manufacturer_identifier("EOB8S39Z"))
        self.assertTrue(is_safe_manufacturer_identifier("NP-ME-WOOD"))
        self.assertTrue(is_safe_manufacturer_identifier("M393A4K40BB1-CRC"))
        self.assertTrue(is_safe_manufacturer_identifier("MAXIMUS-MPX"))
        self.assertTrue(is_safe_manufacturer_identifier("CEA-CO2-5KG"))

        # Unsafe internal/placeholder IDs
        self.assertFalse(is_safe_manufacturer_identifier("PROD-IPHONE-08"))
        self.assertFalse(is_safe_manufacturer_identifier("PROD-ALFA-01"))
        self.assertFalse(is_safe_manufacturer_identifier("PROD-GEN-01"))
        self.assertFalse(is_safe_manufacturer_identifier("INTERNAL-1002"))
        self.assertFalse(is_safe_manufacturer_identifier("ASSET-99"))
        self.assertFalse(is_safe_manufacturer_identifier("8f7b3c2e-4d1a-4f5b-9c12-3e4f5a6b7c8d"))
        self.assertFalse(is_safe_manufacturer_identifier("64bf3a1c8f1e0d3b4a2c1d9e"))  # Mongo ObjectId
        self.assertFalse(is_safe_manufacturer_identifier("12345"))  # Pure autoincrement integer
        self.assertFalse(is_safe_manufacturer_identifier("N/A"))
        self.assertFalse(is_safe_manufacturer_identifier("NONE"))
        self.assertFalse(is_safe_manufacturer_identifier("CUSTOM"))
        self.assertFalse(is_safe_manufacturer_identifier(""))
        self.assertFalse(is_safe_manufacturer_identifier(None))

        print("[OK] Test 6 passed: Fine-grained identifier validator verified.")


if __name__ == "__main__":
    unittest.main()
