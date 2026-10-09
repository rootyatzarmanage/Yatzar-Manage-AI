"""
Unit tests for QueryPlanner and Retrieval V2 Staged Multi-Family Query Architecture.
Verifies:
  1. Hansgrohe 43218000 generates 5 structured query families.
  2. Internal IDs (e.g. C51-F660-07) never leak into search queries.
  3. Bad prompt robustness across 5 test cases (A, B, C, D, E).
  4. Query provenance and metadata annotations (priority, family, evidence type, identifiers).
  5. Official source domain queries generated when source_urls are present.
"""

import os
import sys
import unittest

backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend"))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from services.identifier_policy import ProductIdentity, normalize_product_identity
from services.query_planner import QueryPlanner, QueryFamily, PlannedQuery


class TestQueryPlanner(unittest.TestCase):

    def test_01_hansgrohe_query_generation(self):
        """Test full query planning for Hansgrohe C51 Sink Combi 660 Select."""
        product_dict = {
            "id": "C51-F660-07",
            "brand": "Hansgrohe",
            "name": "C51 Sink Combi 660 Select",
            "model_number": "43218000",
            "category": "Sanitary Ware",
            "source_urls": [
                "https://pro.hansgrohe.com/articledetail-c51-c51-f660-07-sink-combi-660-select-43218000#spareparts"
            ]
        }

        queries = QueryPlanner.plan(product_dict)
        self.assertGreater(len(queries), 8, "Should generate comprehensive query ladder")

        # 1. Check Pass 1 Exact and Source Domain
        pass_1 = [q for q in queries if q.pass_stage == 1]
        self.assertTrue(any('"Hansgrohe 43218000"' in q.query for q in pass_1), "Must include exact brand + model")
        self.assertTrue(any("site:pro.hansgrohe.com" in q.query for q in pass_1), "Must include source domain query")

        # 2. Check Pass 2 Viewpoints
        pass_2 = [q for q in queries if q.pass_stage == 2]
        vp_evidence = {q.target_evidence for q in pass_2}
        self.assertIn("FRONT", vp_evidence)
        self.assertIn("SIDE", vp_evidence)
        self.assertIn("REAR", vp_evidence)
        self.assertIn("TOP", vp_evidence)
        self.assertIn("BOTTOM", vp_evidence)
        self.assertIn("ISOMETRIC", vp_evidence)

        # 3. Check Pass 3 Technical & Components
        pass_3 = [q for q in queries if q.pass_stage == 3]
        tech_evidence = {q.target_evidence for q in pass_3}
        self.assertIn("TECHNICAL_DRAWING", tech_evidence)
        self.assertIn("DIMENSIONS", tech_evidence)
        self.assertIn("SPARE_PARTS", tech_evidence)

        # 4. Check Internal ID exclusion
        for q in queries:
            self.assertNotIn("C51-F660-07", q.query, f"Internal ID leaked into query: {q.query}")

        print(f"[OK] Test 1 passed: Generated {len(queries)} queries for Hansgrohe across {len(set(q.pass_stage for q in queries))} passes.")

    def test_02_bad_user_prompt_robustness(self):
        """
        Tests the 5 bad user prompt cases:
        A. 'Hansgrohe sink'
        B. 'black kitchen sink'
        C. '43218000'
        D. 'C51-F660-07'
        E. empty / omitted
        """
        base_meta = {
            "internal_id": "C51-F660-07",
            "brand": "Hansgrohe",
            "product_name": "C51 Sink Combi 660 Select",
            "model_number": "43218000",
            "category": "Sanitary Ware",
            "source_urls": ["https://pro.hansgrohe.com/articledetail-c51-c51-f660-07-sink-combi-660-select-43218000#spareparts"]
        }

        test_cases = [
            ("Case A", "Hansgrohe sink"),
            ("Case B", "black kitchen sink"),
            ("Case C", "43218000"),
            ("Case D", "C51-F660-07"),
            ("Case E", "")
        ]

        for case_name, bad_prompt in test_cases:
            meta = dict(base_meta, user_prompt=bad_prompt)
            queries = QueryPlanner.plan(meta)

            self.assertGreater(len(queries), 6, f"{case_name}: Must still generate rich query ladder")
            
            # Top query in Pass 1 MUST be the exact brand + manufacturer identifier
            top_q = queries[0]
            self.assertEqual(top_q.pass_stage, 1, f"{case_name}: Top query must be Pass 1")
            self.assertEqual(top_q.query_family, QueryFamily.EXACT_PRODUCT, f"{case_name}: Top query must be exact")
            self.assertIn("Hansgrohe", top_q.query)
            self.assertIn("43218000", top_q.query)

            # Internal ID must NEVER be queried even if user wrote it in prompt (Case D)
            for q in queries:
                if q.query_family != QueryFamily.USER_FALLBACK or "C51-F660-07" in base_meta["internal_id"]:
                    self.assertNotIn("C51-F660-07", q.query, f"{case_name}: Leaked internal ID in query: {q.query}")

            print(f"[OK] {case_name} (Prompt: '{bad_prompt}') passed: Primary query = '{top_q.query}'")

    def test_03_query_metadata_and_provenance(self):
        """Verify each query stores complete metadata and provenance annotations."""
        product_dict = {
            "brand": "Alfa Laval",
            "name": "Heat Exchanger",
            "part_number": "AL-HEX-9000",
            "category": "Industrial Equipment"
        }

        queries = QueryPlanner.plan(product_dict)
        for q in queries:
            self.assertIsInstance(q.query, str)
            self.assertIsInstance(q.query_family, QueryFamily)
            self.assertGreaterEqual(q.priority, 0.0)
            self.assertLessEqual(q.priority, 1.0)
            self.assertIn(q.pass_stage, [1, 2, 3, 4])
            self.assertTrue(len(q.identifiers_used) > 0)
            self.assertTrue(len(q.expected_information) > 0)

        print(f"[OK] Test 3 passed: Verified complete metadata on {len(queries)} planned queries.")


if __name__ == "__main__":
    unittest.main()
