"""
Identifier Normalization and Validation Policy Layer.

Enforces field provenance and prevents internal database keys, UUIDs,
synthetic slug IDs, and unverified tokens from leaking into search queries.
Distinguishes between internal identifiers (never searched) and validated
manufacturer identifiers (suitable for Tier 1 public search).
"""

import re
import urllib.parse
from typing import Optional, Dict, Any, List, Set, Tuple
from pydantic import BaseModel, Field


# Patterns matching internal database keys, UUIDs, hashes, and synthetic slugs
UUID_PATTERN = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)
HEX_HASH_PATTERN = re.compile(r"^[0-9a-fA-F]{24,64}$")
INTERNAL_PREFIX_PATTERN = re.compile(
    r"^(PROD|INTERNAL|ITEM|ASSET|DB|SYS|TEMP|DRAFT|RECORD|ID|OBJECT|KEY|ROW)[-_:]",
    re.IGNORECASE,
)
INTERNAL_SLUG_PATTERN = re.compile(
    r"^(prod|internal|item|asset|db|sys|temp|draft|record|id)_[0-9a-zA-Z_]+$",
    re.IGNORECASE,
)
# Matches small pure integers that look like autoincrement primary keys (1 to 5 digits)
SMALL_INTEGER_PATTERN = re.compile(r"^\d{1,5}$")

# Blacklisted generic placeholder terms
GENERIC_PLACEHOLDERS: Set[str] = {
    "N/A",
    "NA",
    "NONE",
    "NULL",
    "CUSTOM",
    "UNKNOWN",
    "DEFAULT",
    "UNTITLED",
    "TBD",
    "SAMPLE",
    "TEST",
    "PLACEHOLDER",
    "GENERIC",
    "PROD-GEN-01",
    "SKU-01",
    "SKU-001",
    "MODEL-01",
    "PRODUCT ASSET",
    "CUSTOM PRODUCT ASSET",
    "PRODUCT",
    "UPLOADED PRODUCT ASSET",
}


class ProductIdentity(BaseModel):
    """
    Structured product identity model with explicit field provenance.
    Distinguishes internal database primary keys from verified manufacturer identifiers.
    """
    internal_id: Optional[str] = Field(
        default=None,
        description="Internal database primary key, UUID, or internal catalog ID (PROVENANCE: INTERNAL - NEVER SEARCHED)"
    )
    brand: Optional[str] = Field(
        default=None,
        description="Brand name (e.g. Hansgrohe, Apple, Alfa Laval, ViewSonic)"
    )
    manufacturer: Optional[str] = Field(
        default=None,
        description="Manufacturer name (synonym or parent brand)"
    )
    product_name: str = Field(
        default="",
        description="Commercial product name or title (e.g. C51 Sink Combi 660 Select, iPhone 15 Pro)"
    )
    model_number: Optional[str] = Field(
        default=None,
        description="Manufacturer model or article number (e.g. 43218000, A3102, LS740HD, EOB8S39Z)"
    )
    article_number: Optional[str] = Field(
        default=None,
        description="Manufacturer article / catalog number (e.g. 43218000)"
    )
    sku: Optional[str] = Field(
        default=None,
        description="Stock keeping unit (only used if verified manufacturer SKU)"
    )
    part_number: Optional[str] = Field(
        default=None,
        description="Manufacturer part number / MPN (e.g. AL-HEX-9000, MAXIMUS-MPX)"
    )
    category: Optional[str] = Field(
        default=None,
        description="Product taxonomy or category (e.g. Sanitary Ware, Kitchen Sink, Industrial Equipment)"
    )
    subcategory: Optional[str] = Field(
        default=None,
        description="Product subcategory or classification"
    )
    description: Optional[str] = Field(
        default=None,
        description="Product description or specification text"
    )
    source_urls: List[str] = Field(
        default_factory=list,
        description="Official source or product documentation URLs"
    )
    seed_image: Optional[str] = Field(
        default=None,
        description="Seed image path or URL"
    )
    dimensions: Optional[Dict[str, float]] = Field(
        default=None,
        description="Product dimensions (width, height, depth in mm or inches)"
    )
    color: Optional[str] = Field(
        default=None,
        description="Product color or finish (e.g. Black, Chrome, Blue)"
    )
    material: Optional[str] = Field(
        default=None,
        description="Product material (e.g. Granite, Stainless Steel, Vitreous China)"
    )
    user_prompt: Optional[str] = Field(
        default=None,
        description="Raw user-supplied prompt or search notes"
    )


