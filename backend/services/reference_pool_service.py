"""
Reference Pool Curation and Post-Verification Selection Service (Phase 1).

Autonomous post-verification reference curation layer:
  1. Ingests all prefiltered candidates and their CandidateEvaluation results.
  2. Eliminates exact URL / byte duplicates and near-duplicate redundancies.
  3. Performs adaptive, diversity-aware marginal utility selection (maximizing geometric coverage).
  4. Generates a formal EvidenceMatrix tracking viewpoint and technical asset availability.
  5. Preserves full provenance and telemetry for auditability and future Cycle-2 gap analysis.
"""

import math
import hashlib
import logging
from typing import List, Dict, Any, Optional, Set, Tuple
from collections import Counter
from pydantic import BaseModel, Field

import numpy as np

from services.candidate_analyzer_service import (
    CandidateEvaluation,
    ProductMatch,
    CandidateType,
    Viewpoint,
    EvidenceValue
)
from services.variant_policy import (
    VariantEvidence,
    VariantState,
    VariantSource,
    TargetVariantDefinition
)
from services.dinov2_service import DinoV2Engine

logger = logging.getLogger(__name__)


# ============================================================================
# DATA STRUCTURES
# ============================================================================

class EvidenceMatrix(BaseModel):
    """
    Lightweight formal evidence-availability representation for 3D reconstruction.
    Indicates the strength and completeness of retrieved orthogonal viewpoints,
    structural assets, and appearance consistency.
    """
    front_coverage: float = Field(default=0.0, ge=0.0, le=1.0, description="Front elevation evidence strength")
    rear_coverage: float = Field(default=0.0, ge=0.0, le=1.0, description="Rear elevation evidence strength")
    side_coverage: float = Field(default=0.0, ge=0.0, le=1.0, description="Side profile (left/right) evidence strength")
    top_coverage: float = Field(default=0.0, ge=0.0, le=1.0, description="Top-down / plan view evidence strength")
    bottom_coverage: float = Field(default=0.0, ge=0.0, le=1.0, description="Underside / mounting evidence strength")
    isometric_coverage: float = Field(default=0.0, ge=0.0, le=1.0, description="Perspective / 3D aspect evidence strength")
    detail_coverage: float = Field(default=0.0, ge=0.0, le=1.0, description="Close-up / component detail evidence strength")
    technical_drawing_present: bool = Field(default=False, description="Whether 2D dimensional drawing/CAD exists")
    dimensions_present: bool = Field(default=False, description="Whether explicit bounding millimeter dimensions exist")
    installation_present: bool = Field(default=False, description="Whether mounting / installation context exists")
    unknown_viewpoint_count: int = Field(default=0, description="Number of accepted candidates with UNKNOWN viewpoint")
    total_evidence_score: float = Field(default=0.0, ge=0.0, le=1.0, description="Aggregated geometric coverage score")
    unresolved_geometric_gaps: List[str] = Field(default_factory=list, description="Missing viewpoints/assets for Cycle-2")

    # Appearance & Variant consistency (Phase 2)
    target_color: Optional[str] = Field(default=None, description="Resolved target color")
    target_variant: Optional[str] = Field(default=None, description="Resolved target model/article variant")
    variant_consistency_score: float = Field(default=1.0, ge=0.0, le=1.0, description="Pool-wide variant consistency score")
    matching_variant_count: int = Field(default=0, description="Count of selected references matching target variant")
    compatible_variant_count: int = Field(default=0, description="Count of selected references with compatible variant")
    conflicting_variant_count: int = Field(default=0, description="Count of selected references with conflicting variant")
    unknown_variant_count: int = Field(default=0, description="Count of selected references with UNKNOWN variant")
    observed_variants: List[str] = Field(default_factory=list, description="Distinct variants or colors observed in pool")
    unresolved_appearance_gaps: List[str] = Field(default_factory=list, description="Appearance gaps for Cycle-2")


