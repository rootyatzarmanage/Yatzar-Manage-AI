"""
Geometric Uncertainty and Viewpoint Triage Service.
Evaluates single-view product seed images for rotational symmetry, quadrant occlusions,
and azimuthal uncertainty. Implements a strict Metadata Priority Cascade for query generation:
Priority 1 (Verified Manufacturer Identifier) -> Priority 2 (Product Name + Model) -> Priority 3 (Name + Viewpoint Anchors)
-> Priority 4 (Category + Context) -> Priority 5 (User Fallback).
"""

import os
import re
import json
import base64
import logging
from typing import Optional, List, Dict, Any, Union
from pydantic import BaseModel, Field

from services.identifier_policy import (
    is_safe_manufacturer_identifier,
    extract_verified_manufacturer_identifier,
    extract_brand_or_manufacturer,
    sanitize_query_against_internal_leakage,
    GENERIC_PLACEHOLDERS,
    ProductIdentity,
    CanonicalProductIdentity,
    normalize_product_identity
)

logger = logging.getLogger(__name__)


class QuadUncertainty(BaseModel):
    front: float = Field(..., description="Uncertainty for front facing features [0.0 - 1.0]")
    rear: float = Field(..., description="Uncertainty for rear panel / back plate [0.0 - 1.0]")
    sides: float = Field(..., description="Uncertainty for left/right orthogonal profiles [0.0 - 1.0]")
    bottom: float = Field(..., description="Uncertainty for bottom chassis/ports/mounts [0.0 - 1.0]")


class PrioritizedQuery(BaseModel):
    priority: int = Field(..., description="Priority tier (1 to 5)")
    query: str = Field(..., description="Formatted search query string with quotes/anchors")
    angle_tag: str = Field(..., description="Target viewpoint: Front Reference, Side Profile, Rear View, Isometric Angle")
    source_tier: str = Field(..., description="Description of the metadata tier")


class TriageResult(BaseModel):
    rotational_symmetry: bool = Field(..., description="True if object is radial/cylindrically symmetric")
    symmetry_confidence: float = Field(..., description="Confidence score in symmetry assessment [0.0 - 1.0]")
    quad_uncertainty: QuadUncertainty = Field(..., description="Quadrant-level occlusion and geometry uncertainty")
    skip_deep_scraping: bool = Field(..., description="True if max(rear, sides, bottom) <= 0.15 or high symmetry")
    target_search_queries: List[str] = Field(..., description="Prioritized queries for blindspots and occluded quadrants")
    prioritized_queries: Optional[List[Dict[str, Any]]] = Field(default=None, description="Detailed prioritized query ladder with metadata")
    max_scrape_budget: int = Field(..., description="Scrape budget count (3-5 for fast-track, 15-20 for deep scrape)")
    reasoning: Optional[str] = Field(default="", description="Structural triage rationale")
    source: str = Field(default="heuristic_fallback", description="Engine used (vision_llm or heuristic_fallback)")


def build_prioritized_search_queries(
    product_id: str = "",
    product_name: str = "",
    model_number: str = "",
    part_number: str = "",
    sku: str = "",
    brand: str = "",
    category: str = "",
    target_angles: Optional[List[str]] = None,
    raw_queries: Optional[List[str]] = None,
    dynamic_urls: Optional[List[str]] = None,
    article_number: str = "",
    user_prompt: str = ""
) -> List[Dict[str, Any]]:
    """
    Constructs a prioritized search query ladder following the Retrieval V2
    Multi-Family Query Strategy (Exact -> Viewpoints -> Technical -> Category Fallback).
    """
    from services.query_planner import QueryPlanner

    p_ident = ProductIdentity(
        internal_id=product_id or None,
        brand=brand or None,
        product_name=product_name or "",
        model_number=model_number or sku or None,
        article_number=article_number or None,
        part_number=part_number or None,
        sku=sku or None,
        category=category or None,
        source_urls=dynamic_urls or [],
        user_prompt=user_prompt or None
    )

    planned = QueryPlanner.plan(p_ident)

    # Convert to prioritized query dicts
    queries: List[Dict[str, Any]] = []
    for pq in planned:
        queries.append({
            "priority": pq.pass_stage,
            "query": pq.query,
            "angle_tag": pq.angle_tag,
            "source_tier": f"Pass {pq.pass_stage} ({pq.query_family.value})",
            "target_evidence": pq.target_evidence,
            "query_family": pq.query_family.value,
            "identifiers_used": pq.identifiers_used,
            "expected_information": pq.expected_information
        })

    # Include raw queries if specifically passed by caller
    if raw_queries:
        seen = {q["query"] for q in queries}
        for rq in raw_queries:
            if rq and rq.strip() and rq.strip() not in seen:
                seen.add(rq.strip())
                queries.append({
                    "priority": 4,
                    "query": rq.strip(),
                    "angle_tag": "Isometric Angle",
                    "source_tier": "Priority 4 (User Query Fallback)",
                    "target_evidence": "CATEGORY_CONTEXT",
                    "query_family": "USER_FALLBACK",
                    "identifiers_used": ["user_prompt"],
                    "expected_information": f"Direct user query: {rq.strip()}"
                })

    return queries