class CanonicalProductIdentity(BaseModel):
    """
    Normalized canonical product identity representation for retrieval planning.
    """
    canonical_brand: Optional[str] = None
    canonical_product_name: str = ""
    canonical_model: Optional[str] = None
    canonical_category: Optional[str] = None
    canonical_attributes: Dict[str, Any] = Field(default_factory=dict)
    source_domains: List[str] = Field(default_factory=list)
    source_urls: List[str] = Field(default_factory=list)
    raw_identity: ProductIdentity = Field(default_factory=ProductIdentity)


def is_safe_manufacturer_identifier(token: Optional[str]) -> bool:
    """
    Evaluates whether an identifier string is a genuine, verified manufacturer identifier
    safe for public search engine queries (Tier 1).

    Rejects:
    - None / empty strings
    - Generic placeholder strings ("N/A", "NONE", "PROD-GEN-01", etc.)
    - Internal database prefix conventions (e.g. "PROD-IPHONE-08", "INTERNAL-1234", "ASSET-99")
    - Synthetic database slugs (e.g. "prod_123_temp")
    - Standard UUIDs (e.g. "8f7b3c2e-4d1a-4f5b-9c12-3e4f5a6b7c8d")
    - Hex hash digests (MD5, SHA, Mongo ObjectID)
    - Pure tiny integer keys (< 4 digits like "1", "12", "123")
    - Extremely short (< 2 chars) or long (> 60 chars) strings

    Accepts:
    - Standard alphanumeric model numbers ("A3102", "LS740HD", "AL-HEX-9000", "EOB8S39Z")
    - Standard manufacturer article numbers / EANs ("43218000", "0280158040", "10294")
    """
    if not token or not isinstance(token, str):
        return False

    cleaned = token.strip().strip('"').strip("'")
    if len(cleaned) < 2 or len(cleaned) > 60:
        return False

    # Check generic placeholders
    if cleaned.upper() in GENERIC_PLACEHOLDERS:
        return False

    # Check UUID pattern
    if UUID_PATTERN.match(cleaned):
        return False

    # Check hex hash patterns (24 to 64 hex characters)
    if HEX_HASH_PATTERN.match(cleaned):
        return False

    # Check internal database prefixes
    if INTERNAL_PREFIX_PATTERN.match(cleaned):
        return False

    # Check internal slug patterns
    if INTERNAL_SLUG_PATTERN.match(cleaned):
        return False

    # Reject tiny integers (1-3 digits) that look like autoincrement DB keys
    if SMALL_INTEGER_PATTERN.match(cleaned):
        return False

    # Must contain at least one alphanumeric character
    if not any(c.isalnum() for c in cleaned):
        return False

    return True


def normalize_manufacturer_identifier(token: Optional[str]) -> Optional[str]:
    """
    Sanitizes and normalizes a verified manufacturer identifier token.
    Returns None if the token fails safety verification.
    """
    if not is_safe_manufacturer_identifier(token):
        return None
    return token.strip().strip('"').strip("'")


def extract_verified_manufacturer_identifier(
    model_number: Optional[str] = None,
    part_number: Optional[str] = None,
    article_number: Optional[str] = None,
    sku: Optional[str] = None,
    product_id: Optional[str] = None,
    strict_provenance: bool = True
) -> Optional[str]:
    """
    Extracts the highest-confidence verified manufacturer identifier based strictly
    on field provenance:

    1. article_number (Direct manufacturer article/catalog number, e.g. 43218000)
    2. model_number (Highest confidence for commercial/electronic/consumer goods, e.g. A3102, LS740HD, 43218000)
    3. part_number (Highest confidence for industrial/mechanical/hardware goods, e.g. AL-HEX-9000)
    4. sku (Validated against manufacturer identifier rules)

    NOTE: `product_id` is an internal identifier and is NEVER used as a manufacturer identifier.
    """
    # 1. Article number check
    if article_number and is_safe_manufacturer_identifier(article_number):
        if not product_id or article_number.strip().lower() != product_id.strip().lower():
            return normalize_manufacturer_identifier(article_number)

    # 2. Model number check
    if model_number and is_safe_manufacturer_identifier(model_number):
        if not product_id or model_number.strip().lower() != product_id.strip().lower():
            return normalize_manufacturer_identifier(model_number)

    # 3. Part number check
    if part_number and is_safe_manufacturer_identifier(part_number):
        if not product_id or part_number.strip().lower() != product_id.strip().lower():
            return normalize_manufacturer_identifier(part_number)

    # 4. SKU check (only if safe and not identical to internal product_id)
    if sku and is_safe_manufacturer_identifier(sku):
        if not product_id or sku.strip().lower() != product_id.strip().lower():
            return normalize_manufacturer_identifier(sku)

    return None


