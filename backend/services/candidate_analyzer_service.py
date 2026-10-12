"""
Candidate Semantic & Viewpoint Verification Engine (V2).

This service acts as the semantic validation layer between raw visual representation (DINOv2)
and downstream evidence synthesis / 3D reconstruction.

Core Principles:
1. VISUAL SIMILARITY != PRODUCT IDENTITY. High DINOv2 cosine similarity does NOT prove exact identity.
   Similarly, low cosine similarity (e.g. underside photo vs front photo) does NOT mean different product.
2. Exact product identity requires multi-signal corroboration (article numbers, model codes, official
   source domains, verified query lineage, title/alt semantics, and geometrical compatibility).
3. Distinguish exact target product from:
   - Different product of the same brand (e.g., Hansgrohe S51 vs C51; Article 43229000 vs 43218000)
   - Different brand of the same category (e.g., Blanco, Franke, Kohler)
   - Accessories / Attachments (faucets, cutting boards, soap dispensers)
   - Spare parts / Exploded diagrams
   - Technical & Dimensional drawings
   - Manuals / Packaging
   - Generic or irrelevant items
4. Classify exact viewpoints without forcing ambiguous images (FRONT, REAR, LEFT, RIGHT, TOP,
   BOTTOM, ISOMETRIC, DETAIL, INSTALLATION, TECHNICAL, INTERNAL, UNKNOWN).
5. Extract visible attributes without fabricating unobserved geometry.
6. Assess reconstruction evidence value (HIGH, MEDIUM, LOW, NONE) and explain every decision.
"""

import os
import re
import math
import logging
from enum import Enum
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple, Set, Union
from pydantic import BaseModel, Field

from services.identifier_policy import (
    ProductIdentity,
    CanonicalProductIdentity,
    normalize_product_identity,
    is_safe_manufacturer_identifier,
    is_exact_identifier_match,
    extract_primary_category,
    detect_category_conflict
)
from services.variant_policy import (
    VariantEvidence,
    VariantState,
    VariantSource,
    TargetVariantDefinition,
    resolve_target_variant,
    extract_candidate_variant_evidence
)

logger = logging.getLogger(__name__)


# ============================================================================
# STRUCTURED ENUMS & MODELS
# ============================================================================

class ProductMatch(str, Enum):
    EXACT_ID_MATCH = "EXACT_ID_MATCH"
    TARGET_PRODUCT = "TARGET_PRODUCT"
    DIFFERENT_PRODUCT = "DIFFERENT_PRODUCT"
    UNCERTAIN = "UNCERTAIN"


class CandidateType(str, Enum):
    TARGET_PRODUCT = "TARGET_PRODUCT"
    DIFFERENT_PRODUCT = "DIFFERENT_PRODUCT"
    ACCESSORY = "ACCESSORY"
    SPARE_PART = "SPARE_PART"
    PACKAGING = "PACKAGING"
    TECHNICAL_DRAWING = "TECHNICAL_DRAWING"
    MANUAL_DOCUMENT = "MANUAL_DOCUMENT"
    IRRELEVANT = "IRRELEVANT"
    UNCERTAIN = "UNCERTAIN"


class Viewpoint(str, Enum):
    FRONT = "FRONT"
    REAR = "REAR"
    LEFT = "LEFT"
    RIGHT = "RIGHT"
    TOP = "TOP"
    BOTTOM = "BOTTOM"
    ISOMETRIC = "ISOMETRIC"
    DETAIL = "DETAIL"
    INSTALLATION = "INSTALLATION"
    TECHNICAL = "TECHNICAL"
    INTERNAL = "INTERNAL"
    UNKNOWN = "UNKNOWN"


