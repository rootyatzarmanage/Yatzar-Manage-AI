"""
Candidate Pre-Filter Service for Web Image Retrieval.

Performs cheap, deterministic, non-destructive validation on downloaded candidate images
before expensive downstream processing (e.g. DINOv2 feature extraction, intra-pool deduplication,
and future semantic verification).

Evaluates:
  1. Image validity (unreadable, corrupted, unsupported byte payload)
  2. Minimum resolution & area (rejects tiny icons, favicons, tracking pixels)
  3. Extreme aspect ratios (rejects horizontal banners and vertical skyscraper strips)
  4. Blank / solid monochrome image detection (low pixel variance)
"""

import io
import logging
from typing import Optional, List, Dict, Any, Tuple, Union
from PIL import Image
import numpy as np
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# ============================================================================
# CONFIGURABLE DETERMINISTIC THRESHOLDS
# ============================================================================
MIN_IMAGE_WIDTH: int = 120
MIN_IMAGE_HEIGHT: int = 120
MIN_IMAGE_AREA_PIXELS: int = 20000        # e.g., ~142x142 or 120x170
MIN_FILE_SIZE_BYTES: int = 1024           # 1 KB

# Aspect ratio = width / height
# Normal portrait goods (e.g. tall bottles, fireplaces, extinguishers) can be ~1:2.5 (0.40) or 1:3 (0.33)
# Normal landscape goods (e.g. wide heat exchangers, soundbars, keyboards) can be ~2.5:1 (2.50) or 3:1 (3.00)
# Extreme banners (5:1, 8:1) and skyscrapers (1:5, 1:8) are rejected.
MAX_ASPECT_RATIO: float = 3.5             # width / height > 3.5 -> horizontal banner
MIN_ASPECT_RATIO: float = 0.28            # width / height < 0.28 (height/width > 3.57) -> skyscraper

# Pixel variance threshold to detect solid/blank placeholders (0 to 255 scale)
MIN_PIXEL_STD_DEV: float = 4.0

# Supported PIL image formats
ALLOWED_FORMATS = {"JPEG", "JPG", "PNG", "WEBP", "BMP", "TIFF", "MPO"}


class PreFilterResult(BaseModel):
    """
    Structured outcome of candidate pre-filtering.
    Preserves dimensions, format, and audit reasons without destroying candidate metadata.
    """
    accepted: bool = Field(..., description="True if image passed all deterministic sanity checks")
    rejection_reason: Optional[str] = Field(default=None, description="Primary failure code if rejected")
    quality_flags: List[str] = Field(default_factory=list, description="Descriptive quality/shape tags")
    width: int = Field(default=0, description="Image width in pixels")
    height: int = Field(default=0, description="Image height in pixels")
    aspect_ratio: float = Field(default=1.0, description="Width-to-height ratio (width / height)")
    file_size_bytes: int = Field(default=0, description="Raw image payload size in bytes")
    image_format: str = Field(default="UNKNOWN", description="Decoded image format (JPEG, PNG, etc.)")
    variance_score: float = Field(default=0.0, description="Standard deviation of grayscale pixel intensities")