def extract_brand_or_manufacturer(
    product_name: str = "",
    brand: Optional[str] = None,
    manufacturer: Optional[str] = None,
    category: str = ""
) -> Optional[str]:
    """
    Extracts or normalizes the brand name from explicit brand/manufacturer field or product title.
    """
    if brand and brand.strip() and brand.upper() not in GENERIC_PLACEHOLDERS:
        return brand.strip()

    if manufacturer and manufacturer.strip() and manufacturer.upper() not in GENERIC_PLACEHOLDERS:
        return manufacturer.strip()

    if not product_name:
        return None

    # Common known multi-word or single-word brand prefixes
    known_brands = [
        "Hansgrohe",
        "Grohe",
        "Alfa Laval",
        "Apple",
        "Sony",
        "Samsung",
        "Electrolux",
        "Nordpeis",
        "ViewSonic",
        "Videotec",
        "CEA Estintori",
        "Roca",
        "Logitech",
        "Bosch",
        "Siemens",
        "Philips",
        "Dell",
        "HP",
        "Lenovo",
        "Dyson",
        "Canon",
        "Nikon",
        "Bose",
        "Sennheiser",
        "Milwaukee",
        "DeWalt",
        "Makita",
        "Kohler",
        "Duravit",
        "Villeroy & Boch",
        "Franke",
        "Blanco",
        "Jaguar",
        "Herman Miller",
        "Steelcase",
        "Haworth",
    ]

    p_clean = product_name.replace("_", " ").strip()
    for b in known_brands:
        # Match whole word boundary at beginning of product name or within title
        if re.search(r'\b' + re.escape(b) + r'\b', p_clean, re.IGNORECASE):
            return b

    return None


def extract_attributes_from_text(text: str) -> Dict[str, Any]:
    """
    Extracts descriptive attributes (colors, materials, features) from product text/prompts.
    """
    attributes: Dict[str, Any] = {}
    if not text:
        return attributes

    text_lower = text.lower()

    # Colors
    colors = ["black", "white", "chrome", "stainless", "silver", "gold", "bronze", "grey", "gray", "matt black", "matte black", "graphite", "titanium", "blue", "red"]
    for c in colors:
        if re.search(rf'\b{re.escape(c)}\b', text_lower):
            attributes["color"] = c.title()
            break

    # Materials
    materials = ["silicatec", "granite", "stainless steel", "ceramic", "vitreous china", "aluminum", "brass", "copper", "glass", "wood", "plastic", "composite"]
    for m in materials:
        if re.search(rf'\b{re.escape(m)}\b', text_lower):
            attributes["material"] = m.title()
            break

    # Dimensions regex (e.g. 660, 660mm, 594x594)
    dim_match = re.search(r'(\d{2,4})\s*(?:mm|cm)?\s*(?:x\s*(\d{2,4}))?', text_lower)
    if dim_match:
        attributes["dimension_spec"] = dim_match.group(0).strip()

    return attributes


def normalize_product_identity(identity: ProductIdentity) -> CanonicalProductIdentity:
    """
    Builds a normalized CanonicalProductIdentity from structured input metadata,
    extracting clean brand, product title, verified manufacturer identifier,
    attributes, and source domains.
    """
    # 1. Brand Extraction
    brand = extract_brand_or_manufacturer(
        product_name=identity.product_name,
        brand=identity.brand,
        manufacturer=identity.manufacturer,
        category=identity.category or ""
    )

    # 2. Manufacturer Identifier Extraction
    mfr_id = extract_verified_manufacturer_identifier(
        model_number=identity.model_number,
        part_number=identity.part_number,
        article_number=identity.article_number,
        sku=identity.sku,
        product_id=identity.internal_id
    )

    # 3. Product Name Normalization
    raw_name = (identity.product_name or "").strip()
    if raw_name.upper() in GENERIC_PLACEHOLDERS or raw_name.lower() in ["product asset", "custom product asset", "untitled", "product"]:
        clean_name = ""
    else:
        clean_name = raw_name.replace("_", " ").strip()

    # 4. Category Normalization
    raw_cat = (identity.category or "").strip()
    clean_cat = raw_cat if raw_cat.upper() not in GENERIC_PLACEHOLDERS else None

    # 5. Extract Attributes from User Prompt, Description, and explicit fields
    combined_desc = f"{identity.user_prompt or ''} {identity.description or ''} {clean_name}"
    extracted_attrs = extract_attributes_from_text(combined_desc)
    if identity.color:
        extracted_attrs["color"] = identity.color
    if identity.material:
        extracted_attrs["material"] = identity.material
    if identity.dimensions:
        extracted_attrs["dimensions"] = identity.dimensions

    # 6. Parse Source Domains
    source_domains = []
    for u in identity.source_urls:
        if u and u.startswith("http"):
            try:
                parsed = urllib.parse.urlparse(u)
                if parsed.netloc:
                    domain = parsed.netloc.lower()
                    if domain.startswith("www."):
                        domain = domain[4:]
                    if domain not in source_domains:
                        source_domains.append(domain)
            except Exception:
                pass

    return CanonicalProductIdentity(
        canonical_brand=brand,
        canonical_product_name=clean_name,
        canonical_model=mfr_id,
        canonical_category=clean_cat,
        canonical_attributes=extracted_attrs,
        source_domains=source_domains,
        source_urls=identity.source_urls,
        raw_identity=identity
    )


