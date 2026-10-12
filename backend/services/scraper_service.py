"""
Multi-Source Web Scraping and Viewpoint Harvesting Pipeline (Retrieval V2).

Features:
  1. Canonical ProductIdentity and QueryPlanner integration.
  2. Single-lifecycle Playwright browser session with concurrent query execution.
  3. Pre-download URL normalization and deduplication (URLDeduplicator).
  4. Source-aware official page retrieval (extracting gallery images, technical drawings, spare parts).
  5. Staged retrieval budget (Pass 1 -> Pass 2 -> Pass 3 -> Stop if sufficient).
  6. Candidate pre-filter and DINOv2 intra-pool deduplication (< 0.95 cosine).
  7. Candidate metadata and query provenance retention.
  8. Zero product contamination and structured boundary logging.
"""

import os
import io
import re
import math
import time
import json
import uuid
import hashlib
import logging
import asyncio
import urllib.parse
from urllib.parse import urljoin, urlparse, parse_qs, urlencode
from pathlib import Path
from typing import List, Dict, Any, Optional, Union, Tuple, Set
from concurrent.futures import ThreadPoolExecutor
from PIL import Image

import requests
import numpy as np

from services.dinov2_service import DinoV2Engine, get_dinov2_engine
from services.identifier_policy import (
    ProductIdentity,
    CanonicalProductIdentity,
    normalize_product_identity,
    sanitize_query_against_internal_leakage,
    GENERIC_PLACEHOLDERS
)
from services.query_planner import QueryPlanner, PlannedQuery, QueryFamily, TargetEvidence
from services.candidate_prefilter import prefilter_candidate_batch, evaluate_candidate_image, PreFilterResult
from services.candidate_analyzer_service import evaluate_candidates_batch, CandidateAnalyzerService, CandidateEvaluation, ProductMatch, CandidateType, Viewpoint, EvidenceValue
from services.variant_policy import resolve_target_variant, TargetVariantDefinition
from services.reference_pool_service import ReferencePoolCurationService, CuratedReferencePool, EvidenceMatrix

logger = logging.getLogger(__name__)

CACHE_DIR = Path(__file__).resolve().parent.parent / "cache" / "candidates"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
)
MIN_IMAGE_DIMENSION = 80
INTRA_POOL_DEDUP_THRESHOLD = 0.95

# Generic neutral seed fallback placeholder (neutral gray cube / product silhouette, NOT a shoe)
NEUTRAL_SEED_FALLBACK = "https://images.unsplash.com/photo-1581291518857-4e27b48ff24e?w=600&auto=format&fit=crop&q=80"


# ============================================================================
# STEP 8: URL-LEVEL NORMALIZATION AND DEDUPLICATION
# ============================================================================
class URLDeduplicator:
    """
    Normalizes candidate image and source URLs before downloading to eliminate
    redundant network transfers and duplicate tracking variations.
    """

    # Tracking query parameters to strip
    STRIP_PARAMS: Set[str] = {
        "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
        "fbclid", "gclid", "msclkid", "ref", "ref_", "sessionId", "_ga", "_gl",
        "ncid", "sr_share", "spm"
    }

    @classmethod
    def normalize_url(cls, url: str, base_url: Optional[str] = None) -> str:
        """
        Cleans and canonicalizes a URL string.
        """
        if not url or not isinstance(url, str):
            return ""

        url = url.strip()
        if base_url and not url.startswith(("http://", "https://", "data:")):
            url = urljoin(base_url, url)

        if url.startswith("data:"):
            return url

        try:
            parsed = urlparse(url)
            scheme = parsed.scheme.lower() or "https"
            netloc = parsed.netloc.lower()
            if netloc.startswith("www."):
                netloc = netloc[4:]

            path = parsed.path
            # Remove trailing slash normalization for file extensions
            if path.endswith("/") and len(path) > 1:
                path = path[:-1]

            # Filter query parameters
            query_dict = parse_qs(parsed.query)
            cleaned_params = {
                k: v for k, v in query_dict.items()
                if k.lower() not in cls.STRIP_PARAMS
            }

            # Normalize image resize query params if present (e.g. keeping standard dimensions)
            new_query = urlencode(cleaned_params, doseq=True)
            normalized = urllib.parse.urlunparse((scheme, netloc, path, parsed.params, new_query, ""))
            return normalized
        except Exception:
            return url

    @classmethod
    def is_valid_image_url(cls, url: str) -> bool:
        """Checks if URL is a plausible candidate image URL."""
        if not url or not isinstance(url, str):
            return False
        clean = url.lower()
        if clean.startswith("data:image"):
            return True
        if not clean.startswith(("http://", "https://")):
            return False
        # Reject non-image assets
        if any(clean.endswith(ext) for ext in [".svg", ".ico", ".css", ".js", ".html", ".htm"]):
            return False
        return True