def evaluate_candidate_image(
    image_input: Union[Image.Image, bytes, str],
    source_url: str = ""
) -> Tuple[PreFilterResult, Optional[Image.Image], Optional[bytes]]:
    """
    Evaluates a candidate image against deterministic pre-filter rules.

    Args:
        image_input: PIL Image instance, raw byte buffer, or local filepath
        source_url: Source URL for logging and telemetry

    Returns:
        Tuple of:
          - PreFilterResult (structured decision & audit telemetry)
          - PIL Image (converted to RGB if accepted, else None)
          - Raw bytes (if available)
    """
    flags: List[str] = []
    raw_bytes: Optional[bytes] = None
    pil_img: Optional[Image.Image] = None
    img_format = "UNKNOWN"
    file_size = 0

    # 1. Decode / Ingest image payload
    try:
        if isinstance(image_input, Image.Image):
            pil_img = image_input
            img_format = getattr(image_input, "format", "PIL_IN_MEMORY") or "PIL_IN_MEMORY"
            # Estimate or calculate byte buffer
            buf = io.BytesIO()
            pil_img.save(buf, format="JPEG")
            raw_bytes = buf.getvalue()
            file_size = len(raw_bytes)
        elif isinstance(image_input, (bytes, bytearray)):
            raw_bytes = bytes(image_input)
            file_size = len(raw_bytes)
            if file_size < MIN_FILE_SIZE_BYTES:
                return PreFilterResult(
                    accepted=False,
                    rejection_reason="file_too_small",
                    quality_flags=["tiny_payload"],
                    file_size_bytes=file_size,
                    image_format="CORRUPT"
                ), None, None

            bio = io.BytesIO(raw_bytes)
            pil_img = Image.open(bio)
            img_format = pil_img.format or "UNKNOWN"
            # Verify and reload
            pil_img.load()
        elif isinstance(image_input, str):
            # File path
            with open(image_input, "rb") as f:
                raw_bytes = f.read()
            file_size = len(raw_bytes)
            bio = io.BytesIO(raw_bytes)
            pil_img = Image.open(bio)
            img_format = pil_img.format or "UNKNOWN"
            pil_img.load()
        else:
            return PreFilterResult(
                accepted=False,
                rejection_reason="unsupported_input_type",
                quality_flags=["invalid_input"]
            ), None, None

    except Exception as e:
        logger.debug(f"Pre-filter: Image decode failed for '{source_url}': {e}")
        return PreFilterResult(
            accepted=False,
            rejection_reason="corrupted_or_unreadable",
            quality_flags=["decode_error"],
            file_size_bytes=file_size,
            image_format="CORRUPT"
        ), None, None

    if pil_img is None:
        return PreFilterResult(
            accepted=False,
            rejection_reason="unreadable_image",
            quality_flags=["null_image"]
        ), None, None

    width, height = pil_img.size
    if width <= 0 or height <= 0:
        return PreFilterResult(
            accepted=False,
            rejection_reason="invalid_dimensions",
            quality_flags=["zero_dimension"],
            width=width,
            height=height
        ), None, None

    aspect_ratio = round(width / float(height), 4)
    area = width * height

    # 2. Check Format
    norm_format = (img_format or "UNKNOWN").upper()
    if norm_format not in ALLOWED_FORMATS and "PIL" not in norm_format:
        flags.append("non_standard_format")

    # 3. Check Extreme Aspect Ratio (Banners & Skyscrapers)
    if aspect_ratio > MAX_ASPECT_RATIO:
        return PreFilterResult(
            accepted=False,
            rejection_reason="extreme_aspect_ratio_horizontal_banner",
            quality_flags=["horizontal_banner", f"ratio_{aspect_ratio}"],
            width=width,
            height=height,
            aspect_ratio=aspect_ratio,
            file_size_bytes=file_size,
            image_format=norm_format
        ), None, raw_bytes

    if aspect_ratio < MIN_ASPECT_RATIO:
        return PreFilterResult(
            accepted=False,
            rejection_reason="extreme_aspect_ratio_vertical_skyscraper",
            quality_flags=["vertical_skyscraper", f"ratio_{aspect_ratio}"],
            width=width,
            height=height,
            aspect_ratio=aspect_ratio,
            file_size_bytes=file_size,
            image_format=norm_format
        ), None, raw_bytes

    # 4. Check Minimum Dimensions & Area
    if width < MIN_IMAGE_WIDTH or height < MIN_IMAGE_HEIGHT:
        return PreFilterResult(
            accepted=False,
            rejection_reason="dimensions_below_minimum",
            quality_flags=["tiny_resolution", f"{width}x{height}"],
            width=width,
            height=height,
            aspect_ratio=aspect_ratio,
            file_size_bytes=file_size,
            image_format=norm_format
        ), None, raw_bytes

    if area < MIN_IMAGE_AREA_PIXELS:
        return PreFilterResult(
            accepted=False,
            rejection_reason="pixel_area_too_small",
            quality_flags=["low_pixel_count", f"area_{area}"],
            width=width,
            height=height,
            aspect_ratio=aspect_ratio,
            file_size_bytes=file_size,
            image_format=norm_format
        ), None, raw_bytes

    # Annotate valid non-extreme aspect ratio shapes
    if 0.95 <= aspect_ratio <= 1.05:
        flags.append("square")
    elif aspect_ratio > 1.05:
        flags.append("landscape")
    else:
        flags.append("portrait")

    if aspect_ratio >= 2.5:
        flags.append("wide_panoramic")
    elif aspect_ratio <= 0.45:
        flags.append("tall_vertical")

    # 5. Fast Low-Variance / Blank Image Check
    try:
        # Convert small thumbnail to grayscale numpy array for fast variance computation
        thumb = pil_img.resize((64, 64)).convert("L")
        arr = np.asarray(thumb, dtype=np.float32)
        std_dev = float(np.std(arr))
    except Exception:
        std_dev = 20.0

    if std_dev < MIN_PIXEL_STD_DEV:
        return PreFilterResult(
            accepted=False,
            rejection_reason="blank_or_solid_monochrome",
            quality_flags=["low_contrast", "blank_canvas"],
            width=width,
            height=height,
            aspect_ratio=aspect_ratio,
            file_size_bytes=file_size,
            image_format=norm_format,
            variance_score=round(std_dev, 2)
        ), None, raw_bytes

    # Ensure RGB conversion for downstream processing
    rgb_img = pil_img.convert("RGB") if pil_img.mode != "RGB" else pil_img

    return PreFilterResult(
        accepted=True,
        rejection_reason=None,
        quality_flags=flags,
        width=width,
        height=height,
        aspect_ratio=aspect_ratio,
        file_size_bytes=file_size,
        image_format=norm_format,
        variance_score=round(std_dev, 2)
    ), rgb_img, raw_bytes