def sanitize_query_against_internal_leakage(
    query_str: str,
    internal_ids: List[Optional[str]]
) -> str:
    """
    Ensures no internal ID or internal database token leaks into any generated query.
    If the entire query is an internal ID, returns empty string.
    """
    cleaned = query_str.strip()
    for i_id in internal_ids:
        if not i_id or not isinstance(i_id, str):
            continue
        raw_id = i_id.strip()
        if not raw_id:
            continue

        # If query is exactly the quoted or unquoted internal ID
        if cleaned == raw_id or cleaned == f'"{raw_id}"' or cleaned == f"'{raw_id}'":
            return ""

        # Remove internal ID token if it appears inside the query
        escaped = re.escape(raw_id)
        cleaned = re.sub(rf'\b{escaped}\b', '', cleaned, flags=re.IGNORECASE).strip()
        cleaned = re.sub(rf'"{escaped}"', '', cleaned, flags=re.IGNORECASE).strip()

    # Clean up double quotes and multi-spaces resulting from removal
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    if cleaned in ['""', "''", '"" ""', '']:
        return ""
    return cleaned


# ============================================================================
# IDENTIFIER & CATEGORY CORROBORATION HELPERS
# ============================================================================

def is_exact_identifier_match(target_id: Optional[str], text: str) -> bool:
    """
    Checks whether target_id explicitly occurs in candidate text using strict boundary matching.
    Supports standard hyphen/dot/space normalization (e.g. 43218000 matches 43218-000 or 43218.000).
    Rejects prefix/suffix expansions (e.g. 43218000 does NOT match 432180001 or 143218000).
    """
    if not target_id or not text:
        return False
    t_clean = target_id.strip().lower()
    if len(t_clean) < 3 or t_clean.upper() in GENERIC_PLACEHOLDERS:
        return False

    text_lower = text.lower()

    # Generate canonical variants (e.g. 43218000, 43218-000, 43218.000, 43218 000, wh1000xm5/b -> wh1000xm5, wh-1000xm5)
    variants = {t_clean}
    if "/" in t_clean:
        base_part = t_clean.split("/")[0].strip()
        if len(base_part) >= 3:
            variants.add(base_part)
            if re.search(r"[a-z]+\d+", base_part):
                # Insert hyphen between alpha and digits (e.g. wh1000xm5 -> wh-1000xm5)
                m = re.match(r"^([a-z]+)(\d+.*)$", base_part)
                if m:
                    variants.add(f"{m.group(1)}-{m.group(2)}")
    if re.match(r"^\d{8}$", t_clean):
        variants.add(f"{t_clean[:5]}-{t_clean[5:]}")
        variants.add(f"{t_clean[:5]}.{t_clean[5:]}")
        variants.add(f"{t_clean[:5]} {t_clean[5:]}")
    elif "-" in t_clean:
        variants.add(t_clean.replace("-", ""))
        variants.add(t_clean.replace("-", " "))
        variants.add(t_clean.replace("-", "."))
    elif "." in t_clean:
        variants.add(t_clean.replace(".", ""))
        variants.add(t_clean.replace(".", "-"))
        variants.add(t_clean.replace(".", " "))


    for v in variants:
        # Match with strict alphanumeric boundary lookaround to prevent substring false positives
        pattern = rf"(?<![a-zA-Z0-9]){re.escape(v)}(?![a-zA-Z0-9])"
        if re.search(pattern, text_lower):
            return True

    return False