class CurationTelemetry(BaseModel):
    """
    Telemetry and audit metrics recorded during the reference pool curation pass.
    """
    total_input_candidates: int = 0
    semantically_valid_candidates: int = 0
    semantically_rejected_candidates: int = 0
    selected_candidates_count: int = 0
    exact_duplicates_suppressed: int = 0
    near_duplicates_suppressed: int = 0
    redundant_views_suppressed: int = 0
    viewpoint_distribution: Dict[str, int] = Field(default_factory=dict)
    evidence_distribution: Dict[str, int] = Field(default_factory=dict)
    selection_reasons: Dict[str, str] = Field(default_factory=dict)
    suppression_reasons: Dict[str, str] = Field(default_factory=dict)


class CuratedReferencePool(BaseModel):
    """
    Final curated reference pool payload delivered to 3D reconstruction and the API.
    """
    selected_references: List[Dict[str, Any]] = Field(default_factory=list)
    suppressed_duplicates: List[Dict[str, Any]] = Field(default_factory=list)
    suppressed_redundant_candidates: List[Dict[str, Any]] = Field(default_factory=list)
    rejected_semantic_candidates: List[Dict[str, Any]] = Field(default_factory=list)
    evidence_matrix: EvidenceMatrix = Field(default_factory=EvidenceMatrix)
    curation_telemetry: CurationTelemetry = Field(default_factory=CurationTelemetry)


# ============================================================================
# REFERENCE POOL CURATION SERVICE
# ============================================================================