def prefilter_candidate_batch(
    candidates_raw: List[Tuple[Dict[str, Any], Optional[Image.Image], Optional[bytes]]]
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], Dict[str, int]]:
    """
    Processes a batch of downloaded candidates through the candidate pre-filter.

    Returns:
        Tuple of:
          - accepted_candidates: List of item dicts with augmented prefilter metadata and decoded images
          - rejected_candidates: List of audit records with rejection reasons
          - rejection_breakdown: Dict mapping rejection_reason -> count
    """
    accepted_items: List[Dict[str, Any]] = []
    rejected_items: List[Dict[str, Any]] = []
    rejection_counts: Dict[str, int] = {}

    for item, pil_img, raw_bytes in candidates_raw:
        source_url = item.get("url", "")
        img_input = pil_img if pil_img is not None else raw_bytes

        if img_input is None:
            res = PreFilterResult(
                accepted=False,
                rejection_reason="download_failed_or_empty",
                quality_flags=["no_data"]
            )
            out_img = None
            out_raw = None
        else:
            res, out_img, out_raw = evaluate_candidate_image(img_input, source_url=source_url)

        audit_entry = {
            **item,
            "url": source_url,
            "title": item.get("title", ""),
            "priority": item.get("priority", 5),
            "branch_angle": item.get("branch_angle", "Isometric Angle"),
            "source": item.get("source", "Web Search"),
            "query": item.get("query", ""),
            "prefilter": res.model_dump()
        }

        if res.accepted and out_img is not None:
            accepted_item = {
                **item,
                "pil_image": out_img,
                "raw_bytes": out_raw,
                "prefilter": res.model_dump()
            }
            accepted_items.append(accepted_item)
        else:
            reason = res.rejection_reason or "unknown_rejection"
            rejection_counts[reason] = rejection_counts.get(reason, 0) + 1
            rejected_items.append(audit_entry)

    return accepted_items, rejected_items, rejection_counts
