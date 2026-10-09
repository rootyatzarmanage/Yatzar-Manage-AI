"""
Unit and Regression Tests for Candidate Semantic + Viewpoint Verification Layer (V2).

Tests the 18 specific requirements:
  1. Exact target product -> TARGET_PRODUCT
  2. Same category, different product -> DIFFERENT_PRODUCT
  3. Same brand, different model -> DIFFERENT_PRODUCT
  4. Accessory -> ACCESSORY
  5. Spare part -> SPARE_PART
  6. Packaging -> PACKAGING
  7. Technical drawing -> TECHNICAL_DRAWING
  8. Manual -> MANUAL_DOCUMENT
  9. Ambiguous candidate -> UNCERTAIN
  10. Front -> FRONT
  11. Rear -> REAR
  12. Bottom -> BOTTOM
  13. Detail -> DETAIL
  14. Exact target technical drawing -> useful evidence (HIGH)
  15. Low DINO similarity does NOT automatically reject target product
  16. High DINO similarity does NOT automatically prove target product
  17. No candidate can silently become a Nike/demo product
  18. Product identity remains consistent throughout analysis
"""

import os
import sys
import unittest

backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend"))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from services.identifier_policy import (
    ProductIdentity,
    CanonicalProductIdentity,
    normalize_product_identity
)
from services.candidate_analyzer_service import (
    CandidateAnalyzerService,
    CandidateEvaluation,
    ProductMatch,
    CandidateType,
    Viewpoint,
    EvidenceValue,
    evaluate_candidates_batch
)