def build_vision_llm_prompt(product_title: str, product_sku: str, category: str = "") -> str:
    """
    Constructs a strict structured prompt for a Vision LLM to perform geometric uncertainty triage.
    """
    return f"""You are an expert industrial 3D reconstruction engineer evaluating a single 2D seed image of a product.
Product Title: "{product_title}"
Product SKU / Model: "{product_sku}"
Category: "{category}"

Analyze the visible 2D product and estimate geometric uncertainty for full 360-degree watertight 3D reconstruction.

Output a valid JSON object matching this exact schema:
{{
  "rotational_symmetry": <boolean, true if cylindrically or radially symmetric like a bottle, cylinder, cup, wheel>,
  "symmetry_confidence": <float between 0.0 and 1.0>,
  "quad_uncertainty": {{
    "front": <float between 0.0 and 1.0, 0.05 if visible in seed>,
    "rear": <float between 0.0 and 1.0, high if back ports/panels are unknown>,
    "sides": <float between 0.0 and 1.0, uncertainty for side profiles>,
    "bottom": <float between 0.0 and 1.0, uncertainty for feet, ports, mounting plate>
  }},
  "skip_deep_scraping": <boolean, true ONLY IF max(rear, sides, bottom) <= 0.15 or object has perfect rotational symmetry>,
  "target_search_queries": [
    "<specific targeted query for missing back view / ports>",
    "<specific targeted query for side profile / dimensions>",
    "<specific targeted query for bottom chassis / connection ports>"
  ],
  "max_scrape_budget": <integer, 3-5 if skip_deep_scraping is true, else 15-20>,
  "reasoning": "<concise explanation of symmetry and occluded angles>"
}}

Respond ONLY with the JSON object. Do not include markdown formatting or backticks if possible."""