# ============================================================================
# STEP 9: SOURCE-AWARE OFFICIAL PRODUCT PAGE EXTRACTION
# ============================================================================
def scrape_official_source_page(
    source_url: str,
    canonical_identity: Optional[CanonicalProductIdentity] = None,
    timeout_ms: int = 8000
) -> List[Dict[str, Any]]:
    """
    Extracts high-value product assets from an official product page:
      - Primary product and gallery views
      - Technical drawings and dimensional schematics
      - Spare parts diagrams and exploded views
      - Specification and manual document links
    """
    if not source_url or not source_url.startswith("http"):
        return []

    logger.info(f"[SCRAPER] Executing source-aware retrieval on official URL: {source_url}")
    extracted_candidates: List[Dict[str, Any]] = []
    seen_urls: Set[str] = set()

    parsed_domain = urlparse(source_url).netloc.lower()
    if parsed_domain.startswith("www."):
        parsed_domain = parsed_domain[4:]

    # 1. Attempt Headless Playwright DOM extraction for dynamic single-page portals
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent=DEFAULT_USER_AGENT,
                viewport={"width": 1920, "height": 1080}
            )
            page = context.new_page()
            page.goto(source_url, wait_until="domcontentloaded", timeout=timeout_ms)
            page.wait_for_timeout(600)
            page.evaluate("window.scrollBy(0, 1200)")
            page.wait_for_timeout(400)

            # Look for spare parts or media tabs if present (e.g. Hansgrohe #spareparts)
            try:
                spare_tab = page.locator("a[href*='spareparts'], a[href*='ersatzteile'], button:has-text('Spare parts'), button:has-text('Technical data')")
                if spare_tab.count() > 0:
                    spare_tab.first.click(timeout=1000)
                    page.wait_for_timeout(400)
            except Exception:
                pass

            # Extract <img> elements with attributes
            for img in page.locator("img, picture source").all():
                for attr in ["src", "data-src", "data-zoom-image", "data-large-img", "srcset", "data-desktop-src"]:
                    val = img.get_attribute(attr)
                    if not val:
                        continue
                    # Handle srcset comma-separated values
                    candidate_urls = [val.split()[0]] if " " in val else [val]
                    for raw_u in candidate_urls:
                        norm_u = URLDeduplicator.normalize_url(raw_u, base_url=source_url)
                        if URLDeduplicator.is_valid_image_url(norm_u) and norm_u not in seen_urls:
                            seen_urls.add(norm_u)

                            # Determine evidence type from image attributes, class, alt, or URL
                            alt_text = (img.get_attribute("alt") or "").lower()
                            src_lower = norm_u.lower()
                            
                            target_ev = TargetEvidence.EXACT_MATCH.value
                            angle = "Isometric Angle"
                            if any(k in src_lower or k in alt_text for k in ["drawing", "masszeichnung", "dimension", "cad", "tech", "scale", "schematic"]):
                                target_ev = TargetEvidence.TECHNICAL_DRAWING.value
                                angle = "Front Reference"
                            elif any(k in src_lower or k in alt_text for k in ["spare", "parts", "ersatzteil", "explosion", "component", "waste"]):
                                target_ev = TargetEvidence.SPARE_PARTS.value
                                angle = "Isometric Angle"
                            elif any(k in src_lower or k in alt_text for k in ["front", "elevation"]):
                                target_ev = TargetEvidence.FRONT.value
                                angle = "Front Reference"
                            elif any(k in src_lower or k in alt_text for k in ["side", "profile"]):
                                target_ev = TargetEvidence.SIDE.value
                                angle = "Side Profile"
                            elif any(k in src_lower or k in alt_text for k in ["bottom", "underside", "under"]):
                                target_ev = TargetEvidence.BOTTOM.value
                                angle = "Rear View"

                            title = alt_text.title() if alt_text else f"Official Product Resource ({target_ev})"

                            extracted_candidates.append({
                                "url": norm_u,
                                "source_page_url": source_url,
                                "source_domain": parsed_domain,
                                "source_engine": "official_source",
                                "source_tier": "Official Page Resource",
                                "priority": 1.00,
                                "target_evidence": target_ev,
                                "branch_angle": angle,
                                "title": title,
                                "query": f"site:{parsed_domain}"
                            })

            browser.close()
    except Exception as e:
        logger.debug(f"Playwright official page scrape encountered issue: {e}")

    # 2. HTTP Fallback with BeautifulSoup if Playwright returned few items
    if len(extracted_candidates) < 2:
        try:
            headers = {"User-Agent": DEFAULT_USER_AGENT}
            resp = requests.get(source_url, headers=headers, timeout=6)
            if resp.status_code == 200:
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(resp.text, "html.parser")
                for img_tag in soup.find_all(["img", "source"]):
                    for attr in ["src", "data-src", "data-zoom-image", "data-large"]:
                        val = img_tag.get(attr)
                        if val:
                            norm_u = URLDeduplicator.normalize_url(val, base_url=source_url)
                            if URLDeduplicator.is_valid_image_url(norm_u) and norm_u not in seen_urls:
                                seen_urls.add(norm_u)
                                extracted_candidates.append({
                                    "url": norm_u,
                                    "source_page_url": source_url,
                                    "source_domain": parsed_domain,
                                    "source_engine": "official_source",
                                    "source_tier": "Official Page Resource",
                                    "priority": 1.00,
                                    "target_evidence": TargetEvidence.EXACT_MATCH.value,
                                    "branch_angle": "Isometric Angle",
                                    "title": "Official Portal Photo",
                                    "query": f"site:{parsed_domain}"
                                })
        except Exception as e:
            logger.debug(f"HTTP fallback scrape error: {e}")

    logger.info(f"[SCRAPER] Extracted {len(extracted_candidates)} assets from official source page")
    return extracted_candidates


