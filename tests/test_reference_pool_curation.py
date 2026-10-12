"""
Unit and regression tests for Phase 1: Reference Pool Curation & Diversity Selection Layer.

Tests:
  1. Early Top-K Bug: Invalid candidates do not consume pool capacity; all candidates reach semantic verification.
  2. Front Redundancy: Orthogonal views (rear/bottom) survive even if front views have high raw scores.
  3. Near Duplicate: Redundant duplicates are deprioritized/suppressed while distinct viewpoints survive.
  4. Similar But Valuable: High similarity does not suppress a candidate if it provides distinct evidence (e.g. technical drawing).
  5. UNKNOWN Viewpoint: Valid candidate with UNKNOWN viewpoint remains eligible.
  6. Sparse Product: Rare products with few candidates (e.g. 3) gracefully keep all valid items without quota failure.
  7. Evidence Matrix: Correctly tracks coverage percentages and geometric gaps.
  8. Downvote / Exclusion: Excluded candidate IDs are filtered and remaining pool is re-curated cleanly.
"""

import os
import sys
import unittest
import numpy as np

backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend"))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from services.candidate_analyzer_service import (
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


class TestReferencePoolCuration(unittest.TestCase):

    def _create_mock_eval(
        self,
        candidate_id="cand_test",
        image_url="https://example.com/test.jpg",
        match=ProductMatch.TARGET_PRODUCT,
        conf=0.95,
        cand_type=CandidateType.TARGET_PRODUCT,
        viewpoint=Viewpoint.FRONT,
        vp_conf=0.85,
        evidence=True,
        ev_val=EvidenceValue.MEDIUM,
        attributes=None
    ) -> CandidateEvaluation:
        return CandidateEvaluation(
            candidate_id=candidate_id,
            image_url=image_url,
            product_match=match,
            product_match_confidence=conf,
            candidate_type=cand_type,
            verified_viewpoint=viewpoint,
            viewpoint_confidence=vp_conf,
            visible_attributes=attributes or ["silhouette: visible"],
            reconstruction_evidence=evidence,
            evidence_value=ev_val,
            explanation="Mock test evaluation"
        )

    # ------------------------------------------------------------------------
    # TEST 1: Early Top-K Bug Prevention
    # ------------------------------------------------------------------------
    def test_01_early_topk_bug_prevention(self):
        """
        Verify:
        - 12 candidates input: 5 are semantically invalid (e.g. competitors/unrelated), 7 are valid.
        - With max_candidates=7, all 7 valid candidates are selected.
        - Invalid candidates do NOT consume final pool capacity.
        """
        candidates = []
        evaluations = []

        # 5 invalid candidates with high initial raw scores
        for i in range(5):
            candidates.append({
                "id": f"inv_{i}",
                "url": f"https://example.com/invalid_{i}.jpg",
                "score": 0.98,
                "priority": 1.0,
                "title": f"Competitor Product {i}"
            })
            evaluations.append(self._create_mock_eval(
                match=ProductMatch.DIFFERENT_PRODUCT,
                conf=0.95,
                cand_type=CandidateType.DIFFERENT_PRODUCT,
                evidence=False,
                ev_val=EvidenceValue.NONE
            ))

        # 7 valid candidates with moderate raw scores
        for i in range(7):
            candidates.append({
                "id": f"val_{i}",
                "url": f"https://example.com/valid_{i}.jpg",
                "score": 0.85,
                "priority": 0.8,
                "title": f"Target Product View {i}"
            })
            evaluations.append(self._create_mock_eval(
                match=ProductMatch.TARGET_PRODUCT,
                conf=0.90,
                cand_type=CandidateType.TARGET_PRODUCT,
                viewpoint=Viewpoint.FRONT if i < 4 else Viewpoint.REAR,
                evidence=True,
                ev_val=EvidenceValue.MEDIUM
            ))

        curated = ReferencePoolCurationService.curate_pool(
            candidates=candidates,
            evaluations=evaluations,
            max_candidates=7
        )

        selected_ids = {r["id"] for r in curated.selected_references}
        self.assertEqual(len(selected_ids), 7, "All 7 valid candidates must be selected")
        for i in range(7):
            self.assertIn(f"val_{i}", selected_ids, f"Valid candidate val_{i} must be selected")
        for i in range(5):
            self.assertNotIn(f"inv_{i}", selected_ids, f"Invalid candidate inv_{i} must not be selected")

        self.assertEqual(curated.curation_telemetry.semantically_rejected_candidates, 5)
        self.assertEqual(curated.curation_telemetry.semantically_valid_candidates, 7)

    # ------------------------------------------------------------------------
    # TEST 2: Front Redundancy & Orthogonal View Preservation
    # ------------------------------------------------------------------------
    def test_02_front_redundancy_and_orthogonal_preservation(self):
        """
        Input: 8 valid front candidates with high raw scores (0.95),
               1 valid rear candidate (score 0.80),
               1 valid bottom candidate (score 0.78).
        Target pool size: 4.
        Verify: The rear and bottom candidates are selected over redundant front candidates.
        """
        candidates = []
        evaluations = []

        # 8 Front views
        for i in range(8):
            candidates.append({
                "id": f"front_{i}",
                "url": f"https://example.com/front_{i}.jpg",
                "score": 0.95,
                "priority": 0.95
            })
            evaluations.append(self._create_mock_eval(
                viewpoint=Viewpoint.FRONT,
                ev_val=EvidenceValue.MEDIUM
            ))

        # 1 Rear view (lower score)
        candidates.append({
            "id": "rear_0",
            "url": "https://example.com/rear_0.jpg",
            "score": 0.80,
            "priority": 0.80
        })
        evaluations.append(self._create_mock_eval(
            viewpoint=Viewpoint.REAR,
            ev_val=EvidenceValue.MEDIUM
        ))

        # 1 Bottom view (lower score)
        candidates.append({
            "id": "bottom_0",
            "url": "https://example.com/bottom_0.jpg",
            "score": 0.78,
            "priority": 0.78
        })
        evaluations.append(self._create_mock_eval(
            viewpoint=Viewpoint.BOTTOM,
            ev_val=EvidenceValue.HIGH
        ))

        curated = ReferencePoolCurationService.curate_pool(
            candidates=candidates,
            evaluations=evaluations,
            max_candidates=4
        )

        selected_ids = {r["id"] for r in curated.selected_references}
        self.assertEqual(len(selected_ids), 4)
        self.assertIn("rear_0", selected_ids, "Rear view must be selected despite lower raw score")
        self.assertIn("bottom_0", selected_ids, "Bottom view must be selected despite lower raw score")

    # ------------------------------------------------------------------------
    # TEST 3: Near Duplicate Suppression
    # ------------------------------------------------------------------------
    def test_03_near_duplicate_suppression(self):
        """
        Input: Two highly similar front views (cosine sim = 0.99),
               One orthogonal side view (cosine sim = 0.50).
        Verify: Only one front view is selected, side view is selected.
        """
        v_front1 = np.ones(384) / np.linalg.norm(np.ones(384))
        # v_front2 is almost identical (sim > 0.99)
        v_front2 = (np.ones(384) + 0.005 * np.random.randn(384))
        v_front2 /= np.linalg.norm(v_front2)
        # v_side is orthogonal
        v_side = np.zeros(384)
        v_side[0] = 1.0

        candidates = [
            {"id": "front_1", "url": "https://example.com/f1.jpg", "score": 0.90, "cls_vector": v_front1},
            {"id": "front_2", "url": "https://example.com/f2.jpg", "score": 0.89, "cls_vector": v_front2},
            {"id": "side_1", "url": "https://example.com/s1.jpg", "score": 0.82, "cls_vector": v_side}
        ]
        evaluations = [
            self._create_mock_eval(viewpoint=Viewpoint.FRONT, ev_val=EvidenceValue.MEDIUM),
            self._create_mock_eval(viewpoint=Viewpoint.FRONT, ev_val=EvidenceValue.MEDIUM),
            self._create_mock_eval(viewpoint=Viewpoint.LEFT, ev_val=EvidenceValue.MEDIUM)
        ]

        curated = ReferencePoolCurationService.curate_pool(
            candidates=candidates,
            evaluations=evaluations,
            max_candidates=2
        )

        selected_ids = {r["id"] for r in curated.selected_references}
        self.assertEqual(len(selected_ids), 2)
        self.assertIn("side_1", selected_ids, "Orthogonal side view must be selected")
        # Exactly one of front_1 or front_2 selected
        self.assertTrue(("front_1" in selected_ids) ^ ("front_2" in selected_ids),
                        "Only one near-duplicate front view should be selected")

    # ------------------------------------------------------------------------
    # TEST 4: Similar But Distinct Reconstruction Evidence Preserved
    # ------------------------------------------------------------------------
    def test_04_similar_but_valuable_evidence_preserved(self):
        """
        Input: Candidate 1 is a photographic product view.
               Candidate 2 has high visual similarity to Candidate 1 (sim = 0.97),
               but is tagged as CandidateType.TECHNICAL_DRAWING / Viewpoint.TECHNICAL with HIGH evidence.
        Verify: Candidate 2 is NOT suppressed because its structural evidence value is distinct.
        """
        v1 = np.ones(384) / np.linalg.norm(np.ones(384))
        v2 = (np.ones(384) + 0.005 * np.random.randn(384))
        v2 /= np.linalg.norm(v2)

        candidates = [
            {"id": "photo_1", "url": "https://example.com/photo.jpg", "score": 0.90, "cls_vector": v1},
            {"id": "tech_2", "url": "https://example.com/tech_drawing.jpg", "score": 0.88, "cls_vector": v2}
        ]
        evaluations = [
            self._create_mock_eval(cand_type=CandidateType.TARGET_PRODUCT, viewpoint=Viewpoint.FRONT, ev_val=EvidenceValue.MEDIUM),
            self._create_mock_eval(cand_type=CandidateType.TECHNICAL_DRAWING, viewpoint=Viewpoint.TECHNICAL, ev_val=EvidenceValue.HIGH, attributes=["dimensions: 500x400 mm"])
        ]

        curated = ReferencePoolCurationService.curate_pool(
            candidates=candidates,
            evaluations=evaluations,
            max_candidates=2
        )

        selected_ids = {r["id"] for r in curated.selected_references}
        self.assertIn("photo_1", selected_ids)
        self.assertIn("tech_2", selected_ids, "Technical drawing must be preserved despite vector similarity")
        self.assertTrue(curated.evidence_matrix.technical_drawing_present)

    # ------------------------------------------------------------------------
    # TEST 5: UNKNOWN Viewpoint Eligibility
    # ------------------------------------------------------------------------
    def test_05_unknown_viewpoint_eligibility(self):
        """
        Input: Valid target product candidate where candidate-owned metadata has no viewpoint tags (Viewpoint.UNKNOWN).
        Verify: It remains eligible and is selected into the reference pool.
        """
        candidates = [
            {"id": "unknown_vp_1", "url": "https://example.com/product_unlabeled.jpg", "score": 0.88, "priority": 0.9}
        ]
        evaluations = [
            self._create_mock_eval(
                match=ProductMatch.TARGET_PRODUCT,
                conf=0.92,
                viewpoint=Viewpoint.UNKNOWN,
                vp_conf=0.0,
                evidence=True,
                ev_val=EvidenceValue.MEDIUM
            )
        ]

        curated = ReferencePoolCurationService.curate_pool(
            candidates=candidates,
            evaluations=evaluations,
            max_candidates=5
        )

        selected_ids = {r["id"] for r in curated.selected_references}
        self.assertIn("unknown_vp_1", selected_ids, "Candidate with UNKNOWN viewpoint must remain eligible")
        self.assertEqual(curated.evidence_matrix.unknown_viewpoint_count, 1)

    # ------------------------------------------------------------------------
    # TEST 6: Sparse Product Pool Handling (No Quota Failures)
    # ------------------------------------------------------------------------
    def test_06_sparse_product_pool_graceful_acceptance(self):
        """
        Input: Only 3 valid candidates total for a niche product.
        Verify: All 3 candidates are selected without raising errors or failing artificial quotas.
        """
        candidates = [
            {"id": "niche_1", "url": "https://example.com/n1.jpg", "score": 0.85},
            {"id": "niche_2", "url": "https://example.com/n2.jpg", "score": 0.82},
            {"id": "niche_3", "url": "https://example.com/n3.jpg", "score": 0.80}
        ]
        evaluations = [
            self._create_mock_eval(viewpoint=Viewpoint.FRONT),
            self._create_mock_eval(viewpoint=Viewpoint.ISOMETRIC),
            self._create_mock_eval(viewpoint=Viewpoint.UNKNOWN)
        ]

        curated = ReferencePoolCurationService.curate_pool(
            candidates=candidates,
            evaluations=evaluations,
            max_candidates=12
        )

        self.assertEqual(len(curated.selected_references), 3, "All 3 valid items should be accepted for sparse product")
        self.assertEqual(curated.curation_telemetry.selected_candidates_count, 3)

    # ------------------------------------------------------------------------
    # TEST 7: Evidence Matrix Synthesis & Gap Detection
    # ------------------------------------------------------------------------
    def test_07_evidence_matrix_synthesis(self):
        """
        Input: References with Front and Side viewpoints, but missing Rear and Bottom.
        Verify: EvidenceMatrix accurately reflects coverage and lists missing orthogonal gaps.
        """
        candidates = [
            {"id": "c_front", "url": "https://example.com/f.jpg", "score": 0.90},
            {"id": "c_side", "url": "https://example.com/s.jpg", "score": 0.88}
        ]
        evaluations = [
            self._create_mock_eval(viewpoint=Viewpoint.FRONT, vp_conf=0.85),
            self._create_mock_eval(viewpoint=Viewpoint.LEFT, vp_conf=0.85)
        ]

        curated = ReferencePoolCurationService.curate_pool(
            candidates=candidates,
            evaluations=evaluations,
            max_candidates=10
        )

        matrix = curated.evidence_matrix
        self.assertGreater(matrix.front_coverage, 0.5)
        self.assertGreater(matrix.side_coverage, 0.5)
        self.assertEqual(matrix.rear_coverage, 0.0)
        self.assertEqual(matrix.bottom_coverage, 0.0)
        self.assertIn("MISSING_OR_WEAK_REAR_VIEW", matrix.unresolved_geometric_gaps)
        self.assertIn("MISSING_BOTTOM_VIEW", matrix.unresolved_geometric_gaps)

    # ------------------------------------------------------------------------
    # TEST 8: Downvote / Exclusion Compatibility
    # ------------------------------------------------------------------------
    def test_08_exclusion_compatibility(self):
        """
        Verify: Passing excluded_candidate_ids skips those candidates and re-curates cleanly.
        """
        candidates = [
            {"id": "c_1", "url": "https://example.com/1.jpg", "score": 0.95},
            {"id": "c_2", "url": "https://example.com/2.jpg", "score": 0.90},
            {"id": "c_3", "url": "https://example.com/3.jpg", "score": 0.85}
        ]
        evaluations = [
            self._create_mock_eval(viewpoint=Viewpoint.FRONT),
            self._create_mock_eval(viewpoint=Viewpoint.FRONT),
            self._create_mock_eval(viewpoint=Viewpoint.REAR)
        ]

        # Exclude c_1 (simulating a downvote)
        curated = ReferencePoolCurationService.curate_pool(
            candidates=candidates,
            evaluations=evaluations,
            max_candidates=2,
            excluded_candidate_ids={"c_1"}
        )

        selected_ids = {r["id"] for r in curated.selected_references}
        self.assertNotIn("c_1", selected_ids, "Excluded candidate c_1 must not be selected")
        self.assertIn("c_2", selected_ids)
        self.assertIn("c_3", selected_ids)


if __name__ == "__main__":
    unittest.main()