CATEGORY_ANCHORS: Dict[str, Dict[str, List[str]]] = {
    "sink": {
        "keywords": ["sink", "kitchen sink", "washbasin", "lavello", "chiuveta", "mosogato", "spuelen", "spüle", "evier", "fregadero"],
        "conflicts": ["faucet", "tap", "mixer", "armatur", "miscelatore", "baterie", "csaptelep", "shower", "dusche", "brause", "showerpipe", "drain", "drainer", "toilet", "urinal", "bathtub", "badewanne", "soap dispenser"]
    },
    "faucet": {
        "keywords": ["faucet", "tap", "mixer", "armatur", "miscelatore", "baterie", "csaptelep", "basin mixer", "kitchen tap"],
        "conflicts": ["sink", "toilet", "urinal", "bathtub", "shower drain"]
    },
    "shower": {
        "keywords": ["shower", "dusche", "brause", "showerpipe", "hand shower", "showerhead", "shower set"],
        "conflicts": ["sink", "faucet", "tap", "toilet", "urinal", "bathtub"]
    },
    "drain": {
        "keywords": ["drain", "shower drain", "point drain", "linear drain", "ablauf", "bodenablauf"],
        "conflicts": ["sink", "faucet", "tap", "toilet", "bathtub"]
    },
    "toilet": {
        "keywords": ["toilet", "wc", "bidet", "urinal", "closet"],
        "conflicts": ["sink", "faucet", "shower", "bathtub"]
    },
    "bathtub": {
        "keywords": ["bathtub", "bath tub", "badewanne", "baignoire"],
        "conflicts": ["sink", "toilet", "urinal"]
    },
    "headphone": {
        "keywords": ["headphone", "headphones", "earphone", "earphones", "earbud", "earbuds", "headset", "kopfhoerer"],
        "conflicts": ["speaker", "soundbar", "microphone", "headphone stand", "ear cushions", "ear pads", "cable adapter"]
    },
    "speaker": {
        "keywords": ["speaker", "soundbar", "lautsprecher", "subwoofer"],
        "conflicts": ["headphone", "earphone", "headset", "display", "monitor"]
    },
    "monitor": {
        "keywords": ["monitor", "display", "screen", "projector", "beamer", "television", "tv"],
        "conflicts": ["keyboard", "mouse", "mousepad", "headphone"]
    },
    "keyboard": {
        "keywords": ["keyboard", "tastatur", "clavier"],
        "conflicts": ["mouse", "mousepad", "monitor", "headphone"]
    },
    "mouse": {
        "keywords": ["mouse", "gaming mouse", "maus"],
        "conflicts": ["keyboard", "monitor", "headphone"]
    },
    "chair": {
        "keywords": ["chair", "office chair", "stool", "seating", "armchair", "stuhl", "sessel"],
        "conflicts": ["table", "desk", "bed", "cabinet", "shelf"]
    },
    "table": {
        "keywords": ["table", "desk", "dining table", "coffee table", "tisch", "schreibtisch"],
        "conflicts": ["chair", "stool", "sofa", "bed"]
    },
    "heat_exchanger": {
        "keywords": ["heat exchanger", "plate heat exchanger", "waermetauscher", "wärmetauscher"],
        "conflicts": ["pump", "compressor", "boiler", "cooling tower", "gasket kit"]
    },
    "plc": {
        "keywords": ["plc", "programmable logic controller", "simatic", "cpu 1214", "cpu 1212", "cpu 151", "controller module"],
        "conflicts": ["power supply", "inverter", "frequency drive", "servo motor"]
    }
}


def extract_primary_category(product_name: str = "", category: Optional[str] = None) -> Optional[str]:
    """
    Extracts the normalized primary product category key from product name or explicit category field.
    """
    combined = f"{product_name} {category or ''}".lower()
    for cat_key, entry in CATEGORY_ANCHORS.items():
        for kw in entry["keywords"]:
            if re.search(r'\b' + re.escape(kw) + r'\b', combined):
                return cat_key
    return None


def detect_category_conflict(
    target_category_key: Optional[str],
    candidate_text: str
) -> Tuple[bool, Optional[str], Optional[str]]:
    """
    Detects if candidate text contains a contradictory category noun that conflicts with target product.
    Returns (is_conflict, target_category_key, conflicting_noun_found).
    """
    if not target_category_key or target_category_key not in CATEGORY_ANCHORS or not candidate_text:
        return False, None, None

    entry = CATEGORY_ANCHORS[target_category_key]
    conflicts = entry.get("conflicts", [])
    target_kws = entry.get("keywords", [])
    cand_lower = candidate_text.lower()

    # Check if candidate mentions any target keywords
    has_target_keyword = any(re.search(r'\b' + re.escape(kw) + r'\b', cand_lower) for kw in target_kws)

    # Check conflicting terms
    for term in conflicts:
        if re.search(r'\b' + re.escape(term) + r'\b', cand_lower):
            # If target keyword is completely absent or candidate is explicitly focused on the conflicting term
            if not has_target_keyword:
                return True, target_category_key, term

    return False, None, None