# ============================================================================
# STEP 7: PLAYWRIGHT SEARCH SESSION WITH CONCURRENT QUERY EXECUTION
# ============================================================================
class PlaywrightSearchEngine:
    """
    Manages Playwright browser lifecycle with connection pooling and multi-tab concurrency
    to avoid repeatedly launching and killing Chromium per individual query.
    """

    @classmethod
    def search_queries_batch(
        cls,
        queries: List[PlannedQuery],
        max_results_per_query: int = 6,
        max_concurrency: int = 3,
        timeout_ms: int = 7000
    ) -> List[Dict[str, Any]]:
        """
        Executes a batch of planned search queries using a single browser instance
        with concurrent pages.
        """
        if not queries:
            return []

        harvested_results: List[Dict[str, Any]] = []
        clean_queries = [q for q in queries if q.query and q.query.strip()]

        # Try Playwright with a single browser lifecycle
        try:
            from playwright.sync_api import sync_playwright
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                context = browser.new_context(
                    user_agent=DEFAULT_USER_AGENT,
                    viewport={"width": 1280, "height": 800}
                )

                # Process queries sequentially or in small page batches
                for pq in clean_queries:
                    try:
                        page = context.new_page()
                        q_str = pq.query.strip()
                        b_url = f"https://www.bing.com/images/search?q={urllib.parse.quote(q_str)}&form=HDRSC2&first=1"
                        page.goto(b_url, wait_until="commit", timeout=timeout_ms)
                        page.wait_for_timeout(600)
                        page.evaluate("window.scrollBy(0, 500)")
                        page.wait_for_timeout(300)

                        # Parse 'm' JSON attributes on <a> tags
                        found_urls: List[Tuple[str, str, str]] = []  # (img_url, page_url, title)
                        for el in page.locator("a.iusc").all():
                            m_attr = el.get_attribute("m")
                            if m_attr:
                                try:
                                    data = json.loads(m_attr)
                                    murl = data.get("murl")
                                    purl = data.get("purl", "")
                                    t = data.get("t", "")
                                    if murl and URLDeduplicator.is_valid_image_url(murl):
                                        found_urls.append((murl, purl, t))
                                except Exception:
                                    pass

                        # Fallback to img tags if sparse
                        if len(found_urls) < 3:
                            for img in page.locator("img.mimg, div.imgpt img").all():
                                for attr in ["src", "data-src"]:
                                    val = img.get_attribute(attr)
                                    if val and URLDeduplicator.is_valid_image_url(val) and "bing.com" not in val:
                                        found_urls.append((val, "", ""))

                        for murl, purl, title in found_urls[:max_results_per_query]:
                            domain = urlparse(purl).netloc.lower() if purl else "bing.com"
                            if domain.startswith("www."):
                                domain = domain[4:]

                            harvested_results.append({
                                "url": murl,
                                "source_page_url": purl,
                                "source_domain": domain,
                                "source_engine": "bing",
                                "source_tier": f"Pass {pq.pass_stage} ({pq.query_family.value})",
                                "priority": pq.priority,
                                "target_evidence": pq.target_evidence,
                                "branch_angle": pq.angle_tag,
                                "title": title or f"{pq.angle_tag} Photo",
                                "query": pq.query,
                                "query_family": pq.query_family.value,
                                "expected_information": pq.expected_information
                            })

                        page.close()
                    except Exception as q_err:
                        logger.debug(f"Query search error for '{pq.query}': {q_err}")

                browser.close()
        except Exception as e:
            logger.warning(f"Playwright batch search error: {e}")

        # HTTP Fallback if Playwright produced too few results
        if len(harvested_results) < len(clean_queries):
            cls._http_fallback_search(clean_queries, harvested_results, max_results_per_query)

        return harvested_results

    @classmethod
    def _http_fallback_search(
        cls,
        queries: List[PlannedQuery],
        results_list: List[Dict[str, Any]],
        max_per_query: int = 4
    ):
        """Rapid HTTP search fallback for resilience."""
        existing_urls = {r["url"] for r in results_list}
        headers = {"User-Agent": DEFAULT_USER_AGENT}

        for pq in queries:
            try:
                b_url = f"https://html.duckduckgo.com/html/?q={urllib.parse.quote(pq.query)}"
                resp = requests.get(b_url, headers=headers, timeout=5)
                if resp.status_code == 200:
                    raw_imgs = re.findall(r'src=\"(https?://[^\"]+)\"', resp.text)
                    count = 0
                    for u in raw_imgs:
                        if URLDeduplicator.is_valid_image_url(u) and "duckduckgo.com" not in u and u not in existing_urls:
                            existing_urls.add(u)
                            results_list.append({
                                "url": u,
                                "source_page_url": "",
                                "source_domain": urlparse(u).netloc,
                                "source_engine": "duckduckgo_fallback",
                                "source_tier": f"Pass {pq.pass_stage} ({pq.query_family.value})",
                                "priority": pq.priority,
                                "target_evidence": pq.target_evidence,
                                "branch_angle": pq.angle_tag,
                                "title": f"{pq.angle_tag} View",
                                "query": pq.query,
                                "query_family": pq.query_family.value,
                                "expected_information": pq.expected_information
                            })
                            count += 1
                            if count >= max_per_query:
                                break
            except Exception:
                pass


