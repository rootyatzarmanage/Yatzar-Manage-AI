"""
Variant and Appearance Policy Layer (Phase 2).

Provides structured modeling, deterministic extraction, normalization,
and compatibility evaluation for product variants, colors, finishes,
materials, and physical configurations.

Core Principles:
1. Product Identity != Variant/Appearance.
2. Query text is RETRIEVAL CONTEXT, NEVER candidate evidence.
3. The candidate pool is NEVER the ground-truth for target color (no majority-color trap).
4. UNKNOWN is a first-class state, not a failure or mismatch.
5. Preserves raw manufacturer terminology alongside normalized canonical families.
"""

import re
import logging
from enum import Enum
from typing import Optional, List, Dict, Any, Tuple, Set, Union
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


# ============================================================================
# STRUCTURED ENUMS & MODELS
# ============================================================================

class VariantState(str, Enum):
    MATCH = "MATCH"                     # Authoritatively matches target variant
    COMPATIBLE = "COMPATIBLE"           # Compatible base appearance or color family
    CONFLICT = "CONFLICT"               # Explicitly contradicts target model/color/config
    UNKNOWN = "UNKNOWN"                 # Insufficient candidate-owned evidence


class VariantSource(str, Enum):
    EXPLICIT_USER = "EXPLICIT_USER"
    OFFICIAL_METADATA = "OFFICIAL_METADATA"
    CANDIDATE_ARTICLE_SKU = "CANDIDATE_ARTICLE_SKU"
    CANDIDATE_METADATA = "CANDIDATE_METADATA"     # Title, alt text, DOM, URL path
    HEURISTIC_COLOR_ESTIMATION = "HEURISTIC_COLOR_ESTIMATION"  # Low-confidence visual fallback
    NONE = "NONE"


class VariantEvidence(BaseModel):
    """
    Lightweight, audit-ready variant and appearance evidence container.
    """
    color_raw: Optional[str] = Field(default=None, description="Raw unnormalized color string")
    color_normalized: Optional[str] = Field(default=None, description="Normalized canonical color family")
    finish_raw: Optional[str] = Field(default=None, description="Finish or surface treatment (e.g. Matte, Gloss)")
    material_raw: Optional[str] = Field(default=None, description="Observed material description")
    model_variant: Optional[str] = Field(default=None, description="Specific sub-model or article code")
    configuration: Optional[str] = Field(default=None, description="Chassis, port layout, or mounting configuration")

    evidence_state: VariantState = Field(default=VariantState.UNKNOWN, description="Variant relationship to target")
    confidence: float = Field(default=0.0, ge=0.0, le=1.0, description="Confidence in variant classification")
    evidence_source: VariantSource = Field(default=VariantSource.NONE, description="Provenance tier of evidence")
    evidence_snippets: List[str] = Field(default_factory=list, description="Exact substrings from candidate text")
    conflict_details: Optional[str] = Field(default=None, description="Explanation if marked CONFLICT")


class TargetVariantDefinition(BaseModel):
    """
    Authoritative target appearance and variant definition resolved from input metadata.
    """
    target_color_raw: Optional[str] = Field(default=None, description="Raw target color")
    target_color_normalized: Optional[str] = Field(default=None, description="Normalized canonical color family")
    target_finish: Optional[str] = Field(default=None, description="Target finish or surface treatment")
    target_material: Optional[str] = Field(default=None, description="Target material")
    target_model_variant: Optional[str] = Field(default=None, description="Primary target model/article variant code")
    target_model_variants: List[str] = Field(default_factory=list, description="All known verified model/article variant codes for target")
    target_configuration: Optional[str] = Field(default=None, description="Target configuration")

    is_color_specified: bool = Field(default=False, description="True if target color is explicitly known")
    is_variant_specified: bool = Field(default=False, description="True if target model variant is explicitly known")
    confidence: float = Field(default=0.0, ge=0.0, le=1.0, description="Confidence in target definition")
    source: VariantSource = Field(default=VariantSource.NONE, description="Provenance source of target")


# ============================================================================
# CANONICAL VOCABULARIES & COLOR MAPS
# ============================================================================

