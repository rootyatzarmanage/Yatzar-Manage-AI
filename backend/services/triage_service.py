"""
Geometric Uncertainty and Viewpoint Triage Service.
Evaluates single-view product seed images for rotational symmetry, quadrant occlusions,
and azimuthal uncertainty. Implements a strict Metadata Priority Cascade for query generation:
Priority 1 (Product ID) -> Priority 2 (Product Name + Model) -> Priority 3 (Name + Viewpoint Anchors)
-> Priority 4 (Category + Context) -> Priority 5 (User Fallback).
"""

import os
import re
import json
import base64
import logging
from typing import Optional, List, Dict, Any, Union
from pydantic import BaseModel, Field

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
    category: str = "",
    target_angles: Optional[List[str]] = None,
    raw_queries: Optional[List[str]] = None,
    dynamic_urls: Optional[List[str]] = None
) -> List[Dict[str, Any]]:
    """
    Constructs a prioritized search query ladder following the Metadata Priority Cascade:
      - Priority 1 (Product ID / SKU / Part Number): Exact identifier in quotes (e.g., "M393A4K40BB1-CRC")
      - Priority 2 (Product Name + Model Number): Brand/product title with specific model (e.g., "Sony WH-1000XM5")
      - Priority 3 (Product Name + Viewpoint Anchors): Exact quote matching paired with angle keywords
                   (front view, side profile, rear panel, isometric angle)
      - Priority 4 (Category + Model Context): Category with model/descriptors (e.g., "Industrial Equipment Alfa Laval heat exchanger orthogonal")
      - Priority 5 (Direct URLs / Fallback Query): Direct user-supplied query or scrape targets

    Returns:
        List of dicts: [{'priority': int, 'query': str, 'angle_tag': str, 'source_tier': str}, ...]
    """
    queries: List[Dict[str, Any]] = []
    seen_query_strings = set()

    p_id = (product_id or "").strip()
    p_name = (product_name or "").strip()
    p_model = (model_number or "").strip()
    p_cat = (category or "").strip()

    # Filter out generic placeholder IDs
    is_valid_id = bool(p_id and p_id.upper() not in ["PROD-GEN-01", "SKU-01", "CUSTOM", "NONE", "N/A"])
    is_valid_model = bool(p_model and p_model.upper() not in ["PROD-GEN-01", "SKU-01", "NONE", "N/A"])
    is_valid_name = bool(p_name and p_name.lower() not in ["product asset", "custom product asset", "product", "untitled"])

    def add_query(priority: int, q_str: str, angle_tag: str, tier_desc: str):
        cleaned = q_str.strip()
        if cleaned and cleaned not in seen_query_strings:
            seen_query_strings.add(cleaned)
            queries.append({
                "priority": priority,
                "query": cleaned,
                "angle_tag": angle_tag,
                "source_tier": tier_desc
            })

    # -------------------------------------------------------------
    # PRIORITY 1: Exact Product ID / SKU / Part Number in Quotes
    # -------------------------------------------------------------
    if is_valid_id:
        clean_id = p_id.strip('"')
        add_query(1, f'"{clean_id}"', "Front Reference", "Priority 1 (Exact Product ID / SKU)")
        add_query(1, f'"{clean_id}" photo', "Isometric Angle", "Priority 1 (Exact Product ID / SKU)")

    # -------------------------------------------------------------
    # PRIORITY 2: Product Name + Model Number
    # -------------------------------------------------------------
    if is_valid_name and is_valid_model:
        clean_name = p_name.strip('"')
        clean_model = p_model.strip('"')
        add_query(2, f'"{clean_name} {clean_model}"', "Isometric Angle", "Priority 2 (Product Name + Model Number)")
        add_query(2, f'"{clean_name}" "{clean_model}" product photo', "Front Reference", "Priority 2 (Product Name + Model Number)")
    elif is_valid_model and not is_valid_name:
        clean_model = p_model.strip('"')
        add_query(2, f'"{clean_model}" official product photo', "Isometric Angle", "Priority 2 (Model Number Only)")

    # -------------------------------------------------------------
    # PRIORITY 3: Product Name + Viewpoint Anchors
    # -------------------------------------------------------------
    base_name = p_name.strip('"') if is_valid_name else (p_model.strip('"') if is_valid_model else "Product")
    if is_valid_name or is_valid_model:
        clean_base = f'"{base_name}"'
        add_query(3, f'{clean_base} front view', "Front Reference", "Priority 3 (Name + Viewpoint Anchor: Front)")
        add_query(3, f'{clean_base} side profile', "Side Profile", "Priority 3 (Name + Viewpoint Anchor: Side)")
        add_query(3, f'{clean_base} rear panel', "Rear View", "Priority 3 (Name + Viewpoint Anchor: Rear)")
        add_query(3, f'{clean_base} isometric angle', "Isometric Angle", "Priority 3 (Name + Viewpoint Anchor: Isometric)")

    # -------------------------------------------------------------
    # PRIORITY 4: Category + Model Context
    # -------------------------------------------------------------
    if p_cat:
        clean_cat = p_cat.strip('"')
        descriptor = f"{clean_cat} {base_name}" if base_name != "Product" else clean_cat
        add_query(4, f'"{descriptor}" orthogonal view', "Side Profile", "Priority 4 (Category + Context)")
        add_query(4, f'{clean_cat} {base_name} technical diagram', "Rear View", "Priority 4 (Category + Context)")

    # -------------------------------------------------------------
    # PRIORITY 5: Direct URLs / User Raw Queries Fallback
    # -------------------------------------------------------------
    if raw_queries:
        for rq in raw_queries:
            if rq and rq.strip():
                ql = rq.lower()
                tag = "Rear View" if ("rear" in ql or "back" in ql) else ("Side Profile" if ("side" in ql or "profile" in ql) else ("Front Reference" if "front" in ql else "Isometric Angle"))
                add_query(5, rq.strip(), tag, "Priority 5 (User Query / Fallback)")

    if dynamic_urls:
        for du in dynamic_urls:
            if du and du.strip():
                add_query(5, du.strip(), "Isometric Angle", "Priority 5 (Direct Scrape URL)")

    # Fallback if empty
    if not queries:
        clean_base = f'"{base_name}"'
        add_query(3, f'{clean_base} front view', "Front Reference", "Priority 3 (Fallback)")
        add_query(3, f'{clean_base} side profile', "Side Profile", "Priority 3 (Fallback)")
        add_query(3, f'{clean_base} rear view', "Rear View", "Priority 3 (Fallback)")
        add_query(3, f'{clean_base} perspective angle', "Isometric Angle", "Priority 3 (Fallback)")

    # Sort queries strictly by priority tier (1 -> 2 -> 3 -> 4 -> 5)
    queries.sort(key=lambda x: x["priority"])
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
    product_title: str,
    product_sku: str,
    category: str = "",
    product_id: str = "",
    image_path: Optional[str] = None
) -> TriageResult:
    """
    Deterministic fallback heuristic implementing the strict Metadata Priority Cascade.
    """
    title_raw = (product_title or "").strip()
    sku_raw = (product_sku or "").strip()
    cat_raw = (category or "").strip()
    id_raw = (product_id or sku_raw).strip()

    title_lower = title_raw.lower()
    sku_lower = sku_raw.lower()
    cat_lower = cat_raw.lower()
    combined = f"{title_lower} {sku_lower} {cat_lower}"

    # Build prioritized queries via Metadata Priority Cascade
    prioritized_list = build_prioritized_search_queries(
        product_id=id_raw,
        product_name=title_raw,
        model_number=sku_raw,
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

    # 2. Benchmark Asset: iPhone / Smartphone / Electronics
    if "iphone" in combined or "smartphone" in combined or "phone" in combined:
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
            reasoning="Prismatic slab with camera bump asymmetry and specific bottom speaker/port cutouts.",
            source="heuristic_fallback"
        )

    # 3. Fans & Air Handling Devices
    fan_keywords = ["fan", "blower", "cooler", "ventilator", "turbine"]
    if any(k in combined for k in fan_keywords):
        quad = QuadUncertainty(front=0.05, rear=0.68, sides=0.55, bottom=0.38)
        max_blindspot = max(quad.rear, quad.sides, quad.bottom)
        skip = max_blindspot <= 0.15
        return TriageResult(
            rotational_symmetry=False,
            symmetry_confidence=0.89,
            quad_uncertainty=quad,
            skip_deep_scraping=skip,
            target_search_queries=query_strings,
            prioritized_queries=prioritized_list,
            max_scrape_budget=16 if not skip else 5,
            reasoning="Rotational blade symmetry enclosed in asymmetrical cage with distinct rear motor housing and base stand.",
            source="heuristic_fallback"
        )

    # 4. Footwear & Apparel
    shoe_keywords = ["shoe", "sneaker", "boot", "cleat", "loafer", "sandal", "footwear", "air max", "nike", "adidas"]
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
            reasoning="Bilateral asymmetric footwear with critical outsole tread grooves and rear heel collar structure.",
            source="heuristic_fallback"
        )

    # 5. Rotationally / Radially Symmetric Objects
    symmetric_keywords = ["bottle", "can", "cup", "mug", "cylinder", "pipe", "ball", "wheel", "tire", "vase", "bowl", "flask"]
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
    product_id: str = ""
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

        prompt = build_vision_llm_prompt(product_title, product_sku, category)

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

                # Augment with prioritized search queries
                p_queries = build_prioritized_search_queries(
                    product_id=product_id or product_sku,
                    product_name=product_title,
                    model_number=product_sku,
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
                    product_id=product_id or product_sku,
                    product_name=product_title,
                    model_number=product_sku,
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
    product_id: str = ""
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
            product_id=product_id
        )

    # Deterministic heuristic fallback
    if result is None:
        result = _heuristic_triage(
            product_title=product_title,
            product_sku=product_sku,
            category=category,
            product_id=product_id,
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
