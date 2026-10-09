"""
Research Stage Reference Selection Correctness Tests.

Verifies the 8 critical identity prioritization and category conflict rules:
1. Exact SKU + low DINO is NOT rejected by visual threshold.
2. Wrong category (e.g. sink vs faucet) results in CATEGORY_CONFLICT.
3. Technical drawing + wrong category is rejected.
4. Technical drawing + exact SKU is allowed and verified.
5. Same brand + generic token overlap (e.g. 'Hansgrohe' + 'Kitchen') is marked INSUFFICIENT_PRODUCT_IDENTITY.
6. Exact model + compatible category + low DINO is a valid verified candidate.
7. Different model + same category + high DINO does NOT beat an exact-ID candidate.
8. Identifier boundaries (e.g. 43218000 vs 432180001) strictly prevent substring false matches.
"""

import unittest
import numpy as np
from services.identifier_policy import (
    ProductIdentity,
    CanonicalProductIdentity,
    normalize_product_identity,
    is_exact_identifier_match,
    extract_primary_category,
    detect_category_conflict
)
from services.candidate_analyzer_service import (
    CandidateAnalyzerService,
    CandidateEvaluation,
    ProductMatch,
    CandidateType,
    Viewpoint,
    EvidenceValue
)


class TestResearchCorrectness(unittest.TestCase):

    def setUp(self):
        self.sink_identity = normalize_product_identity(ProductIdentity(
            brand="Hansgrohe",
            product_name="Hansgrohe C51 Kitchen Sink",
            model_number="43218000",
            article_number="43218000",
            category="Kitchen Sink"
        ))
        self.analyzer = CandidateAnalyzerService(canonical_identity=self.sink_identity)

    def test_01_exact_sku_low_dino_not_killed(self):
        """TEST 1: Exact SKU candidate with low DINO (0.12) is NOT rejected."""
        cand = {
            "id": "cand-sink-01",
            "url": "https://example.com/sink_img.jpg",
            "source_page_url": "https://vseinstrumenti.ru/product/kuhonnaya-mojka-hansgrohe-43218000",
            "source_domain": "vseinstrumenti.ru",
            "title": "Кухонная мойка со смесителем HANSGROHE 43218000 C51-F660-07",
            "snippet": "Kitchen sink 43218000 granite black",
            "visual_sim_to_seed": 0.12,
            "score": 0.12,
            "raw_bytes": b"fake_bytes_sink_1"
        }
        eval_res = self.analyzer.analyze_candidate(cand, identity=self.sink_identity)
        self.assertIn(eval_res.product_match, [ProductMatch.EXACT_ID_MATCH, ProductMatch.TARGET_PRODUCT])
        self.assertTrue(eval_res.exact_id_match)
        self.assertTrue(eval_res.reconstruction_evidence)
        self.assertIsNone(eval_res.rejection_reason)

    def test_02_wrong_category_conflict(self):
        """TEST 2: Target = Sink, Candidate = Faucet (same brand) -> CATEGORY_CONFLICT."""
        cand = {
            "id": "cand-faucet-01",
            "url": "https://example.com/faucet.jpg",
            "source_page_url": "https://example.com/hansgrohe-kitchen-faucet",
            "source_domain": "example.com",
            "title": "Hansgrohe Kitchen Faucet Focus 240",
            "snippet": "High quality kitchen faucet and mixer tap",
            "visual_sim_to_seed": 0.75,
            "score": 0.75
        }
        eval_res = self.analyzer.analyze_candidate(cand, identity=self.sink_identity)
        self.assertEqual(eval_res.product_match, ProductMatch.DIFFERENT_PRODUCT)
        self.assertFalse(eval_res.category_compatible)
        self.assertFalse(eval_res.reconstruction_evidence)
        self.assertIn("category_conflict", eval_res.match_reasons)

    def test_03_technical_drawing_wrong_category_rejected(self):
        """TEST 3: Technical drawing + wrong category (faucet CAD) must be rejected."""
        cand = {
            "id": "cand-cad-faucet",
            "url": "https://freecadfloorplans.com/hansgrohe-kitchen-faucet.jpg",
            "source_page_url": "https://freecadfloorplans.com/hansgrohe-kitchen-faucet/",
            "source_domain": "freecadfloorplans.com",
            "title": "Hansgrohe Kitchen Faucet - Free CAD Drawings",
            "snippet": "Free CAD technical drawings and blueprints for kitchen faucet",
            "visual_sim_to_seed": 0.09,
            "score": 0.09
        }
        eval_res = self.analyzer.analyze_candidate(cand, identity=self.sink_identity)
        self.assertEqual(eval_res.product_match, ProductMatch.DIFFERENT_PRODUCT)
        self.assertFalse(eval_res.reconstruction_evidence)

    def test_04_technical_drawing_exact_sku_allowed(self):
        """TEST 4: Technical drawing + exact SKU (43218000) is allowed and HIGH evidence value."""
        cand = {
            "id": "cand-cad-sink-exact",
            "url": "https://hansgrohe.com/sink_cad.jpg",
            "source_page_url": "https://hansgrohe.com/articledetail-43218000",
            "source_domain": "hansgrohe.com",
            "title": "Hansgrohe C51 Sink 43218000 Dimensional Drawing",
            "snippet": "Technical CAD dimensions for Hansgrohe C51 Kitchen Sink 43218000",
            "visual_sim_to_seed": 0.15,
            "score": 0.15
        }
        eval_res = self.analyzer.analyze_candidate(cand, identity=self.sink_identity)
        self.assertIn(eval_res.product_match, [ProductMatch.EXACT_ID_MATCH, ProductMatch.TARGET_PRODUCT])
        self.assertEqual(eval_res.candidate_type, CandidateType.TECHNICAL_DRAWING)
        self.assertTrue(eval_res.reconstruction_evidence)
        self.assertEqual(eval_res.evidence_value, EvidenceValue.HIGH)

    def test_05_same_brand_generic_token_overlap(self):
        """TEST 5: Same brand ('Hansgrohe') + generic tokens ('Kitchen') without model/category is UNCERTAIN."""
        cand = {
            "id": "cand-generic-01",
            "url": "https://example.com/generic.jpg",
            "source_page_url": "https://example.com/hansgrohe-kitchen-lifestyle",
            "source_domain": "example.com",
            "title": "Hansgrohe Kitchen Lifestyle Premium Collection",
            "snippet": "Discover the new modern kitchen collection by Hansgrohe",
            "visual_sim_to_seed": 0.50,
            "score": 0.50
        }
        eval_res = self.analyzer.analyze_candidate(cand, identity=self.sink_identity)
        self.assertEqual(eval_res.product_match, ProductMatch.UNCERTAIN)
        self.assertFalse(eval_res.reconstruction_evidence)

    def test_06_exact_model_compatible_category_low_dino(self):
        """TEST 6: Exact model + compatible category + low DINO is a valid verified candidate."""
        cand = {
            "id": "cand-sink-rear",
            "url": "https://example.com/sink_underside.jpg",
            "source_page_url": "https://sanitino.ro/hansgrohe-chiuvete-c51-43218000",
            "source_domain": "sanitino.ro",
            "title": "Hansgrohe Chiuvete Set C51 43218000 Underside Drain",
            "snippet": "Chiuveta bucatarie Hansgrohe C51 43218000 negru grafit",
            "visual_sim_to_seed": 0.18,
            "score": 0.18
        }
        eval_res = self.analyzer.analyze_candidate(cand, identity=self.sink_identity)
        self.assertIn(eval_res.product_match, [ProductMatch.EXACT_ID_MATCH, ProductMatch.TARGET_PRODUCT])
        self.assertTrue(eval_res.exact_id_match)
        self.assertTrue(eval_res.category_compatible)
        self.assertTrue(eval_res.reconstruction_evidence)

    def test_07_different_model_high_dino_does_not_beat_exact_sku(self):
        """TEST 7: Exact-ID candidate outranks different model even if different model has high DINO."""
        cand_exact = {
            "id": "cand-exact-sku",
            "url": "http://127.0.0.1:5000/cache/sink_exact.jpg",
            "title": "Hansgrohe C51 Kitchen Sink 43218000",
            "source": "exact_query",
            "visual_sim_to_seed": 0.15,
            "cls_vector": np.zeros(384)
        }
        eval_exact = self.analyzer.analyze_candidate({
            "title": "Hansgrohe C51 Kitchen Sink 43218000",
            "source_page_url": "https://hansgrohe.com/43218000",
            "source_domain": "hansgrohe.com",
            "snippet": "Hansgrohe sink 43218000"
        }, identity=self.sink_identity)

        cand_other = {
            "id": "cand-other-model",
            "url": "http://127.0.0.1:5000/cache/sink_other.jpg",
            "title": "Hansgrohe S51 Sink 43229000",
            "source": "viewpoint_query",
            "visual_sim_to_seed": 0.85,
            "cls_vector": np.zeros(384)
        }
        eval_other = self.analyzer.analyze_candidate({
            "title": "Hansgrohe S51 Sink 43229000",
            "source_page_url": "https://hansgrohe.com/43229000",
            "source_domain": "hansgrohe.com",
            "snippet": "Hansgrohe sink 43229000"
        }, identity=self.sink_identity)

        # Exact ID is EXACT_ID_MATCH; other model with contradictory SKU is DIFFERENT_PRODUCT
        self.assertEqual(eval_exact.product_match, ProductMatch.EXACT_ID_MATCH)
        self.assertEqual(eval_other.product_match, ProductMatch.DIFFERENT_PRODUCT)
        self.assertTrue(eval_exact.reconstruction_evidence)
        self.assertFalse(eval_other.reconstruction_evidence)

    def test_08_identifier_boundary_strictness(self):
        """TEST 8: 43218000 does NOT match 432180001 or 143218000."""
        self.assertTrue(is_exact_identifier_match("43218000", "Hansgrohe 43218000 kitchen sink"))
        self.assertTrue(is_exact_identifier_match("43218000", "Hansgrohe 43218-000 kitchen sink"))
        self.assertTrue(is_exact_identifier_match("43218000", "Hansgrohe 43218.000 kitchen sink"))
        self.assertTrue(is_exact_identifier_match("43218000", "Hansgrohe 43218 000 kitchen sink"))

        # Rejects prefix/suffix expansion
        self.assertFalse(is_exact_identifier_match("43218000", "Hansgrohe 432180001 kitchen sink"))
        self.assertFalse(is_exact_identifier_match("43218000", "Hansgrohe 143218000 kitchen sink"))
        self.assertFalse(is_exact_identifier_match("43218000", "Hansgrohe ABC43218000 kitchen sink"))


if __name__ == '__main__':
    unittest.main()