# Maps specific manufacturer / descriptive color tokens to canonical base color families
COLOR_FAMILY_MAP: Dict[str, str] = {
    # Black Family
    "black": "black",
    "jet black": "black",
    "matte black": "black",
    "matt black": "black",
    "obsidian black": "black",
    "space black": "black",
    "midnight": "black",
    "onyx": "black",
    "ebony": "black",
    "schwarz": "black",
    "mattschwarz": "black",
    "noir": "black",

    # White Family
    "white": "white",
    "pure white": "white",
    "polar white": "white",
    "pearl white": "white",
    "matte white": "white",
    "ivory": "white",
    "cream": "white",
    "weiss": "white",
    "weiß": "white",
    "blanc": "white",

    # Silver / Gray Family
    "silver": "silver",
    "platinum silver": "silver",
    "sterling silver": "silver",
    "silber": "silver",
    "space gray": "gray",
    "space grey": "gray",
    "gray": "gray",
    "grey": "gray",
    "grau": "gray",
    "graphite": "gray",
    "titanium": "gray",
    "gunmetal": "gray",
    "slate": "gray",
    "charcoal": "gray",
    "anthracite": "gray",
    "silgranit anthracite": "gray",
    "corris grey": "gray",
    "corris gray": "gray",

    # Blue Family
    "blue": "blue",
    "velocity blue": "blue",
    "metallic blue": "blue",
    "sapphire blue": "blue",
    "navy blue": "blue",
    "navy": "blue",
    "midnight blue": "blue",
    "pacific blue": "blue",
    "sky blue": "blue",
    "cyan": "blue",
    "teal": "blue",
    "royal blue": "blue",
    "blau": "blue",
    "bleu": "blue",

    # Red / Orange Family
    "red": "red",
    "crimson": "red",
    "ruby": "red",
    "maroon": "red",
    "burgundy": "red",
    "rot": "red",
    "rouge": "red",
    "orange": "orange",
    "valencia orange": "orange",
    "coral": "orange",
    "amber": "orange",

    # Gold / Bronze / Yellow Family
    "gold": "gold",
    "rose gold": "gold",
    "champagne": "gold",
    "yellow": "yellow",
    "gelb": "yellow",
    "bronze": "bronze",
    "brass": "brass",
    "messing": "brass",
    "copper": "copper",
    "kupfer": "copper",

    # Green Family
    "green": "green",
    "emerald": "green",
    "olive": "green",
    "forest green": "green",
    "sage": "green",
    "mint": "green",
    "grün": "green",
    "vert": "green",

    # Metallic / Chrome Finishes
    "chrome": "chrome",
    "chrom": "chrome",
    "polished chrome": "chrome",
    "brushed chrome": "chrome",
    "stainless steel": "stainless steel",
    "stainless": "stainless steel",
    "edelstahl": "stainless steel",
    "brushed stainless": "stainless steel"
}

FINISH_KEYWORDS: List[str] = [
    "matte", "matt", "gloss", "glossy", "metallic", "satin", "brushed",
    "anodized", "polished", "textured", "frosted", "hochglanz", "gebürstet",
    "seidenmatt", "poliert"
]

MATERIAL_KEYWORDS: Dict[str, str] = {
    "stainless steel": "stainless steel",
    "edelstahl": "stainless steel",
    "granite": "composite granite",
    "silgranit": "composite granite",
    "silicatec": "composite granite",
    "composite": "composite granite",
    "ceramic": "ceramic",
    "keramik": "ceramic",
    "vitreous china": "vitreous china",
    "porcelain": "porcelain",
    "aluminum": "aluminum",
    "aluminium": "aluminum",
    "carbon fiber": "carbon fiber",
    "carbon": "carbon fiber",
    "leather": "leather",
    "leder": "leather",
    "mesh": "mesh fabric",
    "plastic": "plastic",
    "kunststoff": "plastic",
    "wood": "wood",
    "holz": "wood",
    "glass": "glass",
    "glas": "glass",
    "brass": "brass",
    "bronze": "bronze",
    "copper": "copper"
}

CONFIGURATION_KEYWORDS: Dict[str, str] = {
    "single bowl": "single_bowl",
    "double bowl": "double_bowl",
    "1.5 bowl": "one_and_half_bowl",
    "undermount": "undermount",
    "flushmount": "flushmount",
    "flachbündig": "flushmount",
    "countertop": "countertop",
    "wall mount": "wall_mount",
    "dc/dc/dc": "dc_dc_dc",
    "ac/dc/rly": "ac_dc_relay",
    "ac/dc/relay": "ac_dc_relay"
}


# ============================================================================
# NORMALIZATION & EXTRACTION ENGINE
# ============================================================================