class ReferencePoolCurationService:
    """
    Autonomous Post-Verification Reference Pool Curation Layer.
    
    Replaces early pre-verification Top-K truncation with an adaptive, diversity-aware
    marginal utility selector operating over all semantically verified candidates.
    """

    NEAR_DUPLICATE_THRESHOLD: float = 0.96
    VISUAL_REDUNDANCY_THRESHOLD: float = 0.90

    # Configurable Policy Defaults for Variant-Aware Marginal Utility
    VARIANT_MATCH_UTILITY: float = 0.25
    VARIANT_COMPATIBLE_UTILITY: float = 0.15
    VARIANT_UNKNOWN_UTILITY: float = 0.00
    VARIANT_CONFLICT_PENALTY: float = -0.60
    GEOMETRIC_FALLBACK_CONFLICT_PENALTY: float = -0.20

    @classmethod
    def curate_pool(
        cls,
        candidates: List[Dict[str, Any]],
        evaluations: List[CandidateEvaluation],
        max_candidates: int = 12,
        seed_vector: Optional[np.ndarray] = None,
        excluded_candidate_ids: Optional[Set[str]] = None,
        target_variant: Optional[TargetVariantDefinition] = None
    ) -> CuratedReferencePool:
        """
        Executes reference pool curation:
          1. Consolidates candidate dicts with CandidateEvaluations.
          2. Deduplicates exact URLs and identical byte hashes.
          3. Separates semantically valid candidates from rejected candidates.
          4. Performs diversity-aware and variant-aware marginal utility selection up to max_candidates.
          5. Computes EvidenceMatrix (geometry + appearance) and telemetry metadata.
        """
        if excluded_candidate_ids is None:
            excluded_candidate_ids = set()

        telemetry = CurationTelemetry(total_input_candidates=len(candidates))
        suppressed_duplicates: List[Dict[str, Any]] = []
        suppressed_redundant: List[Dict[str, Any]] = []
        rejected_semantic: List[Dict[str, Any]] = []

        # --------------------------------------------------------------------
        # Step 1: Pair candidates with their semantic evaluations
        # --------------------------------------------------------------------
        paired_items: List[Tuple[Dict[str, Any], CandidateEvaluation]] = []
        seen_urls: Set[str] = set()
        seen_byte_hashes: Set[str] = set()

        for c, eval_obj in zip(candidates, evaluations):
            cand_id = str(c.get("id") or "")
            if cand_id in excluded_candidate_ids:
                continue

            # Exact URL duplicate suppression
            norm_url = str(c.get("url") or "").strip().lower()
            if norm_url and norm_url in seen_urls:
                telemetry.exact_duplicates_suppressed += 1
                telemetry.suppression_reasons[cand_id] = "EXACT_DUPLICATE_URL"
                c_copy = dict(c)
                c_copy["suppression_reason"] = "EXACT_DUPLICATE_URL"
                suppressed_duplicates.append(c_copy)
                continue
            if norm_url:
                seen_urls.add(norm_url)

            # Exact byte hash duplicate suppression (if raw_bytes available)
            raw_b = c.get("raw_bytes")
            if raw_b:
                b_hash = hashlib.md5(raw_b).hexdigest()
                if b_hash in seen_byte_hashes:
                    telemetry.exact_duplicates_suppressed += 1
                    telemetry.suppression_reasons[cand_id] = "EXACT_DUPLICATE_BYTES"
                    c_copy = dict(c)
                    c_copy["suppression_reason"] = "EXACT_DUPLICATE_BYTES"
                    suppressed_duplicates.append(c_copy)
                    continue
                seen_byte_hashes.add(b_hash)

            paired_items.append((c, eval_obj))

        # --------------------------------------------------------------------
        # Step 2: Separate semantically valid from semantically invalid
        # --------------------------------------------------------------------
        eligible_items: List[Tuple[Dict[str, Any], CandidateEvaluation]] = []

        for c, eval_obj in paired_items:
            cand_id = str(c.get("id") or "")
            # Reconstruction evidence flag is the primary semantic validity gate
            if eval_obj.reconstruction_evidence:
                eligible_items.append((c, eval_obj))
                telemetry.semantically_valid_candidates += 1
            else:
                telemetry.semantically_rejected_candidates += 1
                telemetry.suppression_reasons[cand_id] = f"SEMANTIC_REJECTED_{eval_obj.product_match.value}"
                c_copy = dict(c)
                c_copy["rejection_reason"] = eval_obj.rejection_reason or eval_obj.explanation
                rejected_semantic.append(c_copy)

        # --------------------------------------------------------------------
        # Step 3: Adaptive Diversity-Aware Marginal Utility Selection
        # --------------------------------------------------------------------
        selected_pairs: List[Tuple[Dict[str, Any], CandidateEvaluation]] = []
        selected_vectors: List[np.ndarray] = []
        covered_viewpoints: Counter = Counter()

        # If eligible items <= max_candidates, accept all without artificial truncation
        if len(eligible_items) <= max_candidates:
            for c, eval_obj in eligible_items:
                cand_id = str(c.get("id") or "")
                selected_pairs.append((c, eval_obj))
                vp = eval_obj.verified_viewpoint
                _, reason = cls._compute_marginal_utility(
                    candidate=c,
                    eval_obj=eval_obj,
                    selected_vectors=selected_vectors,
                    covered_viewpoints=covered_viewpoints,
                    seed_vector=seed_vector,
                    target_variant=target_variant
                )
                telemetry.selection_reasons[cand_id] = reason
                covered_viewpoints[vp] += 1
                if c.get("cls_vector") is not None:
                    selected_vectors.append(c["cls_vector"])

        else:
            # Iterative greedy marginal utility selection
            remaining_candidates = list(eligible_items)

            while len(selected_pairs) < max_candidates and remaining_candidates:
                best_score = -float("inf")
                best_idx = -1
                best_reason = ""

                for idx, (c, eval_obj) in enumerate(remaining_candidates):
                    score, reason = cls._compute_marginal_utility(
                        candidate=c,
                        eval_obj=eval_obj,
                        selected_vectors=selected_vectors,
                        covered_viewpoints=covered_viewpoints,
                        seed_vector=seed_vector,
                        target_variant=target_variant
                    )
                    if score > best_score:
                        best_score = score
                        best_idx = idx
                        best_reason = reason

                if best_idx >= 0:
                    chosen_c, chosen_eval = remaining_candidates.pop(best_idx)
                    chosen_id = str(chosen_c.get("id") or "")
                    selected_pairs.append((chosen_c, chosen_eval))
                    vp = chosen_eval.verified_viewpoint
                    covered_viewpoints[vp] += 1
                    telemetry.selection_reasons[chosen_id] = best_reason
                    if chosen_c.get("cls_vector") is not None:
                        selected_vectors.append(chosen_c["cls_vector"])
                else:
                    break

            # Any remaining unselected eligible candidates are logged as redundant/deprioritized
            for c, eval_obj in remaining_candidates:
                cand_id = str(c.get("id") or "")
                telemetry.redundant_views_suppressed += 1
                telemetry.suppression_reasons[cand_id] = f"REDUNDANT_VIEW_{eval_obj.verified_viewpoint.value}"
                c_copy = dict(c)
                c_copy["suppression_reason"] = f"REDUNDANT_VIEW_{eval_obj.verified_viewpoint.value}"
                suppressed_redundant.append(c_copy)

        telemetry.selected_candidates_count = len(selected_pairs)

        # Record viewpoint and evidence distributions
        for _, eval_obj in selected_pairs:
            vp_name = eval_obj.verified_viewpoint.value
            telemetry.viewpoint_distribution[vp_name] = telemetry.viewpoint_distribution.get(vp_name, 0) + 1
            ev_name = eval_obj.evidence_value.value
            telemetry.evidence_distribution[ev_name] = telemetry.evidence_distribution.get(ev_name, 0) + 1

        # --------------------------------------------------------------------
        # Step 4: Synthesize Evidence Matrix (Geometry + Appearance)
        # --------------------------------------------------------------------
        evidence_matrix = cls._synthesize_evidence_matrix(selected_pairs, target_variant=target_variant)

        # --------------------------------------------------------------------
        # Step 5: Construct Final Selected Reference Cards
        # --------------------------------------------------------------------
        selected_references: List[Dict[str, Any]] = []
        for c, eval_obj in selected_pairs:
            cand_id = str(c.get("id") or "")
            card = dict(c)
            card["selected"] = True
            card["selection_reason"] = telemetry.selection_reasons.get(cand_id, "SELECTED")
            card["product_match"] = eval_obj.product_match.value
            card["product_match_confidence"] = eval_obj.product_match_confidence
            card["candidate_type"] = eval_obj.candidate_type.value
            card["verified_viewpoint"] = eval_obj.verified_viewpoint.value
            card["viewpoint_confidence"] = eval_obj.viewpoint_confidence
            card["visible_attributes"] = eval_obj.visible_attributes
            card["reconstruction_evidence"] = True
            card["evidence_value"] = eval_obj.evidence_value.value
            card["rejection_reason"] = None
            card["explanation"] = eval_obj.explanation
            card["analyzer_source"] = eval_obj.analyzer_source

            # Variant and appearance fields (Phase 2)
            var_ev = eval_obj.variant_evidence
            card["variant_state"] = var_ev.evidence_state.value
            card["variant_color"] = var_ev.color_raw
            card["variant_finish"] = var_ev.finish_raw
            card["variant_material"] = var_ev.material_raw
            card["variant_model"] = var_ev.model_variant
            card["variant_configuration"] = var_ev.configuration
            card["variant_confidence"] = var_ev.confidence
            card["variant_source"] = var_ev.evidence_source.value
            card["variant_evidence"] = var_ev.model_dump()

            selected_references.append(card)

        return CuratedReferencePool(
            selected_references=selected_references,
            suppressed_duplicates=suppressed_duplicates,
            suppressed_redundant_candidates=suppressed_redundant,
            rejected_semantic_candidates=rejected_semantic,
            evidence_matrix=evidence_matrix,
            curation_telemetry=telemetry
        )

    @classmethod
    def _compute_marginal_utility(
        cls,
        candidate: Dict[str, Any],
        eval_obj: CandidateEvaluation,
        selected_vectors: List[np.ndarray],
        covered_viewpoints: Counter,
        seed_vector: Optional[np.ndarray] = None,
        target_variant: Optional[TargetVariantDefinition] = None
    ) -> Tuple[float, str]:
        """
        Calculates the marginal information utility of adding candidate to the currently selected pool.
        
        Balances:
          + Verified identity confidence
          + Need for currently unrepresented or underrepresented viewpoints
          + High reconstruction evidence value (technical drawings, schematics)
          + Variant & appearance consistency (Phase 2)
          + Image quality and priority
          - Visual redundancy / near-duplicate penalty with already selected vectors
        """
        vp = eval_obj.verified_viewpoint
        ev_val = eval_obj.evidence_value
        reasons: List[str] = []

        # 1. Base Identity & Quality Score
        base_score = float(candidate.get("priority", 0.8)) * 0.25
        base_score += float(eval_obj.product_match_confidence) * 0.35

        # 2. Evidence Value Tier
        if ev_val == EvidenceValue.HIGH:
            base_score += 0.30
            reasons.append("HIGH_EVIDENCE")
        elif ev_val == EvidenceValue.MEDIUM:
            base_score += 0.15
        elif ev_val == EvidenceValue.LOW:
            base_score += 0.05

        # 3. Viewpoint Need & Orthogonal Diversity Weighting
        current_vp_count = covered_viewpoints.get(vp, 0)

        if eval_obj.candidate_type == CandidateType.TECHNICAL_DRAWING or vp == Viewpoint.TECHNICAL:
            if current_vp_count == 0:
                base_score += 0.45
                reasons.append("FIRST_TECHNICAL_DRAWING")
            elif current_vp_count == 1:
                base_score += 0.15
            else:
                base_score -= 0.20
        elif vp in [Viewpoint.FRONT, Viewpoint.REAR, Viewpoint.LEFT, Viewpoint.RIGHT, Viewpoint.TOP, Viewpoint.BOTTOM]:
            if current_vp_count == 0:
                base_score += 0.40
                reasons.append(f"FIRST_{vp.value}_VIEW")
            elif current_vp_count == 1:
                base_score += 0.12
                reasons.append(f"SECOND_{vp.value}_VIEW")
            elif current_vp_count == 2:
                base_score -= 0.15
                reasons.append(f"SATURATED_{vp.value}_VIEW")
            else:
                base_score -= 0.35
                reasons.append(f"EXCESS_{vp.value}_VIEW")
        elif vp == Viewpoint.ISOMETRIC:
            if current_vp_count == 0:
                base_score += 0.25
                reasons.append("FIRST_ISOMETRIC_VIEW")
            elif current_vp_count < 2:
                base_score += 0.10
            else:
                base_score -= 0.20
        elif vp == Viewpoint.DETAIL:
            if current_vp_count == 0:
                base_score += 0.25
                reasons.append("FIRST_DETAIL_VIEW")
            else:
                base_score += 0.05
        elif vp == Viewpoint.UNKNOWN:
            # UNKNOWN viewpoints are eligible but don't receive orthogonal bonus
            if current_vp_count < 3:
                base_score += 0.05
                reasons.append("GENERAL_PRODUCT_VIEW")
            else:
                base_score -= 0.10

        # 4. Variant & Appearance Consistency Weighting (Phase 2)
        var_ev = getattr(eval_obj, "variant_evidence", None)
        if var_ev:
            if var_ev.evidence_state == VariantState.MATCH:
                base_score += cls.VARIANT_MATCH_UTILITY
                reasons.append("MATCHING_VARIANT")
            elif var_ev.evidence_state == VariantState.COMPATIBLE:
                base_score += cls.VARIANT_COMPATIBLE_UTILITY
                reasons.append("COMPATIBLE_VARIANT")
            elif var_ev.evidence_state == VariantState.UNKNOWN:
                base_score += cls.VARIANT_UNKNOWN_UTILITY
            elif var_ev.evidence_state == VariantState.CONFLICT:
                # Geometric fallback: If this conflicting variant provides the sole unrepresented
                # critical view (e.g. only rear or technical drawing), apply mild penalty instead of hard discard
                is_sole_critical_view = (current_vp_count == 0 and vp in [Viewpoint.TECHNICAL, Viewpoint.BOTTOM, Viewpoint.REAR])
                if is_sole_critical_view or ev_val == EvidenceValue.HIGH:
                    base_score += cls.GEOMETRIC_FALLBACK_CONFLICT_PENALTY
                    reasons.append("CONFLICT_VARIANT_GEOMETRIC_FALLBACK")
                else:
                    base_score += cls.VARIANT_CONFLICT_PENALTY
                    reasons.append("CONFLICT_VARIANT_PENALTY")

        # 5. Visual Redundancy & Near-Duplicate Penalty via DINO Embeddings
        c_vec = candidate.get("cls_vector")
        if c_vec is not None and selected_vectors:
            max_sim = max(DinoV2Engine.cosine_similarity(c_vec, v) for v in selected_vectors)

            if max_sim >= cls.NEAR_DUPLICATE_THRESHOLD:
                # If highly similar to an existing image, heavily penalize UNLESS it provides distinct evidence value
                if ev_val == EvidenceValue.HIGH or vp == Viewpoint.TECHNICAL:
                    base_score -= 0.10  # Mild penalty because technical content is distinct
                    reasons.append(f"HIGH_SIM_BUT_VALUABLE_{max_sim:.2f}")
                elif current_vp_count >= 1:
                    base_score -= 0.65  # Heavy near-duplicate penalty
                    reasons.append(f"NEAR_DUPLICATE_PENALTY_{max_sim:.2f}")
                else:
                    base_score -= 0.30
                    reasons.append(f"HIGH_SIMILARITY_{max_sim:.2f}")
            elif max_sim >= cls.VISUAL_REDUNDANCY_THRESHOLD:
                if current_vp_count >= 1:
                    base_score -= 0.25 * max_sim
                    reasons.append(f"VISUAL_REDUNDANCY_{max_sim:.2f}")

        selection_reason = ", ".join(reasons) if reasons else f"SCORE_RANKED_{base_score:.2f}"
        return base_score, selection_reason

    @classmethod
    def _synthesize_evidence_matrix(
        cls,
        selected_pairs: List[Tuple[Dict[str, Any], CandidateEvaluation]],
        target_variant: Optional[TargetVariantDefinition] = None
    ) -> EvidenceMatrix:
        """
        Synthesizes the EvidenceMatrix tracking viewpoint coverage, technical asset presence,
        appearance consistency, and unresolved geometric/appearance gaps.
        """
        front_confs: List[float] = []
        rear_confs: List[float] = []
        side_confs: List[float] = []
        top_confs: List[float] = []
        bottom_confs: List[float] = []
        iso_confs: List[float] = []
        detail_confs: List[float] = []
        unknown_count = 0
        has_tech = False
        has_dim = False
        has_install = False

        # Appearance & Variant Tracking
        match_count = 0
        compatible_count = 0
        conflict_count = 0
        unknown_var_count = 0
        observed_variants_set: Set[str] = set()

        for c, eval_obj in selected_pairs:
            vp = eval_obj.verified_viewpoint
            conf = eval_obj.viewpoint_confidence
            ct = eval_obj.candidate_type

            if ct == CandidateType.TECHNICAL_DRAWING or vp == Viewpoint.TECHNICAL:
                has_tech = True
            if any("dimension" in a for a in eval_obj.visible_attributes):
                has_dim = True
            if vp == Viewpoint.INSTALLATION:
                has_install = True

            if vp == Viewpoint.FRONT:
                front_confs.append(conf)
            elif vp == Viewpoint.REAR:
                rear_confs.append(conf)
            elif vp in [Viewpoint.LEFT, Viewpoint.RIGHT]:
                side_confs.append(conf)
            elif vp == Viewpoint.TOP:
                top_confs.append(conf)
            elif vp == Viewpoint.BOTTOM:
                bottom_confs.append(conf)
            elif vp == Viewpoint.ISOMETRIC:
                iso_confs.append(conf)
            elif vp == Viewpoint.DETAIL:
                detail_confs.append(conf)
            elif vp == Viewpoint.UNKNOWN:
                unknown_count += 1

            # Variant metrics
            var_ev = getattr(eval_obj, "variant_evidence", None)
            if var_ev:
                if var_ev.evidence_state == VariantState.MATCH:
                    match_count += 1
                elif var_ev.evidence_state == VariantState.COMPATIBLE:
                    compatible_count += 1
                elif var_ev.evidence_state == VariantState.CONFLICT:
                    conflict_count += 1
                elif var_ev.evidence_state == VariantState.UNKNOWN:
                    unknown_var_count += 1

                if var_ev.color_raw:
                    observed_variants_set.add(var_ev.color_raw)
                if var_ev.model_variant:
                    observed_variants_set.add(var_ev.model_variant)

        def calc_cov(confs: List[float]) -> float:
            if not confs:
                return 0.0
            # Diminishing returns formula: 1 - product of (1 - 0.7 * c)
            inv = 1.0
            for c in confs:
                inv *= (1.0 - 0.75 * min(1.0, max(0.2, c)))
            return round(min(1.0, 1.0 - inv), 3)

        front_cov = calc_cov(front_confs)
        rear_cov = calc_cov(rear_confs)
        side_cov = calc_cov(side_confs)
        top_cov = calc_cov(top_confs)
        bottom_cov = calc_cov(bottom_confs)
        iso_cov = calc_cov(iso_confs)
        detail_cov = calc_cov(detail_confs)

        # Unresolved geometric gaps manifest
        geometric_gaps: List[str] = []
        if front_cov < 0.5:
            geometric_gaps.append("MISSING_OR_WEAK_FRONT_VIEW")
        if side_cov < 0.5:
            geometric_gaps.append("MISSING_OR_WEAK_SIDE_VIEW")
        if rear_cov < 0.5:
            geometric_gaps.append("MISSING_OR_WEAK_REAR_VIEW")
        if top_cov < 0.4:
            geometric_gaps.append("MISSING_TOP_VIEW")
        if bottom_cov < 0.4:
            geometric_gaps.append("MISSING_BOTTOM_VIEW")
        if not has_tech:
            geometric_gaps.append("MISSING_TECHNICAL_DRAWING")

        # Total weighted geometric evidence score
        weights = [
            (front_cov, 0.20),
            (side_cov, 0.20),
            (rear_cov, 0.15),
            (top_cov, 0.10),
            (bottom_cov, 0.10),
            (iso_cov, 0.10),
            (1.0 if has_tech else 0.0, 0.10),
            (1.0 if has_dim else 0.0, 0.05)
        ]
        total_score = round(sum(val * w for val, w in weights), 3)

        # Appearance & Variant Score & Gaps
        total_selected = len(selected_pairs)
        if total_selected > 0 and target_variant and (target_variant.is_color_specified or target_variant.is_variant_specified):
            var_score = round((match_count * 1.0 + compatible_count * 0.75 + unknown_var_count * 0.40) / total_selected, 3)
        else:
            var_score = 1.0

        appearance_gaps: List[str] = []
        if not target_variant or not target_variant.is_color_specified:
            appearance_gaps.append("TARGET_COLOR_UNCONFIRMED")
        if not target_variant or not target_variant.target_material:
            appearance_gaps.append("FINISH_MATERIAL_UNKNOWN")
        if conflict_count > 0:
            appearance_gaps.append("VARIANT_CONFLICT_PRESENT")
        if len(observed_variants_set) > 2 and target_variant and target_variant.is_color_specified:
            appearance_gaps.append("MIXED_VARIANTS_OBSERVED")

        t_col = target_variant.target_color_raw if target_variant else None
        t_var = target_variant.target_model_variant if target_variant else None

        return EvidenceMatrix(
            front_coverage=front_cov,
            rear_coverage=rear_cov,
            side_coverage=side_cov,
            top_coverage=top_cov,
            bottom_coverage=bottom_cov,
            isometric_coverage=iso_cov,
            detail_coverage=detail_cov,
            technical_drawing_present=has_tech,
            dimensions_present=has_dim,
            installation_present=has_install,
            unknown_viewpoint_count=unknown_count,
            total_evidence_score=total_score,
            unresolved_geometric_gaps=geometric_gaps,
            target_color=t_col,
            target_variant=t_var,
            variant_consistency_score=var_score,
            matching_variant_count=match_count,
            compatible_variant_count=compatible_count,
            conflicting_variant_count=conflict_count,
            unknown_variant_count=unknown_var_count,
            observed_variants=sorted(list(observed_variants_set)),
            unresolved_appearance_gaps=appearance_gaps
        )