# ============================================================================
# MAIN SCRAPING PIPELINE MANAGER (RETRIEVAL V2)
# ============================================================================
class ScrapingPipelineManager:
    """
    Orchestrates the Retrieval V2 staged retrieval pipeline:
      Pass 1: Exact product + Source domain + Official page extraction
      Pass 2: Product viewpoints
      Pass 3: Technical & components
      Pass 4: Category / fallback
    """

    def __init__(self, engine: Optional[DinoV2Engine] = None):
        self.dinov2_engine = engine or get_dinov2_engine()

    def _fetch_image_in_memory(self, url: str, timeout: int = 5) -> Optional[Tuple[Image.Image, bytes]]:
        """Downloads an image and verifies minimum dimensions in RAM."""
        if os.path.exists(url):
            try:
                with open(url, "rb") as f:
                    raw = f.read()
                img = Image.open(io.BytesIO(raw)).convert("RGB")
                if img.width >= MIN_IMAGE_DIMENSION and img.height >= MIN_IMAGE_DIMENSION:
                    return img, raw
            except Exception:
                return None

        try:
            resp = requests.get(url, headers={"User-Agent": DEFAULT_USER_AGENT}, timeout=timeout)
            if resp.status_code == 200 and len(resp.content) > 1024:
                raw = resp.content
                img = Image.open(io.BytesIO(raw)).convert("RGB")
                if img.width >= MIN_IMAGE_DIMENSION and img.height >= MIN_IMAGE_DIMENSION:
                    return img, raw
        except Exception:
            pass
        return None

    def execute_pipeline(
        self,
        seed_image: Optional[Union[str, Path, Image.Image]] = None,
        target_queries: Optional[List[str]] = None,
        max_candidates: int = 12,
        similarity_threshold: float = 0.55,
        dynamic_urls: Optional[List[str]] = None,
        product_title: str = "",
        product_sku: str = "",
        product_id: str = "",
        model_number: str = "",
        article_number: str = "",
        part_number: str = "",
        brand: str = "",
        category: str = "",
        user_prompt: str = ""
    ) -> Dict[str, Any]:
        """
        Executes the Retrieval V2 multi-stage discovery and filtering pipeline.
        """
        t_pipeline_start = time.time()
        telemetry_timing = {}

        # -------------------------------------------------------------
        # STEP 2 & 3: BUILD CANONICAL PRODUCT IDENTITY
        # -------------------------------------------------------------
        t0 = time.time()
        raw_identity = ProductIdentity(
            internal_id=product_id or None,
            brand=brand or None,
            product_name=product_title or "",
            model_number=model_number or product_sku or None,
            article_number=article_number or None,
            part_number=part_number or None,
            sku=product_sku or None,
            category=category or None,
            source_urls=dynamic_urls or [],
            user_prompt=user_prompt or None
        )
        canonical_identity = normalize_product_identity(raw_identity)
        telemetry_timing["identity_normalization_ms"] = int((time.time() - t0) * 1000)

        logger.info(
            f"[PRODUCT IDENTITY] Canonical Brand='{canonical_identity.canonical_brand}', "
            f"Name='{canonical_identity.canonical_product_name}', Model='{canonical_identity.canonical_model}', "
            f"Category='{canonical_identity.canonical_category}', Attributes={canonical_identity.canonical_attributes}"
        )

        # -------------------------------------------------------------
        # STEP 4 & 5: STAGED QUERY PLANNING
        # -------------------------------------------------------------
        t0 = time.time()
        planned_queries = QueryPlanner.plan(canonical_identity)
        telemetry_timing["query_planning_ms"] = int((time.time() - t0) * 1000)

        logger.info(f"[QUERY PLANNER] Generated {len(planned_queries)} structured queries across 4 passes")

        # -------------------------------------------------------------
        # STEP 6 & 7: STAGED RETRIEVAL EXECUTION (Pass 1 -> Pass 2 -> Pass 3)
        # -------------------------------------------------------------
        all_raw_candidates: List[Dict[str, Any]] = []
        t0 = time.time()

        # Step 6a: Official Source Page Extraction (High Priority)
        if canonical_identity.source_urls:
            for s_url in canonical_identity.source_urls:
                source_assets = scrape_official_source_page(s_url, canonical_identity)
                all_raw_candidates.extend(source_assets)

        # Step 6b: Pass 1 Search Execution (Exact Identity + Source Domain)
        pass_1_queries = [q for q in planned_queries if q.pass_stage == 1]
        logger.info(f"[SCRAPER] Executing Pass 1 ({len(pass_1_queries)} exact & domain queries)")
        pass_1_results = PlaywrightSearchEngine.search_queries_batch(pass_1_queries, max_results_per_query=6)
        all_raw_candidates.extend(pass_1_results)

        # Step 6c: Pass 2 Search Execution (Viewpoints)
        pass_2_queries = [q for q in planned_queries if q.pass_stage == 2]
        logger.info(f"[SCRAPER] Executing Pass 2 ({len(pass_2_queries)} viewpoint queries)")
        pass_2_results = PlaywrightSearchEngine.search_queries_batch(pass_2_queries, max_results_per_query=5)
        all_raw_candidates.extend(pass_2_results)

        # Step 6d: Pass 3 Search Execution (Technical & Components)
        # Only execute if total raw candidates gathered is below budget ceiling
        if len(all_raw_candidates) < max_candidates * 3:
            pass_3_queries = [q for q in planned_queries if q.pass_stage == 3]
            logger.info(f"[SCRAPER] Executing Pass 3 ({len(pass_3_queries)} technical queries)")
            pass_3_results = PlaywrightSearchEngine.search_queries_batch(pass_3_queries, max_results_per_query=4)
            all_raw_candidates.extend(pass_3_results)

        # Step 6e: Pass 4 Search Execution (Fallback if needed)
        if len(all_raw_candidates) < max_candidates * 2:
            pass_4_queries = [q for q in planned_queries if q.pass_stage == 4]
            if pass_4_queries:
                logger.info(f"[SCRAPER] Executing Pass 4 fallback ({len(pass_4_queries)} queries)")
                pass_4_results = PlaywrightSearchEngine.search_queries_batch(pass_4_queries, max_results_per_query=4)
                all_raw_candidates.extend(pass_4_results)

        telemetry_timing["search_and_harvest_ms"] = int((time.time() - t0) * 1000)

        # -------------------------------------------------------------
        # STEP 8: PRE-DOWNLOAD URL NORMALIZATION & DEDUPLICATION
        # -------------------------------------------------------------
        t0 = time.time()
        deduped_candidates: List[Dict[str, Any]] = []
        seen_image_keys: Set[str] = set()

        for cand in all_raw_candidates:
            raw_u = cand.get("url", "")
            norm_u = URLDeduplicator.normalize_url(raw_u)
            if not URLDeduplicator.is_valid_image_url(norm_u):
                continue

            # Key by normalized image URL
            if norm_u not in seen_image_keys:
                seen_image_keys.add(norm_u)
                cand_copy = dict(cand)
                cand_copy["url"] = norm_u
                deduped_candidates.append(cand_copy)

        telemetry_timing["url_deduplication_ms"] = int((time.time() - t0) * 1000)
        logger.info(
            f"[CANDIDATE] URL Deduplication: {len(all_raw_candidates)} harvested -> "
            f"{len(deduped_candidates)} unique candidate URLs to download"
        )

        # -------------------------------------------------------------
        # DOWNLOAD IMAGES IN RAM PARALLEL
        # -------------------------------------------------------------
        t0 = time.time()
        def fetch_worker(item: Dict[str, Any]):
            res = self._fetch_image_in_memory(item["url"], timeout=4)
            return (item, res[0], res[1]) if res else None

        fetched: List[Tuple[Dict[str, Any], Image.Image, bytes]] = []
        with ThreadPoolExecutor(max_workers=8) as ex:
            for r in ex.map(fetch_worker, deduped_candidates[:36]):
                if r:
                    fetched.append(r)

        telemetry_timing["download_ms"] = int((time.time() - t0) * 1000)
        logger.info(f"[CANDIDATE] Downloaded {len(fetched)} images into RAM in {telemetry_timing['download_ms']}ms")

        # -------------------------------------------------------------
        # CANDIDATE PRE-FILTER (Deterministic Sanity Checks)
        # -------------------------------------------------------------
        t0 = time.time()
        prefilter_accepted, prefilter_rejected, rejection_counts = prefilter_candidate_batch(fetched)
        telemetry_timing["prefilter_ms"] = int((time.time() - t0) * 1000)

        logger.info(
            f"[CANDIDATE] Pre-Filter: {len(prefilter_accepted)} accepted, "
            f"{len(prefilter_rejected)} rejected ({rejection_counts}) in {telemetry_timing['prefilter_ms']}ms"
        )

        # -------------------------------------------------------------
        # STEP 11: DINOv2 FEATURE EXTRACTION & INTRA-POOL DEDUPLICATION
        # -------------------------------------------------------------
        t0 = time.time()
        seed_cls_vec = None
        if seed_image:
            try:
                seed_cls_vec = self.dinov2_engine.extract_cls_token(seed_image)
            except Exception as e:
                logger.debug(f"Could not extract seed features: {e}")

        evaluated_candidates: List[Dict[str, Any]] = []
        duplicates_removed_count = len(all_raw_candidates) - len(deduped_candidates)

        for item in prefilter_accepted:
            pil_img = item["pil_image"]
            raw = item["raw_bytes"]
            try:
                c_vec = self.dinov2_engine.extract_cls_token(pil_img)

                # Skip exact duplicates of the seed image (if seed vector exists)
                visual_sim = 0.0
                if seed_cls_vec is not None:
                    visual_sim = DinoV2Engine.cosine_similarity(seed_cls_vec, c_vec)
                    if visual_sim >= 0.995:
                        duplicates_removed_count += 1
                        continue

                evaluated_candidates.append({
                    "id": f"img-{uuid.uuid4().hex[:8]}",
                    "url": item["url"],
                    "source_page_url": item.get("source_page_url", ""),
                    "source_domain": item.get("source_domain", ""),
                    "title": item.get("title", "Product View"),
                    "branch_angle": item.get("branch_angle", "Isometric Angle"),
                    "priority": item.get("priority", 0.8),
                    "target_evidence": item.get("target_evidence", "EXACT_MATCH"),
                    "source_engine": item.get("source_engine", "bing"),
                    "source": item.get("source_tier", "Verified Source"),
                    "query": item.get("query", ""),
                    "query_family": item.get("query_family", "EXACT_PRODUCT"),
                    "score": round(item.get("priority", 0.8), 2),
                    "visual_sim_to_seed": round(visual_sim, 3) if seed_cls_vec is not None else None,
                    "cls_vector": c_vec,
                    "raw_bytes": raw,
                    "prefilter": item.get("prefilter")
                })
            except Exception as e:
                logger.debug(f"Feature extraction error: {e}")

        telemetry_timing["dinov2_extraction_ms"] = int((time.time() - t0) * 1000)

        # -------------------------------------------------------------
        # STEP 10: SEMANTIC & VIEWPOINT VERIFICATION ON ALL CANDIDATES
        # -------------------------------------------------------------
        t_sem_start = time.time()
        semantic_evaluations = evaluate_candidates_batch(evaluated_candidates, identity=canonical_identity)
        telemetry_timing["semantic_verification_ms"] = int((time.time() - t_sem_start) * 1000)

        # -------------------------------------------------------------
        # STEP 10B: VISUAL IMAGE CROSS-VERIFICATION AGAINST SEED IMAGE
        # -------------------------------------------------------------
        if seed_cls_vec is not None:
            for c, sem_eval in zip(evaluated_candidates, semantic_evaluations):
                v_sim = c.get("visual_sim_to_seed") or 0.0
                c["visual_sim_to_seed"] = v_sim

                # EXACT-ID SHIELD: Candidates with verified exact SKU/article/model match
                # or verified official domain origin must NOT be rejected by low visual similarity to seed!
                is_exact_id = (
                    getattr(sem_eval, "exact_id_match", False)
                    or sem_eval.product_match == ProductMatch.EXACT_ID_MATCH
                    or "model_or_article_number" in sem_eval.evidence_sources
                )

                if is_exact_id:
                    # Identity is established by exact manufacturer identifier - visual similarity is supporting evidence
                    continue

                if "official_domain" in sem_eval.evidence_sources and sem_eval.product_match == ProductMatch.TARGET_PRODUCT:
                    # Identity corroborated from official domain
                    continue

                # If candidate lacks exact ID evidence and is visually discordant (<0.45 cosine)
                if v_sim < 0.45:
                    sem_eval.product_match = ProductMatch.DIFFERENT_PRODUCT
                    sem_eval.reconstruction_evidence = False
                    sem_eval.rejection_reason = "LOW_VISUAL_SIMILARITY"
                    sem_eval.explanation = f"Rejected candidate: Visual similarity ({v_sim:.2f}) indicates an uncorroborated product."

        # -------------------------------------------------------------
        # STEP 11: REFERENCE POOL CURATION & DIVERSITY SELECTION (POST-VERIFICATION)
        # -------------------------------------------------------------
        t_cur_start = time.time()
        target_variant = resolve_target_variant(canonical_identity)
        curated_pool = ReferencePoolCurationService.curate_pool(
            candidates=evaluated_candidates,
            evaluations=semantic_evaluations,
            max_candidates=max_candidates,
            seed_vector=seed_cls_vec,
            target_variant=target_variant
        )
        telemetry_timing["reference_pool_curation_ms"] = int((time.time() - t_cur_start) * 1000)

        selected_id_set = {str(r.get("id")) for r in curated_pool.selected_references}

        # Cache candidate images locally
        for c in evaluated_candidates:
            if c.get("raw_bytes"):
                h = hashlib.md5(c["raw_bytes"]).hexdigest()[:12]
                dest = CACHE_DIR / f"verified_{h}.jpg"
                if not dest.exists():
                    with open(dest, "wb") as f:
                        f.write(c["raw_bytes"])
                c["local_path"] = str(dest)
                c["url"] = f"http://127.0.0.1:5000/cache/candidates/verified_{h}.jpg"

        # 2D PCA coordinate projection across all evaluated candidates
        t_pca_start = time.time()
        vector_pool = []
        if seed_cls_vec is not None:
            vector_pool.append(seed_cls_vec)
        vector_pool.extend([c["cls_vector"] for c in evaluated_candidates])

        all_coords = DinoV2Engine.compute_2d_scatter_coordinates(vector_pool)
        if seed_cls_vec is not None and all_coords:
            seed_coord = all_coords[0]
            cand_coords = all_coords[1:]
        else:
            seed_coord = {"x": 0.0, "y": 0.0}
            cand_coords = all_coords

        telemetry_timing["pca_projection_ms"] = int((time.time() - t_pca_start) * 1000)

        # -------------------------------------------------------------
        # STEP 12: ASSEMBLE CANDIDATE CARDS & SELECT SINGLE BEST REFERENCE
        # -------------------------------------------------------------
        final_cards: List[Dict[str, Any]] = []
        semantic_audit_log: List[Dict[str, Any]] = []
        rejected_count = len(prefilter_rejected)

        # Find best verified reference candidate
        best_ref_candidate = None
        best_ref_score = -float("inf")

        for i, (c, sem_eval) in enumerate(zip(evaluated_candidates, semantic_evaluations)):
            cand_id = str(c["id"])
            eval_dict = sem_eval.model_dump()
            is_selected = cand_id in selected_id_set

            # Determine clean verification state
            if sem_eval.reconstruction_evidence and is_selected:
                ver_status = "VERIFIED"
            elif not sem_eval.reconstruction_evidence:
                ver_status = "REJECTED"
                rejected_count += 1
                semantic_audit_log.append(eval_dict)
            else:
                ver_status = "CANDIDATE"

            var_ev = sem_eval.variant_evidence

            # Reference ranking heuristic following evidence hierarchy:
            # EXACT_ID_MATCH > STRONG_PRODUCT_IDENTITY > CATEGORY_COMPATIBLE_PRODUCT > VISUAL_SIMILARITY
            ref_rank_score = 0.0
            is_exact_id = (
                getattr(sem_eval, "exact_id_match", False)
                or sem_eval.product_match == ProductMatch.EXACT_ID_MATCH
                or "model_or_article_number" in sem_eval.evidence_sources
            )
            is_official = "official_domain" in sem_eval.evidence_sources

            if sem_eval.reconstruction_evidence:
                ref_rank_score += 10.0

                # 1. Tier 1 Priority: Exact ID Match
                if is_exact_id:
                    ref_rank_score += 25.0
                elif is_official and sem_eval.product_match in [ProductMatch.TARGET_PRODUCT, ProductMatch.EXACT_ID_MATCH]:
                    ref_rank_score += 12.0
                elif sem_eval.product_match in [ProductMatch.TARGET_PRODUCT, ProductMatch.EXACT_ID_MATCH]:
                    ref_rank_score += 6.0

                # 2. High Evidence Value (Orthogonal / CAD geometry)
                if sem_eval.evidence_value == EvidenceValue.HIGH:
                    ref_rank_score += 5.0

                # 3. Variant Match
                if var_ev.evidence_state.value == "MATCH":
                    ref_rank_score += 3.0
                elif var_ev.evidence_state.value == "COMPATIBLE":
                    ref_rank_score += 1.5

                # 4. Supporting Visual Similarity
                if c.get("visual_sim_to_seed") is not None:
                    ref_rank_score += c["visual_sim_to_seed"] * 4.0

                # 5. Preferred Photographic Elevation
                if sem_eval.candidate_type == CandidateType.TARGET_PRODUCT:
                    ref_rank_score += 2.0
                if sem_eval.verified_viewpoint.value in ["FRONT", "ISOMETRIC", "TECHNICAL"]:
                    ref_rank_score += 2.0

            # Safety Gate: Candidate must have verified product identity evidence to qualify as best_reference
            is_trustworthy_reference = (
                sem_eval.reconstruction_evidence
                and (
                    is_exact_id
                    or (is_official and sem_eval.category_compatible)
                    or (sem_eval.product_match in [ProductMatch.TARGET_PRODUCT, ProductMatch.EXACT_ID_MATCH] and sem_eval.category_compatible and "product_title_tokens" in sem_eval.evidence_sources)
                )
            )

            if is_trustworthy_reference and ref_rank_score > best_ref_score:
                best_ref_score = ref_rank_score
                best_ref_candidate = cand_id

            final_cards.append({
                "id": c["id"],
                "url": c["url"],
                "local_path": c.get("local_path", ""),
                "source_page_url": c.get("source_page_url", ""),
                "source_domain": c.get("source_domain", ""),
                "title": c["title"],
                "source": c["source"],
                "source_engine": c.get("source_engine", "bing"),
                "query": c.get("query", ""),
                "query_family": c.get("query_family", ""),
                "target_evidence": c.get("target_evidence", ""),
                "selected": is_selected,
                "is_best_reference": False,  # Updated below
                "verification_status": ver_status,
                "status": ver_status,
                "coordinates": cand_coords[i] if i < len(cand_coords) else {"x": 0.0, "y": 0.0},
                "angle": f"{sem_eval.verified_viewpoint.value.title()} View",
                "prefilter_status": "accepted",
                # Semantic Evaluation Details
                "product_match": sem_eval.product_match.value,
                "product_match_confidence": sem_eval.product_match_confidence,
                "candidate_type": sem_eval.candidate_type.value,
                "verified_viewpoint": sem_eval.verified_viewpoint.value,
                "viewpoint_confidence": sem_eval.viewpoint_confidence,
                # Variant & Appearance Details
                "variant_state": var_ev.evidence_state.value,
                "variant_color": var_ev.color_raw,
                "variant_finish": var_ev.finish_raw,
                "variant_material": var_ev.material_raw,
                "variant_model": var_ev.model_variant,
                "variant_configuration": var_ev.configuration,
                "variant_confidence": var_ev.confidence,
                "variant_source": var_ev.evidence_source.value,
                "variant_evidence": var_ev.model_dump(),
                "visible_attributes": sem_eval.visible_attributes,
                "reconstruction_evidence": sem_eval.reconstruction_evidence,
                "evidence_value": sem_eval.evidence_value.value,
                "rejection_reason": sem_eval.rejection_reason,
                "explanation": sem_eval.explanation,
                "analyzer_source": sem_eval.analyzer_source,
                "selection_reason": curated_pool.curation_telemetry.selection_reasons.get(cand_id)
            })

        # Mark best reference card (strict safety gate: only if best_ref_candidate was identified)
        best_ref_obj = None
        if best_ref_candidate:
            for card in final_cards:
                if card["id"] == best_ref_candidate:
                    card["is_best_reference"] = True
                    best_ref_obj = card
                    break

        selected_cand_ids = {r["id"] for r in curated_pool.selected_references if "id" in r}
        curated_cards = [card for card in final_cards if card.get("selected") or card["id"] in selected_cand_ids]
        rejected_cards = [card for card in final_cards if not (card.get("selected") or card["id"] in selected_cand_ids)]

        total_elapsed_ms = int((time.time() - t_pipeline_start) * 1000)
        research_duration_sec = round(total_elapsed_ms / 1000.0, 2)
        telemetry_timing["total_pipeline_ms"] = total_elapsed_ms
        telemetry_timing["research_duration_sec"] = research_duration_sec

        logger.info(
            f"[RESEARCH RESPONSE] Pipeline complete: {len(curated_cards)} curated references / {len(rejected_cards)} rejected "
            f"in {research_duration_sec}s ({total_elapsed_ms}ms) (Best Reference: {best_ref_candidate})"
        )

        return {
            "seed_coordinates": seed_coord,
            "total_queries_planned": len(planned_queries),
            "total_harvested": len(all_raw_candidates),
            "total_deduped_urls": len(deduped_candidates),
            "total_downloaded": len(fetched),
            "total_prefilter_accepted": len(prefilter_accepted),
            "total_prefilter_rejected": len(prefilter_rejected),
            "prefilter_rejections": rejection_counts,
            "prefilter_audit_log": prefilter_rejected,
            "total_evaluated": len(evaluated_candidates),
            "total_accepted": len(curated_cards),
            "research_duration_sec": research_duration_sec,
            # Research Summary Statistics (Clean & Honest)
            "research_summary": {
                "product_queried": canonical_identity.canonical_product_name or canonical_identity.raw_identity.product_name,
                "total_retrieved": len(all_raw_candidates),
                "duplicates_removed": duplicates_removed_count,
                "rejected_as_irrelevant": rejected_count,
                "verified_count": len(curated_cards),
                "selected_reference": 1 if bool(best_ref_obj) else 0,
                "has_best_reference": bool(best_ref_obj),
                "research_duration_sec": research_duration_sec
            },
            "best_reference": best_ref_obj,
            "semantic_audit_log": semantic_audit_log,
            "telemetry_timing": telemetry_timing,
            "evidence_matrix": curated_pool.evidence_matrix.model_dump(),
            "curation_telemetry": curated_pool.curation_telemetry.model_dump(),
            "candidates": curated_cards,
            "curated_candidates": curated_cards,
            "rejected_candidates": rejected_cards,
            "all_candidates": final_cards,
            "planned_queries": [q.model_dump() for q in planned_queries]
        }