class TestCandidateAnalyzerService(unittest.TestCase):

    def setUp(self):
        self.hansgrohe_identity = normalize_product_identity(ProductIdentity(
            brand="Hansgrohe",
            product_name="C51 Sink Combi 660 Select",
            model_number="C51-F660-07",
            article_number="43218000",
            category="Sanitary Ware",
            official_domains=["hansgrohe.com", "pro.hansgrohe.com"]
        ))
        self.analyzer = CandidateAnalyzerService(canonical_identity=self.hansgrohe_identity)

    # ------------------------------------------------------------------------
    # 1. Exact target product -> TARGET_PRODUCT
    # ------------------------------------------------------------------------
    def test_01_exact_target_product(self):
        cand = {
            "id": "c1",
            "url": "https://pro.hansgrohe.com/img/43218000_front.jpg",
            "source_page_url": "https://pro.hansgrohe.com/articledetail-43218000",
            "source_domain": "pro.hansgrohe.com",
            "title": "Hansgrohe C51 Sink Combi 660 Select 43218000",
            "snippet": "Stainless steel single bowl kitchen sink with drainer",
            "score": 0.88,
            "angle": "Front View"
        }
        res = self.analyzer.analyze_candidate(cand)
        self.assertIn(res.product_match, [ProductMatch.TARGET_PRODUCT, ProductMatch.EXACT_ID_MATCH])
        self.assertGreaterEqual(res.product_match_confidence, 0.90)

        self.assertTrue(res.reconstruction_evidence)
        self.assertEqual(res.verified_viewpoint, Viewpoint.FRONT)
        print(f"[OK] Test 1 passed: Exact target product recognized ({res.explanation})")

    # ------------------------------------------------------------------------
    # 2. Same category, different product (competing brand) -> DIFFERENT_PRODUCT
    # ------------------------------------------------------------------------
    def test_02_same_category_different_brand(self):
        cand = {
            "id": "c2",
            "url": "https://www.blanco.com/img/blanco_zenar_45.jpg",
            "source_page_url": "https://www.blanco.com/kitchen-sinks",
            "source_domain": "blanco.com",
            "title": "Blanco Zenar 45 S Inset Kitchen Sink",
            "snippet": "Single bowl stainless steel kitchen sink Blanco",
            "score": 0.82
        }
        res = self.analyzer.analyze_candidate(cand)
        self.assertEqual(res.product_match, ProductMatch.DIFFERENT_PRODUCT)
        self.assertFalse(res.reconstruction_evidence)
        self.assertEqual(res.evidence_value, EvidenceValue.NONE)
        self.assertIn("Blanco", res.rejection_reason)
        print(f"[OK] Test 2 passed: Competing brand sink rejected ({res.rejection_reason})")

    # ------------------------------------------------------------------------
    # 3. Same brand, different model -> DIFFERENT_PRODUCT
    # ------------------------------------------------------------------------
    def test_03_same_brand_different_article(self):
        cand = {
            "id": "c3",
            "url": "https://pro.hansgrohe.com/img/43229000_sink.jpg",
            "source_page_url": "https://pro.hansgrohe.com/articledetail-43229000",
            "source_domain": "pro.hansgrohe.com",
            "title": "Hansgrohe S51 Sink Unit 43229000",
            "snippet": "Hansgrohe S51 double bowl kitchen sink article 43229000",
            "score": 0.85
        }
        res = self.analyzer.analyze_candidate(cand)
        self.assertEqual(res.product_match, ProductMatch.DIFFERENT_PRODUCT)
        self.assertFalse(res.reconstruction_evidence)
        self.assertIn("43229000", res.rejection_reason)
        print(f"[OK] Test 3 passed: Different model from same brand rejected ({res.rejection_reason})")

    # ------------------------------------------------------------------------
    # 4. Accessory -> ACCESSORY
    # ------------------------------------------------------------------------
    def test_04_accessory_classification(self):
        cand = {
            "id": "c4",
            "url": "https://pro.hansgrohe.com/img/cutting_board.jpg",
            "title": "Hansgrohe Accessory Walnut Cutting Board for C51 Sink 43218000",
            "snippet": "High quality cutting board accessory for kitchen sink",
            "score": 0.65
        }
        res = self.analyzer.analyze_candidate(cand)
        self.assertEqual(res.candidate_type, CandidateType.ACCESSORY)
        print(f"[OK] Test 4 passed: Accessory correctly tagged ({res.candidate_type.value})")

    # ------------------------------------------------------------------------
    # 5. Spare part -> SPARE_PART
    # ------------------------------------------------------------------------
    def test_05_spare_part_classification(self):
        cand = {
            "id": "c5",
            "url": "https://pro.hansgrohe.com/img/43218000_spareparts.png",
            "title": "Hansgrohe 43218000 Ersatzteile Spare Parts Diagram",
            "snippet": "Exploded diagram and spare parts list for C51 660 Select",
            "score": 0.70
        }
        res = self.analyzer.analyze_candidate(cand)
        self.assertEqual(res.candidate_type, CandidateType.SPARE_PART)
        self.assertTrue(res.reconstruction_evidence)
        self.assertIn(res.evidence_value, [EvidenceValue.MEDIUM, EvidenceValue.HIGH])
        print(f"[OK] Test 5 passed: Spare parts diagram retained as structural evidence")

    # ------------------------------------------------------------------------
    # 6. Packaging -> PACKAGING
    # ------------------------------------------------------------------------
    def test_06_packaging_classification(self):
        cand = {
            "id": "c6",
            "url": "https://img.com/carton_box_43218000.jpg",
            "title": "Hansgrohe 43218000 packaging cardboard box",
            "snippet": "Shipping carton crate packaging for sink",
            "score": 0.60
        }
        res = self.analyzer.analyze_candidate(cand)
        self.assertEqual(res.candidate_type, CandidateType.PACKAGING)
        self.assertFalse(res.reconstruction_evidence)
        self.assertEqual(res.evidence_value, EvidenceValue.NONE)
        print(f"[OK] Test 6 passed: Packaging discarded from 3D reconstruction")

    # ------------------------------------------------------------------------
    # 7. Technical drawing -> TECHNICAL_DRAWING
    # ------------------------------------------------------------------------
    def test_07_technical_drawing_classification(self):
        cand = {
            "id": "c7",
            "url": "https://pro.hansgrohe.com/img/43218000_masszeichnung.png",
            "title": "Hansgrohe 43218000 Maszeichnung Dimensional Technical Drawing",
            "snippet": "Cutout dimensions 660x450mm scale CAD schematic",
            "score": 0.58
        }
        res = self.analyzer.analyze_candidate(cand)
        self.assertEqual(res.candidate_type, CandidateType.TECHNICAL_DRAWING)
        self.assertEqual(res.verified_viewpoint, Viewpoint.TECHNICAL)
        self.assertTrue(res.reconstruction_evidence)
        self.assertEqual(res.evidence_value, EvidenceValue.HIGH)
        print(f"[OK] Test 7 passed: Technical drawing identified with HIGH evidence value")

    # ------------------------------------------------------------------------
    # 8. Manual -> MANUAL_DOCUMENT
    # ------------------------------------------------------------------------
    def test_08_manual_document_classification(self):
        cand = {
            "id": "c8",
            "url": "https://pro.hansgrohe.com/manual_43218000.pdf_preview.jpg",
            "title": "Hansgrohe 43218000 User Manual & Installation Datasheet",
            "snippet": "Bedienungsanleitung PDF document preview",
            "score": 0.55
        }
        res = self.analyzer.analyze_candidate(cand)
        self.assertEqual(res.candidate_type, CandidateType.MANUAL_DOCUMENT)
        print(f"[OK] Test 8 passed: Manual document classified ({res.candidate_type.value})")

    # ------------------------------------------------------------------------
    # 9. Ambiguous candidate -> UNCERTAIN
    # ------------------------------------------------------------------------
    def test_09_ambiguous_candidate_uncertain(self):
        cand = {
            "id": "c9",
            "url": "https://images.com/sink_random.jpg",
            "title": "Modern Kitchen Sink Inset",
            "snippet": "Modern design stainless steel kitchen sink for home",
            "score": 0.78
        }
        res = self.analyzer.analyze_candidate(cand)
        self.assertEqual(res.product_match, ProductMatch.UNCERTAIN)
        self.assertFalse(res.reconstruction_evidence)
        print(f"[OK] Test 9 passed: Ambiguous sink safely flagged UNCERTAIN")

    # ------------------------------------------------------------------------
    # 10 - 13. Viewpoint Verifications (FRONT, REAR, BOTTOM, DETAIL)
    # ------------------------------------------------------------------------
    def test_10_viewpoint_front(self):
        cand = {"id": "c10", "title": "Hansgrohe 43218000 Front View Face", "score": 0.90}
        res = self.analyzer.analyze_candidate(cand)
        self.assertEqual(res.verified_viewpoint, Viewpoint.FRONT)

    def test_11_viewpoint_rear(self):
        cand = {"id": "c11", "title": "Hansgrohe 43218000 Backside Rear View", "score": 0.85}
        res = self.analyzer.analyze_candidate(cand)
        self.assertEqual(res.verified_viewpoint, Viewpoint.REAR)

    def test_12_viewpoint_bottom(self):
        cand = {"id": "c12", "title": "Hansgrohe 43218000 Unteransicht Underside Bottom View", "score": 0.75}
        res = self.analyzer.analyze_candidate(cand)
        self.assertEqual(res.verified_viewpoint, Viewpoint.BOTTOM)
        self.assertTrue(res.reconstruction_evidence)
        self.assertEqual(res.evidence_value, EvidenceValue.HIGH)

    def test_13_viewpoint_detail(self):
        cand = {"id": "c13", "title": "Hansgrohe 43218000 Drain Strainer Closeup Detail", "score": 0.80}
        res = self.analyzer.analyze_candidate(cand)
        self.assertEqual(res.verified_viewpoint, Viewpoint.DETAIL)

    # ------------------------------------------------------------------------
    # 14. Exact target technical drawing -> useful evidence (HIGH)
    # ------------------------------------------------------------------------
    def test_14_exact_target_technical_drawing_evidence(self):
        cand = {
            "id": "c14",
            "source_domain": "pro.hansgrohe.com",
            "title": "Hansgrohe 43218000 Cutout Dimensions Technical Drawing",
            "snippet": "660x450mm dimensions blueprint",
            "score": 0.60
        }
        res = self.analyzer.analyze_candidate(cand)
        self.assertTrue(res.reconstruction_evidence)
        self.assertEqual(res.evidence_value, EvidenceValue.HIGH)
        print(f"[OK] Test 14 passed: Target dimensional schematic is HIGH value reconstruction evidence")

    # ------------------------------------------------------------------------
    # 15. Low DINO similarity does NOT automatically reject target product
    # ------------------------------------------------------------------------
    def test_15_low_dino_similarity_does_not_reject_target(self):
        cand = {
            "id": "c15",
            "source_domain": "pro.hansgrohe.com",
            "title": "Hansgrohe C51 Sink 43218000 Bottom Underside Profile",
            "snippet": "Underside view of Hansgrohe 43218000 with drain pipes",
            "score": 0.42  # Very low visual cosine vs front seed!
        }
        res = self.analyzer.analyze_candidate(cand)
        self.assertIn(res.product_match, [ProductMatch.TARGET_PRODUCT, ProductMatch.EXACT_ID_MATCH])
        self.assertTrue(res.reconstruction_evidence)
        self.assertEqual(res.verified_viewpoint, Viewpoint.BOTTOM)
        print(f"[OK] Test 15 passed: Low DINO similarity (0.42) successfully retained for bottom view")

    # ------------------------------------------------------------------------
    # 16. High DINO similarity does NOT automatically prove target product
    # ------------------------------------------------------------------------
    def test_16_high_dino_similarity_does_not_prove_target(self):
        cand = {
            "id": "c16",
            "title": "Generic Unbranded Stainless Steel Sink",
            "snippet": "Standard square kitchen sink",
            "score": 0.98  # Extremely high visual cosine to a square sink!
        }
        res = self.analyzer.analyze_candidate(cand)
        # Even with 0.98 DINO similarity, it is UNCERTAIN because product identity is unproven!
        self.assertNotEqual(res.product_match, ProductMatch.TARGET_PRODUCT)
        self.assertFalse(res.reconstruction_evidence)
        print(f"[OK] Test 16 passed: High DINO similarity (0.98) did not falsely prove target product")

    # ------------------------------------------------------------------------
    # 17. No candidate can silently become a Nike/demo product
    # ------------------------------------------------------------------------
    def test_17_no_silent_demo_product_leakage(self):
        cand = {
            "id": "c17",
            "title": "Nike Air Max 90 Infrared Sneaker",
            "snippet": "Running shoes with waffle outsole",
            "score": 0.20
        }
        res = self.analyzer.analyze_candidate(cand)
        self.assertEqual(res.product_match, ProductMatch.DIFFERENT_PRODUCT)
        self.assertFalse(res.reconstruction_evidence)
        self.assertEqual(res.evidence_value, EvidenceValue.NONE)
        print(f"[OK] Test 17 passed: Nike candidate strictly rejected from Hansgrohe evidence pool")

    # ------------------------------------------------------------------------
    # 18. Product identity remains consistent throughout analysis
    # ------------------------------------------------------------------------
    def test_18_identity_consistency(self):
        cand_list = [
            {"id": "a1", "title": "Hansgrohe 43218000 Front", "score": 0.90},
            {"id": "a2", "title": "Hansgrohe 43218000 Maszeichnung", "score": 0.60},
            {"id": "a3", "title": "Blanco Sink", "score": 0.85},
            {"id": "a4", "title": "Hansgrohe 43218000 Bottom View", "score": 0.70}
        ]
        evaluations = evaluate_candidates_batch(cand_list, identity=self.hansgrohe_identity)
        self.assertEqual(len(evaluations), 4)
        self.assertIn(evaluations[0].product_match, [ProductMatch.TARGET_PRODUCT, ProductMatch.EXACT_ID_MATCH])
        self.assertIn(evaluations[1].product_match, [ProductMatch.TARGET_PRODUCT, ProductMatch.EXACT_ID_MATCH])
        self.assertEqual(evaluations[2].product_match, ProductMatch.DIFFERENT_PRODUCT)
        self.assertIn(evaluations[3].product_match, [ProductMatch.TARGET_PRODUCT, ProductMatch.EXACT_ID_MATCH])
        print(f"[OK] Test 18 passed: Batch evaluation maintained consistent identity decisions")



if __name__ == "__main__":
    unittest.main()
