"""
Query Planning and Retrieval Strategy Engine (Retrieval V2).

Transforms structured product metadata, seed image, source URLs, and optional user prompts
into a reliable, diversified, multi-family search strategy.
Eliminates single point of failure on user free-text prompts.
"""

import re
import logging
from enum import Enum
from typing import List, Dict, Any, Optional, Set, Union
from pydantic import BaseModel, Field

from services.identifier_policy import (
    ProductIdentity,
    CanonicalProductIdentity,
    normalize_product_identity,
    sanitize_query_against_internal_leakage,
    GENERIC_PLACEHOLDERS
)

logger = logging.getLogger(__name__)


class QueryFamily(str, Enum):
    EXACT_PRODUCT = "EXACT_PRODUCT"
    SOURCE_DOMAIN = "SOURCE_DOMAIN"
    PRODUCT_VIEWPOINT = "PRODUCT_VIEWPOINT"
    PRODUCT_TECHNICAL = "PRODUCT_TECHNICAL"
    PRODUCT_COMPONENT = "PRODUCT_COMPONENT"
    CATEGORY_ATTRIBUTE = "CATEGORY_ATTRIBUTE"
    USER_FALLBACK = "USER_FALLBACK"


class TargetEvidence(str, Enum):
    EXACT_MATCH = "EXACT_MATCH"
    FRONT = "FRONT"
    REAR = "REAR"
    SIDE = "SIDE"
    TOP = "TOP"
    BOTTOM = "BOTTOM"
    ISOMETRIC = "ISOMETRIC"
    DIMENSIONS = "DIMENSIONS"
    TECHNICAL_DRAWING = "TECHNICAL_DRAWING"
    INSTALLATION = "INSTALLATION"
    MOUNTING = "MOUNTING"
    SPECIFICATION = "SPECIFICATION"
    SPARE_PARTS = "SPARE_PARTS"
    DRAIN_PORTS = "DRAIN_PORTS"
    COMPONENT = "COMPONENT"
    CATEGORY_CONTEXT = "CATEGORY_CONTEXT"


class PlannedQuery(BaseModel):
    """
    Structured query specification retaining provenance and quality purpose.
    """
    query: str = Field(..., description="The exact formatted search query string")
    query_family: QueryFamily = Field(..., description="Query family classification")
    priority: float = Field(..., description="Priority score between 0.0 and 1.0 (1.0 = highest)")
    pass_stage: int = Field(..., description="Staged retrieval pass (1=Exact/Domain, 2=Viewpoints, 3=Technical, 4=Fallback)")
    target_evidence: str = Field(..., description="Target viewpoint or engineering evidence type")
    identifiers_used: List[str] = Field(default_factory=list, description="Product identity fields used in this query")
    expected_information: str = Field(..., description="Rationale and expected visual/technical content")
    angle_tag: str = Field(default="Isometric Angle", description="Mapped 3D angle bucket")