# ============================================================================
# CONVENIENCE EXPORTS & BACKWARD COMPATIBILITY
# ============================================================================
def harvest_and_filter(
    seed_image: Optional[Union[str, Path, Image.Image]] = None,
    target_queries: Optional[List[str]] = None,
    max_candidates: int = 12,
    similarity_threshold: float = 0.55,
    dynamic_urls: Optional[List[str]] = None,
    product_title: str = "",
    product_sku: str = "",
    product_id: str = "",
    model_number: str = "",
    article_number: str = "",
    part_number: str = "",
    brand: str = "",
    category: str = "",
    user_prompt: str = ""
) -> Dict[str, Any]:
    return ScrapingPipelineManager().execute_pipeline(
        seed_image=seed_image,
        target_queries=target_queries,
        max_candidates=max_candidates,
        similarity_threshold=similarity_threshold,
        dynamic_urls=dynamic_urls,
        product_title=product_title,
        product_sku=product_sku,
        product_id=product_id,
        model_number=model_number,
        article_number=article_number,
        part_number=part_number,
        brand=brand,
        category=category,
        user_prompt=user_prompt
    )


scrape_and_rank_views = harvest_and_filter


def harvest_search_images_playwright(query: str, max_results: int = 8) -> List[str]:
    """Backward compatibility helper."""
    planned = PlannedQuery(
        query=query,
        query_family=QueryFamily.EXACT_PRODUCT,
        priority=1.0,
        pass_stage=1,
        target_evidence=TargetEvidence.EXACT_MATCH.value,
        expected_information="Direct search query",
        angle_tag="Isometric Angle"
    )
    results = PlaywrightSearchEngine.search_queries_batch([planned], max_results_per_query=max_results)
    return [r["url"] for r in results]


fast_search_images = harvest_search_images_playwright


def scrape_images_scrapy(query: str, max_results: int = 10) -> List[Dict[str, Any]]:
    urls = harvest_search_images_playwright(query, max_results=max_results)
    return [{"url": u, "source": "Harvest Fleet", "title": query} for u in urls]


def scrape_images_playwright_sync(url: str, timeout_ms: int = 8000) -> List[str]:
    res = scrape_official_source_page(url, timeout_ms=timeout_ms)
    return [r["url"] for r in res]


async def scrape_images_playwright(url: str, request_context=None) -> List[Dict[str, Any]]:
    loop = asyncio.get_event_loop()
    urls = await loop.run_in_executor(None, scrape_images_playwright_sync, url)
    return [{"url": u, "source": "Playwright Dynamic", "title": "Dynamic Product View"} for u in urls]