class EvidenceValue(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    NONE = "NONE"


class CandidateEvaluation(BaseModel):
    """
    Structured semantic & viewpoint verification result for a single candidate image.
    Maintains full retrieval provenance and explicit auditability.
    """
    candidate_id: str
    image_url: str

    # Identity verification
    product_match: ProductMatch
    product_match_confidence: float = Field(ge=0.0, le=1.0)
    candidate_type: CandidateType
    evidence_sources: List[str] = Field(default_factory=list)
    match_reasons: List[str] = Field(default_factory=list)
    exact_id_match: bool = False
    category_compatible: bool = True

    # Viewpoint verification
    requested_viewpoint: str = "UNKNOWN"
    verified_viewpoint: Viewpoint = Viewpoint.UNKNOWN
    viewpoint_confidence: float = Field(ge=0.0, le=1.0)
    verified_viewpoint_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    verified_viewpoint_source: str = "none"

    # Variant & appearance consistency (Phase 2)
    variant_evidence: VariantEvidence = Field(default_factory=VariantEvidence)

    # Geometry & attribute extraction
    visible_attributes: List[str] = Field(default_factory=list)
    reconstruction_evidence: bool = False
    evidence_value: EvidenceValue = EvidenceValue.NONE

    # Audit & explanations
    rejection_reason: Optional[str] = None
    explanation: str
    analyzer_source: str = "multi_signal_rule_engine"

    # Preserved retrieval context (Stored for provenance ONLY - NEVER used as candidate evidence)
    retrieval_context: Dict[str, Any] = Field(default_factory=dict)
    source_page_url: str = ""
    source_domain: str = ""
    query: str = ""
    query_family: str = ""
    query_priority: float = 0.0
    title: str = ""
    snippet: str = ""
    source_engine: str = ""
    download_status: str = "success"
    image_dimensions: Tuple[int, int] = (0, 0)
    prefilter_status: str = "accepted"
    dino_similarity: Optional[float] = None
    dino_status: str = "evaluated"


# ============================================================================
# MULTI-SIGNAL ANALYSIS LOGIC
# ============================================================================

# Negative/competing brand list for sanitizing brand isolation
COMPETING_BRANDS = {
    "sanitary": ["blanco", "franke", "kohler", "grohe", "villeroy", "duravit", "roca", "schock", "alveus", "teka", "ikea"],
    "industrial": ["geabritec", "kelvion", "swep", "danfoss", "tranter", "api heat transfer"],
    "electronics": ["samsung", "sony", "huawei", "xiaomi", "oppo", "optoma", "epson", "benq", "nec", "barco"],
    "footwear": ["adidas", "puma", "reebok", "new balance", "asics", "under armour", "brooks"]
}

# Viewpoint vocabulary dictionaries (multilingual support: EN, DE, FR)
VIEWPOINT_KEYWORDS = {
    Viewpoint.FRONT: ["front", "vorderansicht", "frontansicht", "face", "straight on", "facade", "0 deg", "0°", "front view", "front profile", "front elevation"],
    Viewpoint.REAR: ["rear", "ruckansicht", "rueckansicht", "backside", "rear view", "back view", "180 deg", "180°", "rear panel", "rear elevation"],
    Viewpoint.TOP: ["top view", "top-view", "draufsicht", "bird eye", "bird's eye", "overhead", "plan view", "from above", "top surface", "top profile", "top elevation"],
    Viewpoint.BOTTOM: ["unteransicht", "underside", "bottom view", "bottom-view", "underneath", "underbody", "bottom surface", "bottom elevation"],
    Viewpoint.LEFT: ["left view", "left-view", "left side", "left profile", "side left", "links", "270 deg", "270°", "side view", "side profile"],
    Viewpoint.RIGHT: ["right view", "right-view", "right side", "right profile", "side right", "rechts", "90 deg", "90°"],
    Viewpoint.ISOMETRIC: ["isometric", "isometrisch", "perspective", "perspektive", "3/4 view", "angled", "angle view", "hero view", "three quarter"],
    Viewpoint.DETAIL: ["detail", "close up", "closeup", "nahaufnahme", "macro", "corner view", "closeup view"],
    Viewpoint.INSTALLATION: ["installation", "montage", "einbau", "unterbau", "flachbündig", "flush mount", "undermount", "countertop", "lifestyle view", "installed"],
    Viewpoint.TECHNICAL: ["dimension", "masszeichnung", "maszeichnung", "technical drawing", "blueprint", "schematic", "cad", "zeichnung", "dimensions", "cutout", "ausschnitt"],
    Viewpoint.INTERNAL: ["internal", "innen", "cutaway", "sectional", "schnitt", "exploded", "cross section"]
}

# Candidate type indicators
TYPE_KEYWORDS = {
    CandidateType.ACCESSORY: [
        "accessory", "zubehoer", "zubehör", "faucet", "mixer", "armatur", "soap dispenser", "seifenspender",
        "cutting board", "schneidbrett", "colander", "sieb", "strainer", "remote control", "cable",
        "ear pads", "ear cushions", "headphone stand"
    ],
    CandidateType.TECHNICAL_DRAWING: [
        "dimension", "masszeichnung", "maszeichnung", "blueprint", "technical-data", "schematic", "cad",
        "drawing", "zeichnung", "ausschnittmass", "cutout"
    ],
    CandidateType.SPARE_PART: [
        "sparepart", "spare-part", "spare_part", "ersatzteil", "ersatzteile", "exploded", "part-list",
        "diagram", "piece-detachee", "ricambi"
    ],
    CandidateType.PACKAGING: [
        "box", "carton", "packaging", "verpackung", "karton", "crate", "package"
    ],
    CandidateType.MANUAL_DOCUMENT: [
        "manual", "anleitung", "bedienungsanleitung", "datasheet", "datenblatt", "pdf", "brochure", "catalog"
    ]
}

# Generic words that do NOT establish specific product identity
GENERIC_STOP_TOKENS = {
    "the", "and", "for", "with", "without", "wireless", "noise", "canceling", "cancelling",
    "kitchen", "pro", "series", "classic", "premium", "black", "white", "steel", "stainless",
    "new", "free", "set", "combi", "select", "universal", "standard", "home", "plus",
    "cad", "drawing", "drawings", "dimensions", "schematic", "blueprint", "pdf", "manual",
    "photo", "official", "product", "high", "quality"
}


class CandidateAnalyzerService:
    """
    Evaluates candidate images for exact product identity, candidate type,
    viewpoint angle, visible attributes, variant & appearance consistency,
    and 3D reconstruction value.
    """

    def __init__(self, canonical_identity: Optional[CanonicalProductIdentity] = None):
        self.identity = canonical_identity
        self.target_variant: Optional[TargetVariantDefinition] = (
            resolve_target_variant(canonical_identity) if canonical_identity else None
        )

    @staticmethod
    def _extract_requested_viewpoint(raw_tag: str) -> str:
        """Parses the search query / angle tag into a canonical requested viewpoint string."""
        t_lower = (raw_tag or "").lower()
        if "front" in t_lower or "face" in t_lower:
            return "FRONT"
        if "rear" in t_lower or "back" in t_lower:
            return "REAR"
        if "side" in t_lower or "profile" in t_lower or "left" in t_lower or "right" in t_lower:
            return "SIDE"
        if "top" in t_lower or "overhead" in t_lower:
            return "TOP"
        if "bottom" in t_lower or "under" in t_lower:
            return "BOTTOM"
        if "isometric" in t_lower or "perspective" in t_lower or "angle" in t_lower:
            return "ISOMETRIC"
        if "tech" in t_lower or "draw" in t_lower or "dimension" in t_lower:
            return "TECHNICAL"
        if "detail" in t_lower or "close" in t_lower:
            return "DETAIL"
        if "install" in t_lower or "mount" in t_lower:
            return "INSTALLATION"
        return "UNKNOWN"

    def analyze_candidate(
        self,
        candidate: Dict[str, Any],
        identity: Optional[CanonicalProductIdentity] = None,
        existing_accepted_viewpoints: Optional[Set[Viewpoint]] = None
    ) -> CandidateEvaluation:
        """
        Performs multi-signal semantic and viewpoint analysis on a single candidate.
        Strictly decouples candidate-owned evidence from the search query context.
        """
        active_identity = identity or self.identity
        target_variant = (
            resolve_target_variant(active_identity) if active_identity else self.target_variant
        )
        if existing_accepted_viewpoints is None:
            existing_accepted_viewpoints = set()

        cand_id = str(candidate.get("id") or candidate.get("candidate_id") or "cand-0")
        img_url = candidate.get("url") or candidate.get("image_url") or ""
        source_url = candidate.get("source_page_url") or candidate.get("source_url") or ""
        domain = candidate.get("source_domain") or ""
        title = candidate.get("title") or ""
        snippet = candidate.get("snippet") or ""
        alt_text = candidate.get("alt") or candidate.get("alt_text") or ""
        dom_meta = candidate.get("dom_metadata") or ""

        # Retrieval Context: Stored for provenance/telemetry ONLY.
        # NEVER used as candidate identity, viewpoint, or variant evidence!
        query = candidate.get("query") or ""
        query_family = candidate.get("query_family") or ""
        query_priority = float(candidate.get("query_priority") or candidate.get("priority") or 0.0)
        target_evidence = candidate.get("target_evidence") or ""
        branch_angle = candidate.get("branch_angle") or candidate.get("angle") or ""
        requested_viewpoint = self._extract_requested_viewpoint(target_evidence or branch_angle or query)

        retrieval_ctx = {
            "query": query,
            "query_family": query_family,
            "query_priority": query_priority,
            "target_evidence": target_evidence,
            "requested_viewpoint": requested_viewpoint
        }

        source_engine = candidate.get("source_engine") or candidate.get("source") or "web"
        dino_sim = candidate.get("score") or candidate.get("dino_similarity")
        img_dims = candidate.get("image_dimensions") or (0, 0)
        if isinstance(img_dims, list) and len(img_dims) == 2:
            img_dims = (int(img_dims[0]), int(img_dims[1]))

        # Candidate-Owned Evidence Text Corpus (STRICTLY EXCLUDES QUERY)
        candidate_evidence_text = f"{title} {snippet} {alt_text} {dom_meta} {source_url} {img_url}".lower()

        # Step 1: Detect candidate type from candidate-owned evidence
        cand_type, type_confidence, type_reason = self._classify_candidate_type(candidate_evidence_text, candidate)

        # Step 2: Determine Product Match from candidate-owned evidence
        prod_match, match_conf, match_reason, evidence_sources, match_reasons = self._verify_product_identity(
            active_identity, candidate_evidence_text, candidate, cand_type
        )

        is_exact_id = ("model_or_article_number" in evidence_sources) or (prod_match == ProductMatch.EXACT_ID_MATCH)
        is_cat_compatible = ("category_conflict" not in match_reasons and prod_match != ProductMatch.DIFFERENT_PRODUCT)

        # Harmonize candidate type with product identity match
        if prod_match == ProductMatch.DIFFERENT_PRODUCT and cand_type in [CandidateType.TARGET_PRODUCT, CandidateType.TECHNICAL_DRAWING]:
            cand_type = CandidateType.DIFFERENT_PRODUCT
        elif prod_match == ProductMatch.UNCERTAIN and cand_type == CandidateType.TARGET_PRODUCT:
            cand_type = CandidateType.UNCERTAIN

        if any(bad in candidate_evidence_text for bad in ["sneaker", "running shoe", "air max", "waffle outsole"]):
            cand_type = CandidateType.IRRELEVANT
            prod_match = ProductMatch.DIFFERENT_PRODUCT
            is_cat_compatible = False

        # Step 3: Classify Viewpoint from candidate-owned evidence (NOT query angle!)
        viewpoint, vp_conf, vp_source = self._classify_viewpoint(candidate_evidence_text, candidate, cand_type)

        # Step 4: Extract Variant & Appearance Evidence (Phase 2)
        variant_ev = extract_candidate_variant_evidence(
            candidate_evidence_text=candidate_evidence_text,
            candidate=candidate,
            target=target_variant
        )

        # Step 5: Extract Visible Attributes
        attributes = self._extract_visible_attributes(
            candidate_evidence_text, candidate, active_identity, viewpoint, cand_type, variant_ev
        )

        # Step 6: Assess 3D Reconstruction Evidence & Value
        is_evidence, evidence_val, value_reason = self._assess_reconstruction_value(
            prod_match=prod_match,
            cand_type=cand_type,
            viewpoint=viewpoint,
            match_conf=match_conf,
            existing_viewpoints=existing_accepted_viewpoints,
            candidate=candidate,
            evidence_sources=evidence_sources
        )

        # Step 7: Formulate Final Explanation & Rejection Reason
        variant_note = ""
        if variant_ev.evidence_state == VariantState.MATCH:
            variant_note = f" (Variant: MATCH [{variant_ev.color_raw or 'target'}])"
        elif variant_ev.evidence_state == VariantState.COMPATIBLE:
            variant_note = f" (Variant: COMPATIBLE [{variant_ev.color_raw or 'compatible'}])"
        elif variant_ev.evidence_state == VariantState.CONFLICT:
            variant_note = f" (Variant: CONFLICT [{variant_ev.conflict_details}])"

        if prod_match in [ProductMatch.TARGET_PRODUCT, ProductMatch.EXACT_ID_MATCH] and is_evidence:
            rejection_reason = None
            explanation = f"{match_reason}. Classified as {cand_type.value} ({viewpoint.value} viewpoint via {vp_source}){variant_note}. {value_reason}."
        elif prod_match in [ProductMatch.TARGET_PRODUCT, ProductMatch.EXACT_ID_MATCH] and not is_evidence:
            rejection_reason = f"Redundant or non-essential view ({evidence_val.value} evidence value)"
            explanation = f"{match_reason}, but rejected from evidence pool: {rejection_reason}{variant_note}."
        elif cand_type in [CandidateType.TECHNICAL_DRAWING, CandidateType.SPARE_PART] and is_evidence:
            rejection_reason = None
            explanation = f"{type_reason}. Classified as {cand_type.value} ({viewpoint.value} via {vp_source}){variant_note}. {value_reason}."
        else:
            rejection_reason = match_reason if prod_match == ProductMatch.DIFFERENT_PRODUCT else (type_reason or "Insufficient candidate metadata to corroborate product identity")
            explanation = f"Rejected candidate: {rejection_reason}."

        return CandidateEvaluation(
            candidate_id=cand_id,
            image_url=img_url,
            product_match=prod_match,
            product_match_confidence=round(match_conf, 3),
            candidate_type=cand_type,
            evidence_sources=evidence_sources,
            match_reasons=match_reasons,
            exact_id_match=is_exact_id,
            category_compatible=is_cat_compatible,
            requested_viewpoint=requested_viewpoint,
            verified_viewpoint=viewpoint,
            viewpoint_confidence=round(vp_conf, 3),
            verified_viewpoint_confidence=round(vp_conf, 3),
            verified_viewpoint_source=vp_source,
            variant_evidence=variant_ev,
            visible_attributes=attributes,
            reconstruction_evidence=is_evidence,
            evidence_value=evidence_val,
            rejection_reason=rejection_reason,
            explanation=explanation,
            analyzer_source="multi_signal_rule_engine",
            retrieval_context=retrieval_ctx,
            source_page_url=source_url,
            source_domain=domain,
            query=query,
            query_family=query_family,
            query_priority=query_priority,
            title=title,
            snippet=snippet,
            source_engine=source_engine,
            download_status=candidate.get("download_status", "success"),
            image_dimensions=img_dims,
            prefilter_status=candidate.get("prefilter_status", "accepted"),
            dino_similarity=dino_sim,
            dino_status="evaluated" if dino_sim is not None else "skipped"
        )

    def _classify_candidate_type(
        self,
        text: str,
        candidate: Dict[str, Any]
    ) -> Tuple[CandidateType, float, str]:
        """
        Classifies the functional/document type of the image from candidate-owned metadata.
        """
        # 1. Accessories / standalone attachments
        for kw in TYPE_KEYWORDS[CandidateType.ACCESSORY]:
            if re.search(r'\b' + re.escape(kw) + r'\b', text):
                return CandidateType.ACCESSORY, 0.88, f"Standalone accessory matching '{kw}'"

        # 2. Spare parts / exploded diagrams
        for kw in TYPE_KEYWORDS[CandidateType.SPARE_PART]:
            if re.search(r'\b' + re.escape(kw) + r'\b', text):
                return CandidateType.SPARE_PART, 0.90, "Exploded spare parts assembly diagram"

        # 3. Technical drawings / dimensional blueprints
        for kw in TYPE_KEYWORDS[CandidateType.TECHNICAL_DRAWING]:
            if re.search(r'\b' + re.escape(kw) + r'\b', text):
                return CandidateType.TECHNICAL_DRAWING, 0.92, "Technical dimensional schematic or blueprint"

        # 4. Packaging
        for kw in TYPE_KEYWORDS[CandidateType.PACKAGING]:
            if re.search(r'\b' + re.escape(kw) + r'\b', text):
                return CandidateType.PACKAGING, 0.88, "Product packaging / shipping carton"

        # 5. Manuals / documentation
        for kw in TYPE_KEYWORDS[CandidateType.MANUAL_DOCUMENT]:
            if re.search(r'\b' + re.escape(kw) + r'\b', text):
                return CandidateType.MANUAL_DOCUMENT, 0.82, "Manual / datasheet document preview"

        return CandidateType.TARGET_PRODUCT, 0.70, "Standard product imagery"

    def _verify_product_identity(
        self,
        identity: Optional[Union[CanonicalProductIdentity, ProductIdentity]],
        text: str,
        candidate: Dict[str, Any],
        cand_type: CandidateType
    ) -> Tuple[ProductMatch, float, str, List[str], List[str]]:
        """
        Verifies whether the candidate metadata shows the exact target product.
        Strictly operates on candidate-owned text corpus (title, snippet, URL path, alt).
        """
        if not identity:
            return ProductMatch.UNCERTAIN, 0.50, "No canonical identity supplied for matching", [], ["missing_identity"]

        brand = ""
        product_name = ""
        model_number = ""
        article_number = ""
        category = ""
        official_domains: List[str] = []

        if isinstance(identity, CanonicalProductIdentity):
            brand = identity.canonical_brand or identity.raw_identity.brand or ""
            product_name = identity.canonical_product_name or identity.raw_identity.product_name or ""
            model_number = identity.canonical_model or identity.raw_identity.model_number or ""
            article_number = identity.raw_identity.article_number or ""
            category = identity.canonical_category or identity.raw_identity.category or ""
            official_domains = identity.source_domains or []
        elif isinstance(identity, ProductIdentity):
            brand = identity.brand or ""
            product_name = identity.product_name or ""
            model_number = identity.model_number or ""
            article_number = identity.article_number or ""
            category = identity.category or ""
            official_domains = getattr(identity, "source_urls", []) or []

        evidence_sources = []
        match_reasons = []

        # 1. Check official domain origin
        is_official_domain = False
        source_domain = candidate.get("source_domain", "").lower()
        source_url = candidate.get("source_page_url", "").lower()
        if official_domains:
            if any(dom in source_domain or dom in source_url for dom in official_domains):
                is_official_domain = True
                evidence_sources.append("official_domain")
                match_reasons.append("official_portal_origin")

        # 2. Check for exact article / model number in candidate-owned metadata with strict boundaries
        has_exact_article = False
        matched_id_str = None
        for art in [article_number, model_number]:
            if art and is_exact_identifier_match(art, text):
                has_exact_article = True
                matched_id_str = art.strip()
                evidence_sources.append("model_or_article_number")
                match_reasons.append(f"exact_identifier_{matched_id_str.lower()}")
                break

        # 3. Check for brand name in candidate-owned metadata
        has_brand = False
        if brand and len(brand.strip()) >= 2:
            if re.search(r'\b' + re.escape(brand.lower()) + r'\b', text):
                has_brand = True
                evidence_sources.append("brand_metadata")
                match_reasons.append("brand_corroborated")

        # 4. Check for Category Conflicts (Primary Category Anchor Gate)
        target_cat_key = extract_primary_category(product_name=product_name, category=category)
        is_cat_conflict, t_cat, conf_term = detect_category_conflict(target_cat_key, text)
        if is_cat_conflict and not has_exact_article:
            return (
                ProductMatch.DIFFERENT_PRODUCT,
                0.95,
                f"Category conflict: Target is '{t_cat}', candidate mentions conflicting category '{conf_term}' (CATEGORY_CONFLICT)",
                ["category_conflict"],
                ["category_conflict"]
            )

        # 5. Check for core product name tokens in candidate-owned metadata (non-generic tokens only)
        has_product_name = False
        if product_name:
            norm_name = product_name.lower()
            tokens = [
                t.strip("-_/.,") for t in re.split(r"\s+", norm_name)
                if len(t.strip("-_/.,")) >= 2 and t.strip("-_/.,") not in GENERIC_STOP_TOKENS
            ]
            if tokens:
                matched_tokens = []
                has_alphanumeric_model_token = False
                for t in tokens:
                    p = rf"(?<![a-zA-Z0-9]){re.escape(t)}(?![a-zA-Z0-9])"
                    if re.search(p, text):
                        matched_tokens.append(t)
                        if any(c.isdigit() for c in t) and any(c.isalpha() for c in t):
                            has_alphanumeric_model_token = True
                
                if has_alphanumeric_model_token or len(matched_tokens) >= max(1, math.ceil(len(tokens) * 0.33)):
                    has_product_name = True
                    evidence_sources.append("product_title_tokens")
                    match_reasons.append("title_tokens_corroborated")


        # 6. Check for competing brands (contradictory signal)
        category_key = "sanitary"
        if category or target_cat_key:
            cat_lower = f"{category or ''} {target_cat_key or ''}".lower()
            if "industrial" in cat_lower or "heat" in cat_lower or "plc" in cat_lower or "automation" in cat_lower:
                category_key = "industrial"
            elif "electronic" in cat_lower or "projector" in cat_lower or "phone" in cat_lower or "audio" in cat_lower or "headphone" in cat_lower:
                category_key = "electronics"
            elif "footwear" in cat_lower or "apparel" in cat_lower:
                category_key = "footwear"

        competing = COMPETING_BRANDS.get(category_key, [])
        found_competing = []
        for b in competing:
            if brand and brand.lower() == "hansgrohe" and b == "grohe":
                continue
            if brand and b == brand.lower():
                continue
            if re.search(r"\b" + re.escape(b) + r"\b", text):
                found_competing.append(b)

        if found_competing:
            return ProductMatch.DIFFERENT_PRODUCT, 0.95, f"Competing brand '{found_competing[0].title()}' detected in candidate source", ["competing_brand"], ["competing_brand_isolation"]

        # 7. Contradictory article numbers (e.g. searching for 43218000 but metadata specifically states 43229000)
        numeric_articles = re.findall(r"\b\d{8}\b", text)
        if article_number and numeric_articles:
            if article_number not in numeric_articles and not has_exact_article:
                return ProductMatch.DIFFERENT_PRODUCT, 0.92, f"Contradictory article number '{numeric_articles[0]}' does not match target '{article_number}'", ["article_number"], ["contradictory_article"]

        # 8. Contradictory cross-category contamination check
        if category:
            cat_l = category.lower()
            if any(c in cat_l for c in ["sanitary", "sink", "industrial", "electronic", "projector", "hardware", "furniture", "seating", "automotive"]):
                if any(bad in text for bad in ["sneaker", "running shoe", "air max", "footwear", "nike", "przewalski", "wild horse", "bison herd", "yellowstone", "worksheets"]):
                    return ProductMatch.DIFFERENT_PRODUCT, 0.99, "Cross-category contamination rejected", ["cross_category"], ["category_isolation"]

        # --------------------------------------------------------------------
        # DECISION HIERARCHY (EXACT_ID_MATCH > STRONG_IDENTITY > UNCERTAIN)
        # --------------------------------------------------------------------

        # TIER 1: EXACT ID MATCH (Official portal + exact SKU/model)
        if is_official_domain and has_exact_article:
            return ProductMatch.EXACT_ID_MATCH, 0.99, f"Verified from official portal ({candidate.get('source_domain')}) with exact article/model match", evidence_sources, match_reasons

        # TIER 2: EXACT ID MATCH (Exact article/model + Brand)
        if has_exact_article and has_brand:
            return ProductMatch.EXACT_ID_MATCH, 0.96, f"Exact article/model number '{matched_id_str}' and brand '{brand}' matched in metadata", evidence_sources, match_reasons

        # TIER 3: EXACT ID MATCH (Exact article/model confirmed)
        if has_exact_article:
            return ProductMatch.EXACT_ID_MATCH, 0.92, f"Exact article/model number '{matched_id_str}' confirmed in candidate text", evidence_sources, match_reasons

        # TIER 4: STRONG PRODUCT IDENTITY (Official domain + product name match)
        if is_official_domain and has_product_name:
            return ProductMatch.TARGET_PRODUCT, 0.90, f"Verified from official portal ({candidate.get('source_domain')}) matching '{product_name}'", evidence_sources, match_reasons

        # TIER 5: STRONG PRODUCT IDENTITY (Brand + specific non-generic product name tokens)
        if has_brand and has_product_name:
            return ProductMatch.TARGET_PRODUCT, 0.82, f"Brand '{brand}' and product name '{product_name}' corroborated in metadata", evidence_sources, match_reasons

        # TIER 6: WEAK / UNCERTAIN
        if has_product_name:
            return ProductMatch.UNCERTAIN, 0.50, "Product name matched but specific model/article could not be independently confirmed", evidence_sources, match_reasons

        if has_brand:
            return ProductMatch.UNCERTAIN, 0.35, f"Brand '{brand}' found in candidate but specific model unconfirmed (INSUFFICIENT_PRODUCT_IDENTITY)", evidence_sources, match_reasons

        return ProductMatch.UNCERTAIN, 0.20, "Insufficient candidate metadata to corroborate product identity (INSUFFICIENT_PRODUCT_IDENTITY)", [], ["no_candidate_evidence"]

    def _classify_viewpoint(
        self,
        text: str,
        candidate: Dict[str, Any],
        cand_type: CandidateType
    ) -> Tuple[Viewpoint, float, str]:
        """
        Identifies the physical viewpoint shown in the image from candidate-owned evidence.
        Does NOT infer viewpoint from the retrieval query!
        """
        # If it's a technical drawing
        if cand_type == CandidateType.TECHNICAL_DRAWING:
            return Viewpoint.TECHNICAL, 0.95, "technical_drawing_metadata"

        # Check candidate-owned evidence text (title, alt, snippet, path)
        norm_text = re.sub(r"[\W_]+", " ", text)
        for vp, kws in VIEWPOINT_KEYWORDS.items():
            for kw in kws:
                if re.search(r"\b" + re.escape(kw) + r"\b", norm_text):
                    return vp, 0.85, "candidate_text_evidence"

        # Without candidate-owned evidence, return UNKNOWN (never guess or inherit from query!)
        return Viewpoint.UNKNOWN, 0.0, "none"

    def _extract_visible_attributes(
        self,
        text: str,
        candidate: Dict[str, Any],
        identity: Optional[CanonicalProductIdentity],
        viewpoint: Viewpoint,
        cand_type: CandidateType,
        variant_ev: Optional[VariantEvidence] = None
    ) -> List[str]:
        """
        Extracts only visibly supported geometric, material, and variant attributes.
        Does NOT invent hidden geometry.
        """
        attrs: List[str] = []

        # Viewpoint-specific observed features
        if viewpoint == Viewpoint.BOTTOM:
            attrs.extend(["underside structure", "mounting interface / flanges / base"])
        elif viewpoint == Viewpoint.TOP:
            attrs.extend(["top planar surface", "top controls / ports / interface"])
        elif viewpoint == Viewpoint.FRONT:
            attrs.extend(["front elevation profile", "primary front face"])
        elif viewpoint == Viewpoint.REAR:
            attrs.extend(["rear utility connection ports", "rear panel profile"])
        elif viewpoint == Viewpoint.LEFT or viewpoint == Viewpoint.RIGHT:
            attrs.extend(["lateral orthogonal elevation", "depth aspect profile"])
        elif viewpoint == Viewpoint.TECHNICAL:
            attrs.extend(["dimensional cutout measurements", "outer length x width x depth specifications"])
        elif viewpoint == Viewpoint.DETAIL:
            attrs.extend(["micro-detail texture / finish", "connector / port closeup"])
        elif viewpoint == Viewpoint.INSTALLATION:
            attrs.extend(["mounting boundary", "lifestyle context environment"])
        elif viewpoint == Viewpoint.ISOMETRIC:
            attrs.extend(["3D perspective silhouette", "multi-face aspect profile"])

        # Variant & Appearance Attributes (Phase 2)
        if variant_ev:
            if variant_ev.color_raw:
                attrs.append(f"color: {variant_ev.color_raw}")
            if variant_ev.finish_raw:
                attrs.append(f"finish: {variant_ev.finish_raw}")
            if variant_ev.material_raw and not any("material:" in a for a in attrs):
                attrs.append(f"material: {variant_ev.material_raw}")
            if variant_ev.configuration:
                attrs.append(f"configuration: {variant_ev.configuration}")

        # Material & finish if mentioned in candidate text
        if "stainless" in text or "edelstahl" in text:
            if not any("stainless" in a for a in attrs):
                attrs.append("material: brushed stainless steel")
        elif "granite" in text or "silgranit" in text or "composite" in text:
            if not any("granite" in a for a in attrs):
                attrs.append("material: composite granite")
        elif "ceramic" in text or "keramik" in text:
            if not any("ceramic" in a for a in attrs):
                attrs.append("material: glazed ceramic")
        elif "aluminum" in text or "aluminium" in text:
            if not any("aluminum" in a for a in attrs):
                attrs.append("material: anodized aluminum")
        elif "leather" in text or "mesh" in text:
            if not any("leather" in a or "mesh" in a for a in attrs):
                attrs.append("material: synthetic fabric / mesh")

        # Dimensional attributes if present
        dim_match = re.search(r"(\d{3,4})\s*[xX*]\s*(\d{3,4})(?:\s*[xX*]\s*(\d{2,4}))?", text)
        if dim_match:
            d_str = f"dimensions: {dim_match.group(1)}x{dim_match.group(2)}"
            if dim_match.group(3):
                d_str += f"x{dim_match.group(3)}"
            d_str += " mm"
            attrs.append(d_str)

        if not attrs:
            attrs.append("overall silhouette: visible")

        return attrs

    def _assess_reconstruction_value(
        self,
        prod_match: ProductMatch,
        cand_type: CandidateType,
        viewpoint: Viewpoint,
        match_conf: float,
        existing_viewpoints: Set[Viewpoint],
        candidate: Dict[str, Any],
        evidence_sources: Optional[List[str]] = None
    ) -> Tuple[bool, EvidenceValue, str]:
        """
        Determines if the candidate provides actionable 3D reconstruction evidence.
        """
        sources = evidence_sources or []
        has_id = ("model_or_article_number" in sources) or (prod_match == ProductMatch.EXACT_ID_MATCH)
        is_official = "official_domain" in sources

        # Rejected/different products have zero evidence value
        if prod_match == ProductMatch.DIFFERENT_PRODUCT:
            return False, EvidenceValue.NONE, "Non-target product discarded"

        if cand_type in [CandidateType.PACKAGING, CandidateType.IRRELEVANT, CandidateType.MANUAL_DOCUMENT, CandidateType.ACCESSORY]:
            return False, EvidenceValue.NONE, f"{cand_type.value} does not provide physical asset geometry"

        if prod_match == ProductMatch.UNCERTAIN:
            return False, EvidenceValue.NONE, "Uncertain product match cannot be used as authoritative evidence (INSUFFICIENT_PRODUCT_IDENTITY)"

        # TECHNICAL DRAWING GATING:
        # Technical drawings provide reconstruction evidence if corroborated by exact SKU or official domain or verified target product
        if cand_type == CandidateType.TECHNICAL_DRAWING or viewpoint == Viewpoint.TECHNICAL:
            if has_id or is_official or prod_match in [ProductMatch.TARGET_PRODUCT, ProductMatch.EXACT_ID_MATCH]:
                return True, EvidenceValue.HIGH, "Dimensional schematic corroborated by product identity"
            return False, EvidenceValue.NONE, "Third-party technical drawing uncorroborated by exact model/SKU (UNTRUSTED_TECHNICAL_DRAWING)"


        # Spare parts diagram provides HIGH/MEDIUM internal/mounting value if product matches
        if cand_type == CandidateType.SPARE_PART:
            if has_id or is_official:
                return True, EvidenceValue.MEDIUM, "Spare parts diagram provides mounting & component breakdown"
            return False, EvidenceValue.NONE, "Spare parts diagram uncorroborated by exact model/SKU"

        # Orthogonal/critical viewpoints (BOTTOM, TOP, REAR, TECHNICAL) are HIGH value
        if viewpoint in [Viewpoint.BOTTOM, Viewpoint.TECHNICAL]:
            return True, EvidenceValue.HIGH, f"Critical orthogonal viewpoint ({viewpoint.value}) provides unique occluded geometry"

        # If viewpoint is verified and novel (not yet in accepted set)
        if viewpoint != Viewpoint.UNKNOWN and viewpoint not in existing_viewpoints:
            return True, EvidenceValue.HIGH, f"First verified {viewpoint.value} viewpoint in evidence pool"

        # If viewpoint already exists, evaluate redundancy
        if viewpoint != Viewpoint.UNKNOWN and viewpoint in existing_viewpoints:
            dino_sim = candidate.get("score") or candidate.get("dino_similarity")
            if dino_sim is not None and dino_sim > 0.95:
                return False, EvidenceValue.LOW, f"Redundant visual perspective with existing {viewpoint.value} reference (cosine > 0.95)"
            return True, EvidenceValue.MEDIUM, f"Supporting {viewpoint.value} viewpoint providing additional visual fidelity"

        # If viewpoint is UNKNOWN (no viewpoint metadata found in candidate)
        if viewpoint == Viewpoint.UNKNOWN:
            if len(existing_viewpoints) < 2:
                return True, EvidenceValue.MEDIUM, "Verified target product image with general perspective"
            return False, EvidenceValue.LOW, "Supporting view without distinct verified orthogonal angle"

        return True, EvidenceValue.MEDIUM, "Verified candidate product reference"


def evaluate_candidates_batch(
    candidates: List[Dict[str, Any]],
    identity: Optional[CanonicalProductIdentity] = None
) -> List[CandidateEvaluation]:
    """
    Evaluates an entire batch of candidates with intra-pool viewpoint coverage tracking.
    """
    analyzer = CandidateAnalyzerService(canonical_identity=identity)
    evaluations: List[CandidateEvaluation] = []
    accepted_viewpoints: Set[Viewpoint] = set()

    for cand in candidates:
        evaluation = analyzer.analyze_candidate(
            candidate=cand,
            identity=identity,
            existing_accepted_viewpoints=accepted_viewpoints
        )
        if evaluation.reconstruction_evidence:
            accepted_viewpoints.add(evaluation.verified_viewpoint)
        evaluations.append(evaluation)

    return evaluations

