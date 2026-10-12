"""
Unit and Regression Tests for Phase 2: Variant & Appearance Consistency Layer.

Covers:
  1. Exact target color match (MATCH)
  2. Compatible finish / color family (COMPATIBLE)
  3. Conflicting color penalty (CONFLICT)
  4. Unknown color eligibility (UNKNOWN)
  5. Majority-color trap immunity (Zero candidate feedback to target)
  6. Exact model match
  7. Article / configuration difference (Siemens S7-1200 variants)
  8. Query contamination firewall (Query terms never become candidate evidence)
  9. Seed color ambiguity handling
  10. Candidate metadata conflict handling
  11. Technical drawing with unstated / conflicting appearance
  12. Viewpoint vs. variant consistency tradeoff (Geometric fallback)
  13. Generic unbranded product color handling
  14. Accessory with matching color rejected by identity layer
  15. Different product with same color rejected by identity layer
  16. EvidenceMatrix appearance metrics and gap detection
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
    normalize_product_identity
)
from services.variant_policy import (
    VariantEvidence,
    VariantState,
    VariantSource,
    TargetVariantDefinition,
    resolve_target_variant,
    extract_candidate_variant_evidence,
    normalize_color
)
from services.candidate_analyzer_service import (
    CandidateAnalyzerService,
    CandidateEvaluation,
    ProductMatch,
    CandidateType,
    Viewpoint,
    EvidenceValue
)
from services.reference_pool_service import (
    ReferencePoolCurationService,
    CuratedReferencePool,
    EvidenceMatrix
)


class TestVariantConsistency(unittest.TestCase):

    def setUp(self):
        # Sony WH-1000XM5 Black Target
        self.sony_black_identity = normalize_product_identity(ProductIdentity(
            brand="Sony",
            product_name="WH-1000XM5 Wireless Noise Canceling Headphones",
            model_number="WH1000XM5/B",
            color="Black",
            category="Consumer Electronics",
            source_urls=["https://electronics.sony.com/audio/headphones/headband/p/wh1000xm5-b"]
        ))
        self.sony_analyzer = CandidateAnalyzerService(canonical_identity=self.sony_black_identity)

        # Jaguar XE SV Project 8 Velocity Blue Target
        self.jaguar_blue_identity = normalize_product_identity(ProductIdentity(
            brand="Jaguar",
            product_name="XE SV Project 8 Sedan",
            model_number="XE-SV-P8",
            color="Velocity Blue",
            category="Automotive",
            user_prompt="Jaguar XE SV Project 8 Velocity Blue track edition"
        ))
        self.jaguar_analyzer = CandidateAnalyzerService(canonical_identity=self.jaguar_blue_identity)

    # ------------------------------------------------------------------------
    # 1. Exact target color match (MATCH)
    # ------------------------------------------------------------------------
    def test_01_exact_target_color_match(self):
        cand = {
            "id": "c1",
            "url": "https://electronics.sony.com/img/wh1000xm5_black_front.jpg",
            "source_page_url": "https://electronics.sony.com/audio/wh1000xm5-black",
            "source_domain": "electronics.sony.com",
            "title": "Sony WH-1000XM5 Wireless Headphones - Black",
            "snippet": "Premium noise canceling headphones in Matte Black finish",
            "score": 0.95
        }
        res = self.sony_analyzer.analyze_candidate(cand)
        self.assertIn(res.product_match, [ProductMatch.TARGET_PRODUCT, ProductMatch.EXACT_ID_MATCH])
        self.assertEqual(res.variant_evidence.evidence_state, VariantState.MATCH)
        self.assertEqual(res.variant_evidence.color_normalized, "black")
        self.assertGreaterEqual(res.variant_evidence.confidence, 0.85)
        self.assertTrue(res.reconstruction_evidence)
        print(f"[OK] Test 1 passed: Exact color match recognized ({res.variant_evidence.color_raw})")

    # ------------------------------------------------------------------------
    # 2. Compatible finish / color family (COMPATIBLE)
    # ------------------------------------------------------------------------
    def test_02_compatible_color_finish(self):
        cand = {
            "id": "c2",
            "url": "https://example.com/jaguar_p8_blue.jpg",
            "source_page_url": "https://example.com/car-reviews/jaguar-p8",
            "source_domain": "example.com",
            "title": "Jaguar XE SV Project 8 in Metallic Blue on track",
            "snippet": "V8 supercharged sedan with carbon fiber aero in metallic blue",
            "score": 0.90
        }
        res = self.jaguar_analyzer.analyze_candidate(cand)
        self.assertIn(res.product_match, [ProductMatch.TARGET_PRODUCT, ProductMatch.EXACT_ID_MATCH])
        self.assertEqual(res.variant_evidence.evidence_state, VariantState.COMPATIBLE)
        self.assertEqual(res.variant_evidence.color_normalized, "blue")
        self.assertTrue(res.reconstruction_evidence)
        print(f"[OK] Test 2 passed: Compatible color family recognized ({res.variant_evidence.color_raw} -> blue)")

    # ------------------------------------------------------------------------
    # 3. Conflicting color penalty (CONFLICT)
    # ------------------------------------------------------------------------
    def test_03_conflicting_color_penalty(self):
        cand = {
            "id": "c3",
            "url": "https://electronics.sony.com/img/wh1000xm5_silver.jpg",
            "source_page_url": "https://electronics.sony.com/audio/wh1000xm5-silver",
            "source_domain": "electronics.sony.com",
            "title": "Sony WH-1000XM5 Wireless Headphones - Platinum Silver",
            "snippet": "Comfortable noise canceling in platinum silver",
            "score": 0.92
        }
        res = self.sony_analyzer.analyze_candidate(cand)
        self.assertIn(res.product_match, [ProductMatch.TARGET_PRODUCT, ProductMatch.EXACT_ID_MATCH])
        self.assertEqual(res.variant_evidence.evidence_state, VariantState.CONFLICT)
        self.assertEqual(res.variant_evidence.color_normalized, "silver")
        self.assertIn("Platinum Silver", res.variant_evidence.conflict_details)
        print(f"[OK] Test 3 passed: Conflicting color flagged CONFLICT ({res.variant_evidence.conflict_details})")

    # ------------------------------------------------------------------------
    # 4. Unknown color eligibility (UNKNOWN)
    # ------------------------------------------------------------------------
    def test_04_unknown_color_eligibility(self):
        cand = {
            "id": "c4",
            "url": "https://example.com/sony_headset.jpg",
            "source_page_url": "https://example.com/sony-headphones",
            "source_domain": "example.com",
            "title": "Sony WH-1000XM5 Wireless Over-Ear Headphones",
            "snippet": "Industry leading noise cancellation with dual processors",
            "score": 0.88
        }
        res = self.sony_analyzer.analyze_candidate(cand)
        self.assertIn(res.product_match, [ProductMatch.TARGET_PRODUCT, ProductMatch.EXACT_ID_MATCH])
        self.assertEqual(res.variant_evidence.evidence_state, VariantState.UNKNOWN)
        self.assertTrue(res.reconstruction_evidence)
        print("[OK] Test 4 passed: Unknown color candidate remains eligible for reconstruction")


    # ------------------------------------------------------------------------
    # 5. Majority-color trap immunity
    # ------------------------------------------------------------------------
    def test_05_majority_color_trap_immunity(self):
        """
        Verify that an unconstrained product search (no user color specified)
        does NOT set target_color to Black merely because 80% of candidates are Black.
        """
        unconstrained_ident = normalize_product_identity(ProductIdentity(
            brand="Sony",
            product_name="WH-1000XM5 Wireless Headphones",
            model_number="WH1000XM5",
            category="Consumer Electronics"
        ))
        target_var = resolve_target_variant(unconstrained_ident)
        self.assertFalse(target_var.is_color_specified)
        self.assertIsNone(target_var.target_color_raw)
        self.assertIsNone(target_var.target_color_normalized)

        # Build candidate pool with 4 Black candidates and 1 Silver candidate
        candidates = []
        evaluations = []
        analyzer = CandidateAnalyzerService(canonical_identity=unconstrained_ident)

        for i in range(4):
            c_dict = {
                "id": f"blk_{i}",
                "url": f"https://example.com/black_{i}.jpg",
                "title": f"Sony WH-1000XM5 Black Edition {i}",
                "score": 0.90
            }
            candidates.append(c_dict)
            evaluations.append(analyzer.analyze_candidate(c_dict))

        c_silver = {
            "id": "slv_0",
            "url": "https://example.com/silver_0.jpg",
            "title": "Sony WH-1000XM5 Platinum Silver",
            "score": 0.90
        }
        candidates.append(c_silver)
        evaluations.append(analyzer.analyze_candidate(c_silver))

        curated = ReferencePoolCurationService.curate_pool(
            candidates=candidates,
            evaluations=evaluations,
            max_candidates=5,
            target_variant=target_var
        )

        # Both black and silver must be present without penalty since target is UNKNOWN
        selected_ids = [r["id"] for r in curated.selected_references]
        self.assertIn("slv_0", selected_ids)
        self.assertEqual(curated.evidence_matrix.target_color, None)
        self.assertIn("TARGET_COLOR_UNCONFIRMED", curated.evidence_matrix.unresolved_appearance_gaps)
        print("[OK] Test 5 passed: Majority-color trap prevented; target remains UNKNOWN and both colors retained.")

    # ------------------------------------------------------------------------
    # 6. Exact model match
    # ------------------------------------------------------------------------
    def test_06_exact_model_match(self):
        siemens_ident = normalize_product_identity(ProductIdentity(
            brand="Siemens",
            product_name="SIMATIC S7-1200 CPU 1214C",
            model_number="6ES7214-1AG40-0XB0",
            category="Industrial Automation"
        ))
        analyzer = CandidateAnalyzerService(canonical_identity=siemens_ident)
        cand = {
            "id": "s1",
            "url": "https://mall.industry.siemens.com/img/6es7214-1ag40-0xb0.jpg",
            "source_page_url": "https://mall.industry.siemens.com/product?6es7214-1ag40-0xb0",
            "source_domain": "mall.industry.siemens.com",
            "title": "SIMATIC S7-1200, CPU 1214C, compact CPU, DC/DC/DC, 6ES7214-1AG40-0XB0",
            "snippet": "Compact CPU with onboard I/O, supply DC 20.4-28.8V DC",
            "score": 0.98
        }
        res = analyzer.analyze_candidate(cand)
        self.assertIn(res.product_match, [ProductMatch.TARGET_PRODUCT, ProductMatch.EXACT_ID_MATCH])

        self.assertEqual(res.variant_evidence.evidence_state, VariantState.MATCH)
        self.assertEqual(res.variant_evidence.model_variant, "6ES7214-1AG40-0XB0")
        print("[OK] Test 6 passed: Exact Siemens S7-1200 model variant match recognized.")

    # ------------------------------------------------------------------------
    # 7. Article / configuration difference (Siemens S7-1200 1AG40 vs 1BG40)
    # ------------------------------------------------------------------------
    def test_07_article_configuration_difference(self):
        siemens_ident = normalize_product_identity(ProductIdentity(
            brand="Siemens",
            product_name="SIMATIC S7-1200 CPU 1214C",
            model_number="6ES7214-1AG40-0XB0",
            category="Industrial Automation"
        ))
        analyzer = CandidateAnalyzerService(canonical_identity=siemens_ident)
        cand = {
            "id": "s2",
            "url": "https://example.com/siemens_1bg40.jpg",
            "source_page_url": "https://example.com/siemens-s7-1200-relay",
            "source_domain": "example.com",
            "title": "Siemens SIMATIC S7-1200 CPU 1214C AC/DC/Relay (6ES7214-1BG40-0XB0)",
            "snippet": "AC/DC/Relay compact PLC controller 6ES7214-1BG40-0XB0",
            "score": 0.90
        }
        res = analyzer.analyze_candidate(cand)
        self.assertEqual(res.variant_evidence.evidence_state, VariantState.CONFLICT)
        self.assertIn("6ES7214-1BG40-0XB0", res.variant_evidence.conflict_details)
        print(f"[OK] Test 7 passed: S7-1200 AC/DC/Relay variant conflict identified ({res.variant_evidence.conflict_details})")

    # ------------------------------------------------------------------------
    # 8. Query contamination firewall
    # ------------------------------------------------------------------------
    def test_08_query_contamination_firewall(self):
        """
        Verify that search query requesting 'Black Sony WH-1000XM5 rear view' does NOT
        cause a generic / unrelated candidate to inherit 'black' color or 'REAR' viewpoint.
        """
        cand = {
            "id": "c_query_test",
            "url": "https://example.com/nature_shot.jpg",
            "query": "Black Sony WH-1000XM5 rear view",
            "query_family": "PRODUCT_VIEWPOINT",
            "target_evidence": "REAR",
            "branch_angle": "Rear View",
            "title": "Wild prancing mustang in field",
            "snippet": "Beautiful horse galloping across grass",
            "score": 0.30
        }
        res = self.sony_analyzer.analyze_candidate(cand)
        # Identity must reject or mark uncertain
        self.assertIn(res.product_match, [ProductMatch.DIFFERENT_PRODUCT, ProductMatch.UNCERTAIN])
        self.assertFalse(res.reconstruction_evidence)
        # Variant must NOT be MATCH
        self.assertEqual(res.variant_evidence.evidence_state, VariantState.UNKNOWN)
        self.assertIsNone(res.variant_evidence.color_raw)
        # Viewpoint must NOT be REAR
        self.assertEqual(res.verified_viewpoint, Viewpoint.UNKNOWN)
        print("[OK] Test 8 passed: Query terms strictly prohibited from contaminating candidate evidence.")

    # ------------------------------------------------------------------------
    # 9. Seed ambiguity
    # ------------------------------------------------------------------------
    def test_09_seed_ambiguity(self):
        raw_ident = ProductIdentity(
            brand="Apple",
            product_name="Magic Mouse",
            seed_image="https://example.com/seed.jpg"
        )
        target = resolve_target_variant(raw_ident)
        self.assertFalse(target.is_color_specified)
        self.assertIsNone(target.target_color_raw)
        print("[OK] Test 9 passed: Seed image without explicit metadata does not fabricate false color confidence.")

    # ------------------------------------------------------------------------
    # 10. Candidate metadata conflict
    # ------------------------------------------------------------------------
    def test_10_candidate_metadata_conflict(self):
        cand = {
            "id": "c10",
            "url": "https://example.com/contradictory.jpg",
            "title": "Sony WH-1000XM5 Wireless Headphones (Black)",
            "snippet": "Sleek silver lightweight finish with carry case",
            "dom_metadata": {"color": "Silver"},
            "score": 0.88
        }
        # Evaluated against Sony Black target
        res = self.sony_analyzer.analyze_candidate(cand)
        # DOM metadata with Silver overrides or contradicts title
        self.assertEqual(res.variant_evidence.evidence_state, VariantState.CONFLICT)
        print("[OK] Test 10 passed: Candidate metadata conflict identified cleanly.")

    # ------------------------------------------------------------------------
    # 11. Technical drawing with unstated / conflicting appearance
    # ------------------------------------------------------------------------
    def test_11_technical_drawing_unstated_appearance(self):
        cand = {
            "id": "c_tech",
            "url": "https://electronics.sony.com/img/wh1000xm5_dimension_cad.jpg",
            "source_page_url": "https://electronics.sony.com/support/dimensions",
            "source_domain": "electronics.sony.com",
            "title": "Sony WH-1000XM5 Dimensional Blueprint & Technical Drawing",
            "snippet": "Outer dimensions 240x180x80 mm headset chassis schematic",
            "score": 0.95
        }
        res = self.sony_analyzer.analyze_candidate(cand)
        self.assertEqual(res.candidate_type, CandidateType.TECHNICAL_DRAWING)
        self.assertEqual(res.verified_viewpoint, Viewpoint.TECHNICAL)
        self.assertEqual(res.evidence_value, EvidenceValue.HIGH)
        self.assertTrue(res.reconstruction_evidence)
        # Variant is UNKNOWN because CAD drawing has no color
        self.assertEqual(res.variant_evidence.evidence_state, VariantState.UNKNOWN)
        print("[OK] Test 11 passed: Technical CAD drawing retained as HIGH evidence value despite UNKNOWN color.")

    # ------------------------------------------------------------------------
    # 12. Viewpoint vs. variant consistency tradeoff (Geometric fallback)
    # ------------------------------------------------------------------------
    def test_12_viewpoint_vs_variant_tradeoff(self):
        """
        If Target is Black, and pool contains:
        - 3 Front Views in Black
        - 1 Rear View in Silver (only rear view in existence)
        The Silver rear view must survive into selected references via geometric fallback.
        """
        candidates = []
        evaluations = []

        # 3 Front views in Black
        for i in range(3):
            c = {
                "id": f"front_blk_{i}",
                "url": f"https://example.com/front_blk_{i}.jpg",
                "title": f"Sony WH-1000XM5 Black Front Face View {i}",
                "score": 0.95
            }
            candidates.append(c)
            eval_obj = self.sony_analyzer.analyze_candidate(c)
            eval_obj.verified_viewpoint = Viewpoint.FRONT
            eval_obj.viewpoint_confidence = 0.90
            evaluations.append(eval_obj)

        # 1 Rear view in Silver
        c_rear = {
            "id": "rear_slv_0",
            "url": "https://example.com/rear_slv_0.jpg",
            "title": "Sony WH-1000XM5 Platinum Silver Rear Elevation Backside View",
            "score": 0.92
        }
        candidates.append(c_rear)
        eval_rear = self.sony_analyzer.analyze_candidate(c_rear)
        eval_rear.verified_viewpoint = Viewpoint.REAR
        eval_rear.viewpoint_confidence = 0.90
        evaluations.append(eval_rear)

        target_var = resolve_target_variant(self.sony_black_identity)
        curated = ReferencePoolCurationService.curate_pool(
            candidates=candidates,
            evaluations=evaluations,
            max_candidates=4,
            target_variant=target_var
        )

        selected_ids = [r["id"] for r in curated.selected_references]
        self.assertIn("rear_slv_0", selected_ids)
        # Rear view selected via geometric fallback
        rear_card = next(r for r in curated.selected_references if r["id"] == "rear_slv_0")
        self.assertIn("CONFLICT_VARIANT_GEOMETRIC_FALLBACK", rear_card["selection_reason"])
        self.assertGreaterEqual(curated.evidence_matrix.rear_coverage, 0.50)
        print("[OK] Test 12 passed: Sole rear view admitted as geometric fallback, preserving orthogonal coverage.")

    # ------------------------------------------------------------------------
    # 13. Generic unbranded product color handling
    # ------------------------------------------------------------------------
    def test_13_generic_unbranded_product(self):
        generic_ident = normalize_product_identity(ProductIdentity(
            product_name="Ergonomic Mesh Office Chair",
            color="Grey",
            category="Office Furniture"
        ))
        analyzer = CandidateAnalyzerService(canonical_identity=generic_ident)
        cand = {
            "id": "ch1",
            "url": "https://example.com/grey_chair.jpg",
            "title": "Ergonomic Mesh Office Chair in Grey",
            "snippet": "High back breathable mesh task chair in grey finish",
            "score": 0.85
        }
        res = analyzer.analyze_candidate(cand)
        self.assertEqual(res.variant_evidence.evidence_state, VariantState.MATCH)
        self.assertEqual(res.variant_evidence.color_normalized, "gray")
        print("[OK] Test 13 passed: Generic unbranded product color normalized and matched cleanly.")

    # ------------------------------------------------------------------------
    # 14. Accessory with matching color rejected by identity layer
    # ------------------------------------------------------------------------
    def test_14_accessory_with_matching_color(self):
        sink_ident = normalize_product_identity(ProductIdentity(
            brand="Hansgrohe",
            product_name="C51 Sink Combi 660 Select",
            model_number="C51-F660-07",
            article_number="43218000",
            color="Chrome",
            category="Sanitary Ware"
        ))
        analyzer = CandidateAnalyzerService(canonical_identity=sink_ident)
        cand = {
            "id": "acc1",
            "url": "https://example.com/soap_dispenser.jpg",
            "title": "Hansgrohe Chrome Soap Dispenser for Kitchen Sink",
            "snippet": "Matching chrome soap dispenser accessory for C51 sink",
            "score": 0.85
        }
        res = analyzer.analyze_candidate(cand)
        self.assertEqual(res.candidate_type, CandidateType.ACCESSORY)
        self.assertFalse(res.reconstruction_evidence)
        print("[OK] Test 14 passed: Accessory with matching color correctly discarded from 3D reference pool.")

    # ------------------------------------------------------------------------
    # 15. Different product with same color rejected by identity layer
    # ------------------------------------------------------------------------
    def test_15_different_product_with_same_color(self):
        cand = {
            "id": "diff1",
            "url": "https://www.blanco.com/img/blanco_black.jpg",
            "source_domain": "blanco.com",
            "title": "Blanco Zenar 45 Inset Kitchen Sink Black Granite",
            "snippet": "Single bowl black granite sink",
            "score": 0.80
        }
        sink_ident = normalize_product_identity(ProductIdentity(
            brand="Hansgrohe",
            product_name="C51 Sink Combi 660 Select",
            model_number="43218000",
            color="Black",
            category="Sanitary Ware"
        ))
        analyzer = CandidateAnalyzerService(canonical_identity=sink_ident)
        res = analyzer.analyze_candidate(cand)
        self.assertEqual(res.product_match, ProductMatch.DIFFERENT_PRODUCT)
        self.assertFalse(res.reconstruction_evidence)
        print("[OK] Test 15 passed: Competing brand product in matching color discarded by identity layer.")

    # ------------------------------------------------------------------------
    # 16. EvidenceMatrix appearance metrics & gap detection
    # ------------------------------------------------------------------------
    def test_16_evidence_matrix_appearance_metrics(self):
        candidates = []
        evaluations = []

        for i in range(2):
            c = {
                "id": f"c_blk_{i}",
                "url": f"https://example.com/blk_{i}.jpg",
                "title": f"Sony WH-1000XM5 Black Headset {i}",
                "score": 0.95
            }
            candidates.append(c)
            eval_obj = self.sony_analyzer.analyze_candidate(c)
            evaluations.append(eval_obj)

        target_var = resolve_target_variant(self.sony_black_identity)
        curated = ReferencePoolCurationService.curate_pool(
            candidates=candidates,
            evaluations=evaluations,
            max_candidates=5,
            target_variant=target_var
        )

        ev_mat = curated.evidence_matrix
        self.assertEqual(ev_mat.target_color, "Black")
        self.assertEqual(ev_mat.matching_variant_count, 2)
        self.assertEqual(ev_mat.conflicting_variant_count, 0)
        self.assertEqual(ev_mat.variant_consistency_score, 1.0)
        self.assertIn("Black", ev_mat.observed_variants)
        self.assertNotIn("TARGET_COLOR_UNCONFIRMED", ev_mat.unresolved_appearance_gaps)
        print(f"[OK] Test 16 passed: EvidenceMatrix appearance score={ev_mat.variant_consistency_score}, observed={ev_mat.observed_variants}")


if __name__ == "__main__":
    unittest.main()