class QueryPlanner:
    """
    Generates a staged, multi-family retrieval strategy from CanonicalProductIdentity.
    """

    @classmethod
    def plan(
        cls,
        identity: Union[ProductIdentity, CanonicalProductIdentity, Dict[str, Any]],
        max_stage: int = 3,
        include_domain_queries: bool = True
    ) -> List[PlannedQuery]:
        """
        Builds a comprehensive list of PlannedQuery items grouped across query families.
        """
        if isinstance(identity, dict):
            # Convert dict to ProductIdentity first
            p_ident = ProductIdentity(
                internal_id=identity.get("id") or identity.get("product_id") or identity.get("internal_id"),
                brand=identity.get("brand") or identity.get("manufacturer"),
                manufacturer=identity.get("manufacturer"),
                product_name=identity.get("name") or identity.get("product_name") or identity.get("product_title") or "",
                model_number=identity.get("modelNumber") or identity.get("model_number"),
                article_number=identity.get("articleNumber") or identity.get("article_number"),
                part_number=identity.get("partNumber") or identity.get("part_number"),
                sku=identity.get("sku") or identity.get("product_sku"),
                category=identity.get("category"),
                subcategory=identity.get("subcategory"),
                description=identity.get("description"),
                source_urls=identity.get("sourceUrls") or identity.get("source_urls") or identity.get("dynamic_urls") or [],
                dimensions=identity.get("dimensions"),
                color=identity.get("color"),
                material=identity.get("material"),
                user_prompt=identity.get("prompt") or identity.get("user_prompt")
            )
            canonical = normalize_product_identity(p_ident)
        elif isinstance(identity, ProductIdentity):
            canonical = normalize_product_identity(identity)
        elif isinstance(identity, CanonicalProductIdentity):
            canonical = identity
        else:
            raise ValueError(f"Unsupported identity type: {type(identity)}")

        internal_id = canonical.raw_identity.internal_id
        brand = canonical.canonical_brand
        p_name = canonical.canonical_product_name
        model = canonical.canonical_model
        category = canonical.canonical_category
        attrs = canonical.canonical_attributes
        domains = canonical.source_domains
        user_prompt = (canonical.raw_identity.user_prompt or "").strip()

        logger.info(
            f"[QUERY PLANNER] Planning retrieval strategy for Brand='{brand}', Name='{p_name}', "
            f"Model='{model}', Category='{category}', Domains={domains}"
        )

        planned_queries: List[PlannedQuery] = []
        seen_queries: Set[str] = set()

        def add_q(
            q_str: str,
            family: QueryFamily,
            priority: float,
            stage: int,
            target_ev: TargetEvidence,
            id_used: List[str],
            expected_info: str,
            angle_tag: str = "Isometric Angle"
        ):
            # Sanitize against internal DB ID leakage
            sanitized = sanitize_query_against_internal_leakage(q_str, [internal_id])
            if not sanitized:
                return
            clean = sanitized.strip()
            if clean and clean not in seen_queries:
                seen_queries.add(clean)
                planned_queries.append(PlannedQuery(
                    query=clean,
                    query_family=family,
                    priority=priority,
                    pass_stage=stage,
                    target_evidence=target_ev.value,
                    identifiers_used=id_used,
                    expected_information=expected_info,
                    angle_tag=angle_tag
                ))

        def format_brand_product(b_str: Optional[str], n_str: str) -> str:
            if not b_str:
                return n_str.strip()
            if not n_str:
                return b_str.strip()
            b_clean = b_str.strip()
            n_clean = n_str.strip()
            if n_clean.lower().startswith(b_clean.lower()):
                return n_clean
            return f"{b_clean} {n_clean}"

        # Best anchor descriptor for product without repeating brand tokens
        brand_prod = format_brand_product(brand, p_name)
        if brand_prod:
            primary_anchor = brand_prod
        elif model:
            primary_anchor = f"{brand} {model}".strip() if brand else model
        else:
            primary_anchor = category or "Product"

        # -------------------------------------------------------------
        # PASS 1: EXACT PRODUCT & SOURCE-DOMAIN QUERIES (Priority 0.95 - 1.0)
        # -------------------------------------------------------------
        # Family A: Exact Product
        if brand and model:
            add_q(
                f'"{brand} {model}"',
                QueryFamily.EXACT_PRODUCT,
                1.00,
                1,
                TargetEvidence.EXACT_MATCH,
                ["brand", "model_number"],
                f"Exact manufacturer search for {brand} model {model}",
                "Isometric Angle"
            )
            add_q(
                f'"{brand}" "{model}" official photo',
                QueryFamily.EXACT_PRODUCT,
                0.97,
                1,
                TargetEvidence.EXACT_MATCH,
                ["brand", "model_number"],
                f"High-resolution official catalog imagery for {brand} {model}",
                "Front Reference"
            )

        if brand and p_name and model:
            bp = format_brand_product(brand, p_name)
            add_q(
                f'"{bp}" "{model}"',
                QueryFamily.EXACT_PRODUCT,
                0.98,
                1,
                TargetEvidence.EXACT_MATCH,
                ["brand", "product_name", "model_number"],
                f"Full commercial title and model number {bp} {model}",
                "Isometric Angle"
            )

        if p_name and model and not brand:
            add_q(
                f'"{p_name} {model}"',
                QueryFamily.EXACT_PRODUCT,
                0.95,
                1,
                TargetEvidence.EXACT_MATCH,
                ["product_name", "model_number"],
                f"Product name and manufacturer model combination {p_name} {model}",
                "Isometric Angle"
            )

        if model and not (brand and model):
            add_q(
                f'"{model}" official product photo',
                QueryFamily.EXACT_PRODUCT,
                0.94,
                1,
                TargetEvidence.EXACT_MATCH,
                ["model_number"],
                f"Direct manufacturer article/model lookup for {model}",
                "Isometric Angle"
            )

        if brand and p_name and not model:
            bp = format_brand_product(brand, p_name)
            add_q(
                f'"{bp}" product photo',
                QueryFamily.EXACT_PRODUCT,
                0.93,
                2,
                TargetEvidence.EXACT_MATCH,
                ["brand", "product_name"],
                f"Brand and product name photo {bp}",
                "Front Reference"
            )

        # Family F: Source-Domain Queries
        if include_domain_queries and domains:
            for dom in domains:
                if model:
                    add_q(
                        f'site:{dom} "{model}"',
                        QueryFamily.SOURCE_DOMAIN,
                        0.96,
                        1,
                        TargetEvidence.EXACT_MATCH,
                        ["model_number", "source_domain"],
                        f"Official portal resource query for model {model} on {dom}",
                        "Front Reference"
                    )
                if p_name:
                    add_q(
                        f'site:{dom} "{p_name}"',
                        QueryFamily.SOURCE_DOMAIN,
                        0.94,
                        1,
                        TargetEvidence.EXACT_MATCH,
                        ["product_name", "source_domain"],
                        f"Official portal page search for {p_name} on {dom}",
                        "Isometric Angle"
                    )

        # -------------------------------------------------------------
        # PASS 2: PRODUCT + VIEWPOINT QUERIES (Priority 0.85 - 0.92)
        # -------------------------------------------------------------
        # Viewpoint search anchor: use "Brand Model" or "Brand Name" or "Name" without duplicates
        vp_anchor = f'"{brand} {model}"' if (brand and model) else f'"{primary_anchor}"'

        # Front View
        add_q(
            f'{vp_anchor} front view',
            QueryFamily.PRODUCT_VIEWPOINT,
            0.92,
            2,
            TargetEvidence.FRONT,
            ["brand", "model_number" if model else "product_name"],
            f"Frontal elevation and face profile of {primary_anchor}",
            "Front Reference"
        )

        # Side Profile
        add_q(
            f'{vp_anchor} side profile',
            QueryFamily.PRODUCT_VIEWPOINT,
            0.90,
            2,
            TargetEvidence.SIDE,
            ["brand", "model_number" if model else "product_name"],
            f"Left/right side orthogonal profile and depth elevation",
            "Side Profile"
        )

        # Rear View
        add_q(
            f'{vp_anchor} rear view',
            QueryFamily.PRODUCT_VIEWPOINT,
            0.89,
            2,
            TargetEvidence.REAR,
            ["brand", "model_number" if model else "product_name"],
            f"Rear panel, back face, connection ports and rear brackets",
            "Rear View"
        )

        # Top View
        add_q(
            f'{vp_anchor} top view',
            QueryFamily.PRODUCT_VIEWPOINT,
            0.88,
            2,
            TargetEvidence.TOP,
            ["brand", "model_number" if model else "product_name"],
            f"Top-down planar elevation, surface geometry and cutouts",
            "Front Reference"
        )

        # Underside / Bottom View
        add_q(
            f'{vp_anchor} underside bottom view',
            QueryFamily.PRODUCT_VIEWPOINT,
            0.87,
            2,
            TargetEvidence.BOTTOM,
            ["brand", "model_number" if model else "product_name"],
            f"Underside chassis, drain basin, bottom mounting flanges or feet",
            "Rear View"
        )

        # Isometric Angle
        add_q(
            f'{vp_anchor} isometric 3D angle',
            QueryFamily.PRODUCT_VIEWPOINT,
            0.86,
            2,
            TargetEvidence.ISOMETRIC,
            ["brand", "model_number" if model else "product_name"],
            f"Isometric 3D angle showing multiple orthogonal faces simultaneously",
            "Isometric Angle"
        )

        # -------------------------------------------------------------
        # PASS 3: PRODUCT + TECHNICAL EVIDENCE & COMPONENTS (Priority 0.70 - 0.82)
        # -------------------------------------------------------------
        # Family C: Technical Evidence
        add_q(
            f'{vp_anchor} technical drawing dimensions',
            QueryFamily.PRODUCT_TECHNICAL,
            0.82,
            3,
            TargetEvidence.TECHNICAL_DRAWING,
            ["brand", "model_number" if model else "product_name"],
            f"Technical 2D engineering drawing with millimeter dimensional callouts",
            "Front Reference"
        )

        add_q(
            f'{vp_anchor} dimensional specification sheet',
            QueryFamily.PRODUCT_TECHNICAL,
            0.80,
            3,
            TargetEvidence.DIMENSIONS,
            ["brand", "model_number" if model else "product_name"],
            f"Engineering data sheet, CAD outline, and outer bounding dimensions",
            "Front Reference"
        )

        add_q(
            f'{vp_anchor} installation manual mounting diagram',
            QueryFamily.PRODUCT_TECHNICAL,
            0.78,
            3,
            TargetEvidence.INSTALLATION,
            ["brand", "model_number" if model else "product_name"],
            f"Installation handbook diagrams and cutout template drawings",
            "Side Profile"
        )

        # Family D: Product Components (Evidence-Driven per Category / Attributes)
        combined_cat_text = f"{p_name} {category or ''} {user_prompt}".lower()
        
        # 1. Audio / Headphones / Earphones
        if any(k in combined_cat_text for k in ["headphone", "earphone", "headset", "earbud", "audio"]):
            add_q(
                f'{vp_anchor} ear cups headband hinge',
                QueryFamily.PRODUCT_COMPONENT,
                0.76,
                3,
                TargetEvidence.COMPONENT,
                ["brand" if brand else "product_name"],
                f"Earcups, headband adjustment, and pivot hinge details",
                "Rear View"
            )
            add_q(
                f'{vp_anchor} charging port audio controls',
                QueryFamily.PRODUCT_COMPONENT,
                0.74,
                3,
                TargetEvidence.COMPONENT,
                ["brand" if brand else "product_name"],
                f"Charging interface, button layout, and acoustic vents",
                "Isometric Angle"
            )
        # 2. Phones / Smartphones / Cameras / Projectors / Displays
        elif any(k in combined_cat_text for k in ["phone", "smartphone", "iphone", "camera", "projector", "display", "monitor"]):
            add_q(
                f'{vp_anchor} camera module interface ports',
                QueryFamily.PRODUCT_COMPONENT,
                0.76,
                3,
                TargetEvidence.COMPONENT,
                ["brand" if brand else "product_name"],
                f"Camera module, rear port interface, and buttons",
                "Rear View"
            )
        # 3. Plumbing / Sanitary / Sinks / Faucets
        elif any(k in combined_cat_text for k in ["sink", "sanitary", "faucet", "basin", "plumbing", "drainer"]):
            add_q(
                f'{vp_anchor} drain connection overflow',
                QueryFamily.PRODUCT_COMPONENT,
                0.76,
                3,
                TargetEvidence.DRAIN_PORTS,
                ["brand", "model_number" if model else "product_name"],
                f"Drain basket, waste set, overflow and underside plumbing fittings",
                "Rear View"
            )
            add_q(
                f'{vp_anchor} spare parts exploded view',
                QueryFamily.PRODUCT_COMPONENT,
                0.74,
                3,
                TargetEvidence.SPARE_PARTS,
                ["brand", "model_number" if model else "product_name"],
                f"Exploded parts diagram and component assembly breakdown",
                "Isometric Angle"
            )
        # 4. Industrial Automation / PLC / Controllers / Modules
        elif any(k in combined_cat_text for k in ["plc", "controller", "terminal", "module", "automation", "inverter", "drive", "sensor"]):
            add_q(
                f'{vp_anchor} terminal block wiring connectors',
                QueryFamily.PRODUCT_COMPONENT,
                0.76,
                3,
                TargetEvidence.COMPONENT,
                ["brand" if brand else "product_name"],
                f"Terminal connection blocks, status LEDs, and bus interface",
                "Rear View"
            )
            add_q(
                f'{vp_anchor} din rail mounting schematic',
                QueryFamily.PRODUCT_COMPONENT,
                0.74,
                3,
                TargetEvidence.COMPONENT,
                ["brand" if brand else "product_name"],
                f"DIN rail clip mechanism and mounting bracket schematic",
                "Isometric Angle"
            )
        # 5. Industrial Fluid / Heat Exchangers / Pumps / Valves
        elif any(k in combined_cat_text for k in ["heat exchanger", "plate pack", "pump", "valve", "compressor"]):
            add_q(
                f'{vp_anchor} connection ports flange tightening bolts',
                QueryFamily.PRODUCT_COMPONENT,
                0.76,
                3,
                TargetEvidence.COMPONENT,
                ["brand", "model_number" if model else "product_name"],
                f"Port flanges, tightening bolts, and frame plate assembly",
                "Rear View"
            )
            add_q(
                f'{vp_anchor} exploded spare parts schematic',
                QueryFamily.PRODUCT_COMPONENT,
                0.74,
                3,
                TargetEvidence.SPARE_PARTS,
                ["brand", "model_number" if model else "product_name"],
                f"Exploded mechanical schematic and frame components",
                "Isometric Angle"
            )
        # 6. Seating / Chairs / Office Furniture
        elif any(k in combined_cat_text for k in ["chair", "seating", "desk chair", "armchair", "stool"]):
            add_q(
                f'{vp_anchor} caster base gas lift mechanism',
                QueryFamily.PRODUCT_COMPONENT,
                0.76,
                3,
                TargetEvidence.COMPONENT,
                ["product_name"],
                f"5-star caster base, gas lift cylinder, and tilt mechanism",
                "Rear View"
            )
            add_q(
                f'{vp_anchor} armrest lumbar support adjustment',
                QueryFamily.PRODUCT_COMPONENT,
                0.74,
                3,
                TargetEvidence.COMPONENT,
                ["product_name"],
                f"Armrest mounting, 3D lumbar support, and backrest frame",
                "Isometric Angle"
            )
        # 7. Automotive / Vehicles
        elif any(k in combined_cat_text for k in ["car", "sedan", "vehicle", "automotive", "sports car", "coupe", "truck", "suv"]):
            add_q(
                f'{vp_anchor} wheel rim exhaust rear wing spoiler',
                QueryFamily.PRODUCT_COMPONENT,
                0.76,
                3,
                TargetEvidence.COMPONENT,
                ["brand" if brand else "product_name"],
                f"Aerodynamic rear diffuser, spoiler, and wheel rim details",
                "Rear View"
            )
            add_q(
                f'{vp_anchor} front grille headlight cluster',
                QueryFamily.PRODUCT_COMPONENT,
                0.74,
                3,
                TargetEvidence.COMPONENT,
                ["brand" if brand else "product_name"],
                f"Front air intake grille and aerodynamic bumper profile",
                "Front Reference"
            )

        # -------------------------------------------------------------
        # PASS 4: CATEGORY + ATTRIBUTE / USER FALLBACK (Priority 0.50 - 0.65)
        # -------------------------------------------------------------
        color_attr = attrs.get("color")
        mat_attr = attrs.get("material")
        dim_attr = attrs.get("dimension_spec")

        if category and brand:
            attr_part = f"{color_attr} " if color_attr else ""
            add_q(
                f'"{brand}" {category} {attr_part}product view',
                QueryFamily.CATEGORY_ATTRIBUTE,
                0.62,
                4,
                TargetEvidence.CATEGORY_CONTEXT,
                ["brand", "category"],
                f"Broader category search for {brand} {category} with attribute {attr_part}",
                "Isometric Angle"
            )

        if category and not brand and p_name:
            add_q(
                f'"{category}" "{p_name}" orthogonal elevation',
                QueryFamily.CATEGORY_ATTRIBUTE,
                0.58,
                4,
                TargetEvidence.CATEGORY_CONTEXT,
                ["category", "product_name"],
                f"Category-scoped orthogonal view for {p_name}",
                "Side Profile"
            )

        # User Prompt (Only if non-empty, sanitized against internal IDs, and distinct)
        if user_prompt and user_prompt.upper() not in GENERIC_PLACEHOLDERS:
            # Check if user prompt is not purely identical to an existing query
            clean_prompt = user_prompt.strip('"').strip("'")
            if len(clean_prompt) >= 3 and clean_prompt.lower() not in [p.query.lower() for p in planned_queries]:
                add_q(
                    clean_prompt,
                    QueryFamily.USER_FALLBACK,
                    0.52,
                    4,
                    TargetEvidence.CATEGORY_CONTEXT,
                    ["user_prompt"],
                    f"Direct user search prompt fallback: {clean_prompt}",
                    "Isometric Angle"
                )

        # Fallback if empty
        if not planned_queries:
            clean_base = f'"{primary_anchor}"'
            add_q(f'{clean_base} front photo', QueryFamily.PRODUCT_VIEWPOINT, 0.85, 2, TargetEvidence.FRONT, ["product_name"], "Front photo fallback", "Front Reference")
            add_q(f'{clean_base} side photo', QueryFamily.PRODUCT_VIEWPOINT, 0.80, 2, TargetEvidence.SIDE, ["product_name"], "Side photo fallback", "Side Profile")
            add_q(f'{clean_base} rear photo', QueryFamily.PRODUCT_VIEWPOINT, 0.75, 2, TargetEvidence.REAR, ["product_name"], "Rear photo fallback", "Rear View")

        # Sort queries: pass_stage ascending (1 -> 2 -> 3 -> 4), priority descending
        planned_queries.sort(key=lambda x: (x.pass_stage, -x.priority))
        return planned_queries


def plan_retrieval_queries(
    identity: Union[ProductIdentity, CanonicalProductIdentity, Dict[str, Any]],
    max_stage: int = 3
) -> List[PlannedQuery]:
    """Convenience helper function for query planning."""
    return QueryPlanner.plan(identity, max_stage=max_stage)