def _heuristic_triage(
    product_title: str = "",
    product_sku: str = "",
    category: str = "",
    product_id: str = "",
    model_number: str = "",
    part_number: str = "",
    brand: str = "",
    image_path: Optional[str] = None
) -> TriageResult:
    """
    Deterministic fallback heuristic implementing the strict Metadata Priority Cascade.
    """
    title_raw = (product_title or "").strip()
    cat_raw = (category or "").strip()
    id_raw = (product_id or "").strip()
    model_raw = (model_number or product_sku or "").strip()
    part_raw = (part_number or "").strip()
    brand_raw = (brand or "").strip()

    title_lower = title_raw.lower()
    sku_lower = model_raw.lower()
    cat_lower = cat_raw.lower()
    combined = f"{title_lower} {sku_lower} {cat_lower} {brand_raw.lower()}"

    # Build prioritized queries via Retrieval V2 QueryPlanner
    prioritized_list = build_prioritized_search_queries(
        product_id=id_raw,
        product_name=title_raw,
        model_number=model_raw,
        part_number=part_raw,
        sku=product_sku,
        brand=brand_raw,
        category=cat_raw
    )
    query_strings = [item["query"] for item in prioritized_list]

    # 1. Benchmark Asset: Alfa Laval Heat Exchanger / Industrial Equipment
    if "alfa laval" in combined or "heat exchanger" in combined or "hex" in combined:
        quad = QuadUncertainty(front=0.05, rear=0.82, sides=0.68, bottom=0.88)
        max_blindspot = max(quad.rear, quad.sides, quad.bottom)
        skip = max_blindspot <= 0.15
        return TriageResult(
            rotational_symmetry=False,
            symmetry_confidence=0.96,
            quad_uncertainty=quad,
            skip_deep_scraping=skip,
            target_search_queries=query_strings,
            prioritized_queries=prioritized_list,
            max_scrape_budget=18 if not skip else 5,
            reasoning="Planar asymmetric industrial equipment with critical unseen rear fluid ports and side bolt assemblies.",
            source="heuristic_fallback"
        )

    # 2. Sinks, Basins, Faucets & Sanitary Ware (e.g. Hansgrohe, Roca)
    sanitary_keywords = ["sink", "basin", "combi", "faucet", "tap", "drain", "sanitary", "urinal", "toilet", "vanity", "hansgrohe", "grohe", "roca"]
    if any(k in combined for k in sanitary_keywords):
        quad = QuadUncertainty(front=0.05, rear=0.72, sides=0.58, bottom=0.85)
        max_blindspot = max(quad.rear, quad.sides, quad.bottom)
        skip = max_blindspot <= 0.15
        return TriageResult(
            rotational_symmetry=False,
            symmetry_confidence=0.92,
            quad_uncertainty=quad,
            skip_deep_scraping=skip,
            target_search_queries=query_strings,
            prioritized_queries=prioritized_list,
            max_scrape_budget=16 if not skip else 5,
            reasoning="Planar sanitary ware with critical unseen underside basin structure, mounting flanges, and overflow/drain fixtures.",
            source="heuristic_fallback"
        )

    # 3. Benchmark Asset: iPhone / Smartphone / Electronics / Projectors
    if "iphone" in combined or "smartphone" in combined or "phone" in combined or "projector" in combined or "laser" in combined or "viewsonic" in combined:
        quad = QuadUncertainty(front=0.05, rear=0.48, sides=0.32, bottom=0.42)
        max_blindspot = max(quad.rear, quad.sides, quad.bottom)
        skip = max_blindspot <= 0.15
        return TriageResult(
            rotational_symmetry=False,
            symmetry_confidence=0.94,
            quad_uncertainty=quad,
            skip_deep_scraping=skip,
            target_search_queries=query_strings,
            prioritized_queries=prioritized_list,
            max_scrape_budget=14 if not skip else 4,
            reasoning="Prismatic electronics enclosure with asymmetric IO connector panels, ventilation grilles, and lens mount.",
            source="heuristic_fallback"
        )

    # 4. Rotationally / Radially Symmetric Objects (Bottles, Cans, Cylinders)
    symmetric_keywords = ["bottle", "can", "cup", "mug", "cylinder", "pipe", "ball", "wheel", "tire", "vase", "bowl", "flask", "extinguisher"]
    if any(k in combined for k in symmetric_keywords):
        quad = QuadUncertainty(front=0.05, rear=0.10, sides=0.10, bottom=0.14)
        skip = True
        return TriageResult(
            rotational_symmetry=True,
            symmetry_confidence=0.95,
            quad_uncertainty=quad,
            skip_deep_scraping=skip,
            target_search_queries=query_strings,
            prioritized_queries=prioritized_list,
            max_scrape_budget=4,
            reasoning="High rotational symmetry along vertical axis; novel viewpoints can be inferred analytically.",
            source="heuristic_fallback"
        )

    # 5. Footwear & Apparel (Generic category)
    shoe_keywords = ["shoe", "sneaker", "boot", "cleat", "loafer", "sandal", "footwear"]
    if any(k in combined for k in shoe_keywords):
        quad = QuadUncertainty(front=0.05, rear=0.62, sides=0.35, bottom=0.75)
        max_blindspot = max(quad.rear, quad.sides, quad.bottom)
        skip = max_blindspot <= 0.15
        return TriageResult(
            rotational_symmetry=False,
            symmetry_confidence=0.86,
            quad_uncertainty=quad,
            skip_deep_scraping=skip,
            target_search_queries=query_strings,
            prioritized_queries=prioritized_list,
            max_scrape_budget=15 if not skip else 4,
            reasoning="Bilateral asymmetric footwear with outsole tread pattern and rear heel collar geometry.",
            source="heuristic_fallback"
        )

    # 6. Default General Asymmetric Object
    quad = QuadUncertainty(front=0.05, rear=0.65, sides=0.48, bottom=0.55)
    max_blindspot = max(quad.rear, quad.sides, quad.bottom)
    skip = max_blindspot <= 0.15
    return TriageResult(
        rotational_symmetry=False,
        symmetry_confidence=0.85,
        quad_uncertainty=quad,
        skip_deep_scraping=skip,
        target_search_queries=query_strings,
        prioritized_queries=prioritized_list,
        max_scrape_budget=15 if not skip else 5,
        reasoning="General asymmetric object with standard multi-view ambiguity across rear and profile quadrants.",
        source="heuristic_fallback"
    )