def normalize_color(raw_color: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
    """
    Normalizes a raw color string into (canonical_color_family, detected_finish).
    Preserves raw color semantic nuance while mapping to standard family.
    """
    if not raw_color or not isinstance(raw_color, str):
        return None, None

    cleaned = raw_color.strip().lower()
    if not cleaned or cleaned in ["n/a", "none", "unknown", "null", "default"]:
        return None, None

    # Detect finish keyword if present
    detected_finish = None
    for f in FINISH_KEYWORDS:
        if re.search(r'\b' + re.escape(f) + r'\b', cleaned):
            detected_finish = f.title()
            break

    # Exact dictionary match
    if cleaned in COLOR_FAMILY_MAP:
        return COLOR_FAMILY_MAP[cleaned], detected_finish

    # Substring / multi-word token search (longest match first)
    sorted_color_keys = sorted(COLOR_FAMILY_MAP.keys(), key=len, reverse=True)
    for c_key in sorted_color_keys:
        if re.search(r'\b' + re.escape(c_key) + r'\b', cleaned):
            return COLOR_FAMILY_MAP[c_key], detected_finish

    return cleaned, detected_finish


def resolve_target_variant(
    identity: Any,
    user_prompt: Optional[str] = None
) -> TargetVariantDefinition:
    """
    Resolves the authoritative Target Variant Definition from the product identity hierarchy.

    Hierarchy:
    1. Explicit user-provided target variant / color field (identity.color)
    2. Exact manufacturer model / article / SKU metadata (identity.model_number, article_number)
    3. User prompt explicit attribute extraction (e.g. "Velocity Blue", "Black")
    4. Canonical attributes dictionary
    5. UNKNOWN (if no target variant is specified)

    CRITICAL: The candidate pool is NEVER inspected here. No majority-color guessing.
    """
    raw_ident = getattr(identity, "raw_identity", identity)

    raw_color = getattr(raw_ident, "color", None) or getattr(identity, "color", None)
    raw_material = getattr(raw_ident, "material", None) or getattr(identity, "material", None)
    user_p = user_prompt or getattr(raw_ident, "user_prompt", None) or ""

    # Collect all verified manufacturer identifiers
    target_model_variants: List[str] = []
    for m in [
        getattr(raw_ident, 'model_number', None),
        getattr(raw_ident, 'article_number', None),
        getattr(raw_ident, 'part_number', None),
        getattr(raw_ident, 'sku', None),
        getattr(identity, 'canonical_model', None)
    ]:
        if m and str(m).strip() and str(m).strip() not in target_model_variants:
            target_model_variants.append(str(m).strip())

    raw_model = target_model_variants[0] if target_model_variants else None

    canonical_attrs = getattr(identity, "canonical_attributes", {})

    target_color = raw_color
    target_source = VariantSource.EXPLICIT_USER if raw_color else VariantSource.NONE
    target_conf = 0.95 if raw_color else 0.0

    # If no explicit color field, check canonical_attributes
    if not target_color and canonical_attrs.get("color"):
        target_color = str(canonical_attrs.get("color"))
        target_source = VariantSource.OFFICIAL_METADATA
        target_conf = 0.88

    # If still no color, extract from explicit user prompt if present
    if not target_color and user_p:
        u_lower = user_p.lower()
        sorted_color_keys = sorted(COLOR_FAMILY_MAP.keys(), key=len, reverse=True)
        for c_key in sorted_color_keys:
            if re.search(r'\b' + re.escape(c_key) + r'\b', u_lower):
                target_color = c_key.title()
                target_source = VariantSource.EXPLICIT_USER
                target_conf = 0.90
                break

    # Normalize color and extract finish
    norm_color, det_finish = normalize_color(target_color)

    # Detect material
    det_material = raw_material or canonical_attrs.get("material")
    if not det_material and user_p:
        u_lower = user_p.lower()
        for mat_key, mat_val in MATERIAL_KEYWORDS.items():
            if re.search(r'\b' + re.escape(mat_key) + r'\b', u_lower):
                det_material = mat_val.title()
                break

    # Detect configuration
    det_config = None
    combined_text = f"{user_p} {getattr(raw_ident, 'product_name', '')} {getattr(raw_ident, 'description', '')}".lower()
    for cfg_key, cfg_val in CONFIGURATION_KEYWORDS.items():
        if re.search(r'\b' + re.escape(cfg_key) + r'\b', combined_text):
            det_config = cfg_val
            break

    is_color_known = norm_color is not None
    is_var_known = bool(target_model_variants or det_config)

    overall_conf = target_conf if is_color_known else (0.80 if is_var_known else 0.0)
    final_source = target_source if is_color_known else (VariantSource.CANDIDATE_ARTICLE_SKU if is_var_known else VariantSource.NONE)

    return TargetVariantDefinition(
        target_color_raw=target_color,
        target_color_normalized=norm_color,
        target_finish=det_finish,
        target_material=det_material,
        target_model_variant=raw_model,
        target_model_variants=target_model_variants,
        target_configuration=det_config,
        is_color_specified=is_color_known,
        is_variant_specified=is_var_known,
        confidence=overall_conf,
        source=final_source
    )


def extract_candidate_variant_evidence(
    candidate_evidence_text: str,
    candidate: Dict[str, Any],
    target: Optional[TargetVariantDefinition] = None
) -> VariantEvidence:
    """
    Extracts variant evidence strictly from candidate-owned text and metadata.
    STRICTLY excludes query text, query family, or requested viewpoints.
    """
    if not candidate_evidence_text:
        return VariantEvidence(
            evidence_state=VariantState.UNKNOWN,
            confidence=0.0,
            evidence_source=VariantSource.NONE
        )

    text_lower = candidate_evidence_text.lower()
    snippets: List[str] = []

    # 1. Color extraction from candidate text
    extracted_color_raw: Optional[str] = None
    extracted_color_norm: Optional[str] = None
    extracted_finish: Optional[str] = None

    sorted_color_keys = sorted(COLOR_FAMILY_MAP.keys(), key=len, reverse=True)
    for c_key in sorted_color_keys:
        match = re.search(r'\b' + re.escape(c_key) + r'\b', text_lower)
        if match:
            extracted_color_raw = c_key.title()
            extracted_color_norm, detected_finish = normalize_color(c_key)
            extracted_finish = detected_finish
            snippets.append(f"color: {extracted_color_raw}")
            break

    # Look for finish keywords if not found with color
    if not extracted_finish:
        for f in FINISH_KEYWORDS:
            if re.search(r'\b' + re.escape(f) + r'\b', text_lower):
                extracted_finish = f.title()
                snippets.append(f"finish: {extracted_finish}")
                break

    # 2. Material extraction from candidate text
    extracted_material: Optional[str] = None
    for mat_key, mat_val in MATERIAL_KEYWORDS.items():
        if re.search(r'\b' + re.escape(mat_key) + r'\b', text_lower):
            extracted_material = mat_val.title()
            snippets.append(f"material: {extracted_material}")
            break

    # 3. Model variant / article code extraction from candidate text
    extracted_model_variant: Optional[str] = None
    # Look for Siemens-style alphanumeric variants e.g. 6ES7214-1AG40-0XB0
    s7_match = re.search(r'\b(6es7[0-9]{3}-[0-9][a-z0-9]{4}-[0-9][a-z0-9]{3})\b', text_lower)
    if s7_match:
        extracted_model_variant = s7_match.group(1).upper()
        snippets.append(f"article_variant: {extracted_model_variant}")
    else:
        # Standard 8-digit article number
        art_match = re.search(r'\b\d{8}\b', text_lower)
        if art_match:
            extracted_model_variant = art_match.group(0)
            snippets.append(f"article_variant: {extracted_model_variant}")

    # 4. Configuration extraction from candidate text
    extracted_config: Optional[str] = None
    for cfg_key, cfg_val in CONFIGURATION_KEYWORDS.items():
        if re.search(r'\b' + re.escape(cfg_key) + r'\b', text_lower):
            extracted_config = cfg_val
            snippets.append(f"configuration: {extracted_config}")
            break

    # Determine confidence and evidence source
    evidence_source = VariantSource.NONE
    confidence = 0.0
    if snippets:
        evidence_source = VariantSource.CANDIDATE_METADATA
        confidence = 0.85

    # Check for DOM metadata or structured candidate properties if available
    dom_meta = candidate.get("dom_metadata")
    if isinstance(dom_meta, dict):
        if dom_meta.get("color"):
            extracted_color_raw = str(dom_meta["color"]).title()
            extracted_color_norm, _ = normalize_color(extracted_color_raw)
            evidence_source = VariantSource.OFFICIAL_METADATA
            confidence = 0.95
            snippets.append(f"dom_color: {extracted_color_raw}")

    initial_evidence = VariantEvidence(
        color_raw=extracted_color_raw,
        color_normalized=extracted_color_norm,
        finish_raw=extracted_finish,
        material_raw=extracted_material,
        model_variant=extracted_model_variant,
        configuration=extracted_config,
        evidence_state=VariantState.UNKNOWN,
        confidence=confidence,
        evidence_source=evidence_source,
        evidence_snippets=snippets,
        conflict_details=None
    )

    # If target is provided, evaluate compatibility
    if target:
        return evaluate_variant_compatibility(initial_evidence, target)

    return initial_evidence


def evaluate_variant_compatibility(
    candidate_ev: VariantEvidence,
    target: TargetVariantDefinition
) -> VariantEvidence:
    """
    Evaluates candidate variant evidence against the resolved target variant.
    Produces MATCH, COMPATIBLE, CONFLICT, or UNKNOWN.
    """
    # If target has neither color nor variant specified, everything is eligible / UNKNOWN
    if not target.is_color_specified and not target.is_variant_specified:
        candidate_ev.evidence_state = VariantState.UNKNOWN
        return candidate_ev

    reasons: List[str] = []
    is_conflict = False
    is_exact_match = False
    is_compatible = False

    # 1. Model / Article variant check (Hardest constraint)
    if target.target_model_variants and candidate_ev.model_variant:
        c_model = candidate_ev.model_variant.strip().lower()
        t_models_lower = [m.lower() for m in target.target_model_variants]
        if c_model in t_models_lower:
            is_exact_match = True
            reasons.append(f"Exact model/article match '{candidate_ev.model_variant}'")
        else:
            is_conflict = True
            reasons.append(f"Model variant conflict: target is '{target.target_model_variant}', candidate is '{candidate_ev.model_variant}'")

    # 2. Configuration check
    if target.target_configuration and candidate_ev.configuration:
        if target.target_configuration == candidate_ev.configuration:
            is_compatible = True
            reasons.append(f"Configuration match '{target.target_configuration}'")
        else:
            is_conflict = True
            reasons.append(f"Configuration conflict: target '{target.target_configuration}' vs candidate '{candidate_ev.configuration}'")

    # 3. Color & Finish check
    if target.is_color_specified:
        t_color_norm = target.target_color_normalized
        t_color_raw = (target.target_color_raw or "").lower()

        if candidate_ev.color_normalized:
            c_color_norm = candidate_ev.color_normalized
            c_color_raw = (candidate_ev.color_raw or "").lower()

            if t_color_raw and c_color_raw and t_color_raw == c_color_raw:
                # Exact raw color match (e.g. "Velocity Blue" == "Velocity Blue" or "Black" == "Black")
                is_exact_match = True
                reasons.append(f"Exact raw color match '{candidate_ev.color_raw}'")
            elif t_color_norm == c_color_norm:
                # Same canonical family
                # Check if target specified a distinct branded modifier (e.g. "Velocity Blue") vs a different modifier ("Metallic Blue")
                target_is_specific_shade = t_color_raw not in COLOR_FAMILY_MAP.values() and len(t_color_raw.split()) > 1
                cand_is_specific_shade = c_color_raw not in COLOR_FAMILY_MAP.values() and len(c_color_raw.split()) > 1

                if target_is_specific_shade and cand_is_specific_shade and t_color_raw != c_color_raw:
                    is_compatible = True
                    reasons.append(f"Compatible color family '{c_color_norm}' (target '{target.target_color_raw}' vs candidate '{candidate_ev.color_raw}')")
                else:
                    is_exact_match = True
                    reasons.append(f"Matching color family '{c_color_norm}'")
            else:
                # Contradictory color family (e.g. "Silver" vs "Black")
                is_conflict = True
                reasons.append(f"Color conflict: target is '{target.target_color_raw}' ({t_color_norm}), candidate is '{candidate_ev.color_raw}' ({c_color_norm})")

    # Determine final state
    if is_conflict:
        candidate_ev.evidence_state = VariantState.CONFLICT
        candidate_ev.conflict_details = "; ".join(reasons)
        candidate_ev.confidence = max(0.85, candidate_ev.confidence)
    elif is_exact_match:
        candidate_ev.evidence_state = VariantState.MATCH
        candidate_ev.confidence = max(0.90, candidate_ev.confidence)
    elif is_compatible:
        candidate_ev.evidence_state = VariantState.COMPATIBLE
        candidate_ev.confidence = max(0.80, candidate_ev.confidence)
    else:
        candidate_ev.evidence_state = VariantState.UNKNOWN

    return candidate_ev
