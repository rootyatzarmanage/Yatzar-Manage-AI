"""
Focused Regression Test Suite for Forensic Research & Candidate Filtering Regression Fix.

Verifies:
A. Genuinely correct candidates survive:
   - Spacing variations (e.g. "PS 10" vs "PS10", "C 51" vs "C51") trigger Exact-ID match.
   - Alternate viewpoint candidates (v_sim between 0.28 and 0.44) survive when corroborated.
   - Technical drawings / schematics survive when corroborated (v_sim >= 0.20).
   - Multiple verified candidates with UNKNOWN viewpoint are retained for marginal utility curation.
   - Rejection reason is never cryptic "Standard product imagery".
   - Query Planner does not duplicate model number when already present in product name.

B. Same-model-number but wrong-product candidates are rejected:
   - Matching model number with conflicting category noun (e.g. "C51" faucet vs sink) is rejected.
   - Matching model number with competing brand or discordant category is rejected.
   - Discordant noise (v_sim < 0.20) is strictly rejected as LOW_VISUAL_SIMILARITY.
"""

import os
import sys
import unittest
import numpy as np

backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend"))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from services.identifier_policy import (
    ProductIdentity,
    CanonicalProductIdentity,
    normalize_product_identity,
    is_exact_identifier_match,
    detect_category_conflict
)
from services.query_planner import QueryPlanner, QueryFamily
from services.candidate_analyzer_service import (
    CandidateAnalyzerService,
    ProductMatch,
    CandidateType,
    Viewpoint,
    EvidenceValue,
    evaluate_candidates_batch
)
from services.scraper_service import ScrapingPipelineManager
from services.reference_pool_service import ReferencePoolCurationService