def _call_vision_llm(
    image_path: str,
    product_title: str,
    product_sku: str,
    category: str = "",
    product_id: str = "",
    model_number: str = "",
    part_number: str = "",
    brand: str = ""
) -> Optional[TriageResult]:
    """
    Calls Gemini or OpenAI Vision API if configured via environment variables.
    """
    gemini_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    openai_key = os.getenv("OPENAI_API_KEY")

    if not (gemini_key or openai_key):
        return None

    if not image_path or not os.path.exists(image_path):
        return None

    try:
        with open(image_path, "rb") as f:
            b64_image = base64.b64encode(f.read()).decode("utf-8")

        prompt = build_vision_llm_prompt(product_title, model_number or product_sku, category)

        # Gemini API call if key present
        if gemini_key:
            import requests
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={gemini_key}"
            payload = {
                "contents": [{
                    "parts": [
                        {"text": prompt},
                        {
                            "inline_data": {
                                "mime_type": "image/jpeg",
                                "data": b64_image
                            }
                        }
                    ]
                }],
                "generationConfig": {
                    "response_mime_type": "application/json",
                    "temperature": 0.1
                }
            }
            resp = requests.post(url, json=payload, timeout=20)
            if resp.status_code == 200:
                data = resp.json()
                raw_text = data["candidates"][0]["content"]["parts"][0]["text"]
                parsed = json.loads(raw_text)
                parsed["source"] = "vision_llm_gemini"

                # Augment with prioritized search queries enforcing provenance
                p_queries = build_prioritized_search_queries(
                    product_id=product_id,
                    product_name=product_title,
                    model_number=model_number or product_sku,
                    part_number=part_number,
                    sku=product_sku,
                    brand=brand,
                    category=category,
                    raw_queries=parsed.get("target_search_queries")
                )
                parsed["prioritized_queries"] = p_queries
                parsed["target_search_queries"] = [pq["query"] for pq in p_queries]
                return TriageResult(**parsed)

        # OpenAI API call if key present
        if openai_key:
            import requests
            headers = {
                "Authorization": f"Bearer {openai_key}",
                "Content-Type": "application/json"
            }
            payload = {
                "model": "gpt-4o-mini",
                "response_format": {"type": "json_object"},
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {
                                "type": "image_url",
                                "image_url": {"url": f"data:image/jpeg;base64,{b64_image}"}
                            }
                        ]
                    }
                ],
                "temperature": 0.1
            }
            resp = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload, timeout=20)
            if resp.status_code == 200:
                data = resp.json()
                raw_text = data["choices"][0]["message"]["content"]
                parsed = json.loads(raw_text)
                parsed["source"] = "vision_llm_openai"

                p_queries = build_prioritized_search_queries(
                    product_id=product_id,
                    product_name=product_title,
                    model_number=model_number or product_sku,
                    part_number=part_number,
                    sku=product_sku,
                    brand=brand,
                    category=category,
                    raw_queries=parsed.get("target_search_queries")
                )
                parsed["prioritized_queries"] = p_queries
                parsed["target_search_queries"] = [pq["query"] for pq in p_queries]
                return TriageResult(**parsed)

    except Exception as e:
        logger.warning(f"Vision LLM call failed, falling back to heuristic triage: {e}")

    return None


def evaluate_geometric_uncertainty(
    image_path: Optional[str] = None,
    product_title: str = "",
    product_sku: str = "",
    category: str = "",
    product_id: str = "",
    model_number: str = "",
    part_number: str = "",
    brand: str = ""
) -> Dict[str, Any]:
    """
    Main entry point for Stage 1: Geometric Uncertainty and Viewpoint Triage.
    Evaluates product image & metadata, producing a structured triage assessment
    with prioritized queries matching the Metadata Priority Cascade.
    """
    result: Optional[TriageResult] = None

    # Attempt Vision LLM if image and API key are available
    if image_path and os.path.isfile(image_path):
        result = _call_vision_llm(
            image_path=image_path,
            product_title=product_title,
            product_sku=product_sku,
            category=category,
            product_id=product_id,
            model_number=model_number,
            part_number=part_number,
            brand=brand
        )

    # Deterministic heuristic fallback
    if result is None:
        result = _heuristic_triage(
            product_title=product_title,
            product_sku=product_sku,
            category=category,
            product_id=product_id,
            model_number=model_number,
            part_number=part_number,
            brand=brand,
            image_path=image_path
        )

    max_blindspot = max(
        result.quad_uncertainty.rear,
        result.quad_uncertainty.sides,
        result.quad_uncertainty.bottom
    )
    if max_blindspot <= 0.15 or result.rotational_symmetry:
        result.skip_deep_scraping = True
        if result.max_scrape_budget > 5:
            result.max_scrape_budget = 4
    else:
        result.skip_deep_scraping = False
        if result.max_scrape_budget < 10:
            result.max_scrape_budget = 15

    return result.model_dump()