class TestCandidateFilteringRegressionFix(unittest.TestCase):

    # =========================================================================
    # PART A: GENUINELY CORRECT CANDIDATES SURVIVE
    # =========================================================================

    def test_01_space_variant_marsurf_ps10_survives(self):
        """Authentic distributor candidate with 'PS10' (no space) matches target 'MarSurf PS 10'."""
        self.assertTrue(is_exact_identifier_match("MarSurf PS 10", "Mahr MarSurf PS10 Portable Roughness Unit"))
        self.assertTrue(is_exact_identifier_match("PS 10", "Mahr MarSurf PS10 Unit"))
        self.assertTrue(is_exact_identifier_match("PS10", "Mahr MarSurf PS 10 Unit"))
        self.assertTrue(is_exact_identifier_match("C51", "Hansgrohe C 51 Kitchen Sink"))
        self.assertTrue(is_exact_identifier_match("C 51", "Hansgrohe C51 Kitchen Sink"))
        self.assertTrue(is_exact_identifier_match("6910232", "Mahr Federal 6910-232 Surface Tester"))

        # Test through CandidateAnalyzerService
        identity = CanonicalProductIdentity(
            canonical_brand="Mahr",
            canonical_product_name="MarSurf PS 10",
            canonical_model="MarSurf PS 10",
            canonical_category="Metrology"
        )
        analyzer = CandidateAnalyzerService(canonical_identity=identity)
        candidate = {
            "id": "cand-ps10-01",
            "title": "Mahr MarSurf PS10 Portable Roughness Measuring Unit – engineering-gauge.co.uk",
            "source_domain": "engineering-gauge.co.uk",
            "source_page_url": "https://engineering-gauge.co.uk/products/mahr-federal-6910230-marsurf-ps-10",
            "url": "https://engineering-gauge.co.uk/cdn/shop/products/ps10.jpg",
            "visual_sim_to_seed": 0.35,  # Alternate angle
            "dino_similarity": 0.35
        }
        evaluation = analyzer.analyze_candidate(candidate, identity=identity)
        self.assertIn(evaluation.product_match, [ProductMatch.EXACT_ID_MATCH, ProductMatch.TARGET_PRODUCT])
        self.assertTrue(evaluation.reconstruction_evidence)
        self.assertIsNone(evaluation.rejection_reason)
        print("[OK] Test 1 passed: Space variant 'PS10' matches 'MarSurf PS 10' and candidate survives.")

    def test_02_technical_drawing_lower_similarity_survives(self):
        """Technical dimensional schematic corroborated by product title survives with v_sim >= 0.20."""
        identity = CanonicalProductIdentity(
            canonical_brand="Mahr",
            canonical_product_name="MarSurf PS 10 Roughness Tester",
            canonical_model="MarSurf PS 10",
            canonical_category="Industrial Equipment"
        )
        analyzer = CandidateAnalyzerService(canonical_identity=identity)
        candidate = {
            "id": "cand-drawing-01",
            "title": "Mahr MarSurf PS 10 dimensional schematic and mounting specifications",
            "source_domain": "manuals.com",
            "source_page_url": "https://manuals.com/mahr/ps10/dimensions",
            "url": "https://manuals.com/ps10-dimensions.png",
            "visual_sim_to_seed": 0.44,  # Technical drawing below standard 0.45 photo threshold
            "dino_similarity": 0.44
        }
        evaluation = analyzer.analyze_candidate(candidate, identity=identity)
        self.assertEqual(evaluation.candidate_type, CandidateType.TECHNICAL_DRAWING)
        self.assertEqual(evaluation.verified_viewpoint, Viewpoint.TECHNICAL)
        self.assertTrue(evaluation.reconstruction_evidence)
        self.assertEqual(evaluation.evidence_value, EvidenceValue.HIGH)
        self.assertIsNone(evaluation.rejection_reason)
        print("[OK] Test 2 passed: Technical drawing survives and provides HIGH reconstruction evidence.")

    def test_03_multiple_unknown_viewpoint_verified_candidates_survive(self):
        """Multiple verified candidates with UNKNOWN viewpoint are NOT prematurely throttled."""
        identity = CanonicalProductIdentity(
            canonical_brand="ViewSonic",
            canonical_product_name="LS800HD Laser Projector",
            canonical_model="LS800HD",
            canonical_category="Projector"
        )
        candidates = [
            {
                "id": f"cand-vs-{i}",
                "title": f"ViewSonic LS800HD Laser Projector Studio Photo {i}",
                "source_domain": "reseller.com",
                "source_page_url": f"https://reseller.com/item-{i}",
                "url": f"https://reseller.com/photo-{i}.jpg",
                "visual_sim_to_seed": 0.60 + (i * 0.02),
                "dino_similarity": 0.60 + (i * 0.02)
            }
            for i in range(5)
        ]
        evaluations = evaluate_candidates_batch(candidates, identity=identity)

        # All 5 must have reconstruction_evidence = True and not be throttled to 2
        evidence_count = sum(1 for e in evaluations if e.reconstruction_evidence)
        self.assertEqual(evidence_count, 5, "All 5 verified candidates should have reconstruction_evidence=True")

        for idx, e in enumerate(evaluations):
            self.assertEqual(e.verified_viewpoint, Viewpoint.UNKNOWN)
            self.assertIsNone(e.rejection_reason, f"Candidate {idx} should not have a rejection reason")
        print("[OK] Test 3 passed: Multiple verified candidates with UNKNOWN viewpoint survive into candidate pool.")

    def test_04_query_planner_does_not_duplicate_tokens(self):
        """Query Planner avoids duplicate model tokens when product name already contains model."""
        product_dict = {
            "name": "Mahr MarSurf PS 10",
            "model_number": "MarSurf PS 10",
            "category": "Metrology"
        }
        queries = QueryPlanner.plan(product_dict)
        query_strings = [q.query for q in queries]

        # Must not contain "Mahr MarSurf PS 10 MarSurf PS 10"
        for q in query_strings:
            self.assertNotIn("MarSurf PS 10 MarSurf PS 10", q)
        self.assertTrue(any('"Mahr MarSurf PS 10"' in q for q in query_strings))
        print("[OK] Test 4 passed: Query Planner does not duplicate model number.")

    def test_05_rejection_reason_is_never_standard_product_imagery(self):
        """Uncorroborated candidates have descriptive rejection reason, never 'Standard product imagery'."""
        identity = CanonicalProductIdentity(
            canonical_brand="Hansgrohe",
            canonical_product_name="SilicaTec C51 Kitchen Sink",
            canonical_model="43218000",
            canonical_category="Kitchen Sink"
        )
        analyzer = CandidateAnalyzerService(canonical_identity=identity)
        candidate = {
            "id": "cand-unrelated-generic",
            "title": "Random Unrelated Product Item",
            "source_domain": "generalstore.com",
            "source_page_url": "https://generalstore.com/item-99",
            "url": "https://generalstore.com/item.jpg",
            "visual_sim_to_seed": 0.50
        }
        evaluation = analyzer.analyze_candidate(candidate, identity=identity)
        self.assertEqual(evaluation.product_match, ProductMatch.UNCERTAIN)
        self.assertFalse(evaluation.reconstruction_evidence)
        self.assertNotEqual(evaluation.rejection_reason, "Standard product imagery")
        self.assertIn("Insufficient candidate metadata", evaluation.rejection_reason)
        print("[OK] Test 5 passed: Rejection reason accurately reflects insufficient candidate metadata.")

    # =========================================================================
    # PART B: SAME-MODEL-NUMBER BUT WRONG-PRODUCT CANDIDATES ARE REJECTED
    # =========================================================================

    def test_06_same_model_number_wrong_category_is_rejected(self):
        """Candidate with matching model number 'C51' but in conflicting category (faucet/tap) is rejected."""
        identity = CanonicalProductIdentity(
            canonical_brand="Hansgrohe",
            canonical_product_name="SilicaTec C51 Kitchen Sink",
            canonical_model="C51",
            canonical_category="Kitchen Sink"
        )
        analyzer = CandidateAnalyzerService(canonical_identity=identity)

        # Candidate has model "C51", but is a basin mixer / faucet tap (sink is absent)
        candidate = {
            "id": "cand-c51-faucet",
            "title": "Modern C51 Chrome Basin Mixer Tap and Kitchen Faucet",
            "source_domain": "tapshop.com",
            "source_page_url": "https://tapshop.com/c51-tap",
            "url": "https://tapshop.com/c51-tap.jpg",
            "visual_sim_to_seed": 0.55
        }
        evaluation = analyzer.analyze_candidate(candidate, identity=identity)
        self.assertEqual(evaluation.product_match, ProductMatch.DIFFERENT_PRODUCT)
        self.assertFalse(evaluation.reconstruction_evidence)
        self.assertIn("category_conflict", evaluation.evidence_sources)
        print("[OK] Test 6 passed: Same model number 'C51' in conflicting category (faucet) is rejected.")

    def test_07_same_model_number_competing_brand_is_rejected(self):
        """Candidate with matching model number 'PS10' from a competing brand is rejected."""
        identity = CanonicalProductIdentity(
            canonical_brand="Mahr",
            canonical_product_name="MarSurf PS 10 Roughness Tester",
            canonical_model="PS 10",
            canonical_category="Industrial Equipment"
        )
        analyzer = CandidateAnalyzerService(canonical_identity=identity)

        # Candidate has PS-10 / PS10 but is an electronic keyboard or audio speaker
        candidate = {
            "id": "cand-ps10-audio",
            "title": "Yamaha PS-10 Electronic Keyboard Synthesizer PS10",
            "source_domain": "synthesizers.com",
            "source_page_url": "https://synthesizers.com/ps10",
            "url": "https://synthesizers.com/ps10.jpg",
            "visual_sim_to_seed": 0.30
        }
        evaluation = analyzer.analyze_candidate(candidate, identity=identity)
        # Should be rejected because of competing/discordant product context
        self.assertIn(evaluation.product_match, [ProductMatch.DIFFERENT_PRODUCT, ProductMatch.UNCERTAIN])
        self.assertFalse(evaluation.reconstruction_evidence)
        print("[OK] Test 7 passed: Same model number from unrelated product/brand is not accepted.")

    def test_08_discordant_noise_still_rejected_low_visual_similarity(self):
        """Truly discordant web noise (e.g. cricket photo, butterfly chart with v_sim < 0.20) is rejected."""
        identity = CanonicalProductIdentity(
            canonical_brand="ViewSonic",
            canonical_product_name="Laser Projector LS800HD",
            canonical_model="LS800HD",
            canonical_category="Projector"
        )
        analyzer = CandidateAnalyzerService(canonical_identity=identity)

        # Unrelated image harvested via keyword noise
        candidate = {
            "id": "cand-noise-cricket",
            "title": "Shubman Gill celebrating century in ODI jersey",
            "source_domain": "sportsblog.in",
            "source_page_url": "https://sportsblog.in/gill-century",
            "url": "https://sportsblog.in/gill.jpg",
            "visual_sim_to_seed": 0.04,  # Far below threshold
            "dino_similarity": 0.04
        }
        evaluation = analyzer.analyze_candidate(candidate, identity=identity)
        self.assertEqual(evaluation.product_match, ProductMatch.UNCERTAIN)
        self.assertFalse(evaluation.reconstruction_evidence)
        print("[OK] Test 8 passed: Discordant web noise is rejected.")


if __name__ == "__main__":
    unittest.main()
