"""
Multi-Source Web Scraping and Viewpoint Harvesting Pipeline.
Uses Playwright Headless Chromium to harvest genuine search engine image results
via Bing Image Search using a strict Metadata Priority Cascade.
Repurposes DINOv2 strictly for downstream intra-candidate deduplication
and PCA 2D scatter coordinate projection.
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
from urllib.parse import urljoin
from pathlib import Path
from typing import List, Dict, Any, Optional, Union, Tuple
from concurrent.futures import ThreadPoolExecutor
from PIL import Image

import requests
import numpy as np

from services.dinov2_service import DinoV2Engine, get_dinov2_engine
from services.triage_service import build_prioritized_search_queries

logger = logging.getLogger(__name__)

CACHE_DIR = Path(__file__).resolve().parent.parent / "cache" / "candidates"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
)
MIN_IMAGE_DIMENSION = 80
INTRA_POOL_DEDUP_THRESHOLD = 0.95


def harvest_search_images_playwright(query: str, max_results: int = 8) -> List[str]:
    """
    Launches headless Chromium to navigate to Bing Images, waits for real image
    DOM nodes, and extracts genuine product images via `a.iusc` (`murl`) attribute.
    """
    image_urls: List[str] = []
    clean_query = query.strip()
    if not clean_query:
        return []

    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent=DEFAULT_USER_AGENT,
                viewport={"width": 1280, "height": 800}
            )
            page = context.new_page()

            # Navigate to Bing Images with full DOM rendering
            b_url = f"https://www.bing.com/images/search?q={urllib.parse.quote(clean_query)}&form=HDRSC2&first=1"
            page.goto(b_url, wait_until="commit", timeout=8000)
            page.wait_for_timeout(800)
            page.evaluate("window.scrollBy(0, 600)")
            page.wait_for_timeout(400)

            # 1. Parse 'm' JSON attributes on <a> tags (contains direct hi-res murl)
            for el in page.locator("a.iusc").all():
                m_attr = el.get_attribute("m")
                if m_attr:
                    try:
                        data = json.loads(m_attr)
                        u = data.get("murl")
                        if u and u.startswith("http") and not any(u.lower().endswith(ext) for ext in [".svg", ".ico", ".gif"]):
                            image_urls.append(u)
                    except Exception:
                        pass

            # Fallback to direct img elements if sparse
            if len(image_urls) < 4:
                for img in page.locator("img.mimg, div.imgpt img, img").all():
                    for attr in ["src", "data-src"]:
                        val = img.get_attribute(attr)
                        if val and val.startswith("http") and "bing.com" not in val and not any(val.lower().endswith(ext) for ext in [".svg", ".ico"]):
                            image_urls.append(val)

            browser.close()
    except Exception as e:
        logger.warning(f"Playwright search error for '{clean_query}': {e}")

    # Fallback to HTTP regex if headless browser encountered an issue
    if len(image_urls) < 3:
        try:
            b_url = f"https://html.duckduckgo.com/html/?q={urllib.parse.quote(clean_query)}"
            headers = {"User-Agent": DEFAULT_USER_AGENT}
            resp = requests.get(b_url, headers=headers, timeout=6)
            if resp.status_code == 200:
                raw_imgs = re.findall(r'src=\"(https?://[^\"]+)\"', resp.text)
                for u in raw_imgs:
                    if "duckduckgo.com" not in u and not u.lower().endswith((".svg", ".ico", ".gif")):
                        image_urls.append(u)
        except Exception:
            pass

    # Deduplicate URLs
    seen = set()
    deduped = []
    for u in image_urls:
        if u not in seen:
            seen.add(u)
            deduped.append(u)
            if len(deduped) >= max_results:
                break
    return deduped


fast_search_images = harvest_search_images_playwright


def scrape_images_playwright_sync(url: str, timeout_ms: int = 9000) -> List[str]:
    """Headless Playwright worker for custom retail store pages."""
    image_urls = []
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(user_agent=DEFAULT_USER_AGENT, viewport={"width": 1920, "height": 1080})
            page = context.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
            page.wait_for_timeout(800)
            page.evaluate("window.scrollBy(0, 1500)")
            page.wait_for_timeout(600)
            
            for img in page.locator("img").all():
                for attr in ["src", "data-src", "data-desktop-src"]:
                    val = img.get_attribute(attr)
                    if val and not val.strip().startswith("data:"):
                        full_url = urljoin(url, val.strip())
                        if full_url.startswith(("http://", "https://")) and not full_url.lower().endswith((".svg", ".ico")):
                            image_urls.append(full_url)
            browser.close()
    except Exception as e:
        logger.debug(f"Playwright error for {url}: {e}")
    return list(dict.fromkeys(image_urls))


async def scrape_images_playwright(url: str, request_context=None) -> List[Dict[str, Any]]:
    """Asynchronous Playwright wrapper for direct endpoint queries."""
    loop = asyncio.get_event_loop()
    urls = await loop.run_in_executor(None, scrape_images_playwright_sync, url)
    return [{"url": u, "source": "Playwright Dynamic", "title": "Dynamic Product View"} for u in urls]


def scrape_images_scrapy(query: str, max_results: int = 10) -> List[Dict[str, Any]]:
    """Scrapy / HTTP worker wrapper."""
    urls = harvest_search_images_playwright(query, max_results=max_results)
    return [{"url": u, "source": "Harvest Fleet", "title": query} for u in urls]


class ScrapingPipelineManager:
    """
    Manages search image harvesting using a strict Metadata Priority Cascade,
    and applies DINOv2 strictly for intra-pool deduplication and PCA coordinate projection.
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
        product_title: str = "Product Asset",
        product_sku: str = "",
        product_id: str = "",
        model_number: str = "",
        category: str = ""
    ) -> Dict[str, Any]:
        """
        Executes the refactored image discovery and filtering pipeline:
        1. Generates prioritized queries via Metadata Priority Cascade (Priority 1 -> 5).
        2. Queries Priority 1 & 2 targets first before falling back down the ladder.
        3. Harvests images via Bing Image Search Playwright DOM parser.
        4. Ingests all valid candidates without seed-vector gatekeeping.
        5. Performs intra-pool deduplication using DINOv2 cosine similarity (drops >= 0.95 identical angles).
        6. Projects candidates onto 2D PCA vector space coordinates.
        7. Writes accepted candidates to local cache.
        """
        # 1. Build Metadata Prioritized Query Ladder
        effective_sku = model_number or product_sku
        effective_id = product_id or product_sku

        prioritized_ladder = build_prioritized_search_queries(
            product_id=effective_id,
            product_name=product_title,
            model_number=effective_sku,
            category=category,
            raw_queries=target_queries,
            dynamic_urls=dynamic_urls
        )

        logger.info(f"Built {len(prioritized_ladder)} prioritized queries for '{product_title}' (SKU: {effective_sku})")

        # 2. Extract Seed Vector for PCA Anchor (if provided)
        seed_cls_vec = None
        if seed_image:
            try:
                seed_cls_vec = self.dinov2_engine.extract_cls_token(seed_image)
            except Exception as e:
                logger.warning(f"Could not extract seed features: {e}")

        # 3. Harvest candidate image links (Querying Priority 1 and 2 targets first)
        all_candidates: List[Dict[str, Any]] = []
        seen_urls = set()

        # Group queries by priority tier to ensure Priority 1 & 2 are harvested first
        for q_item in prioritized_ladder:
            p_tier = q_item["priority"]
            q_str = q_item["query"]
            angle_tag = q_item["angle_tag"]
            source_desc = q_item["source_tier"]

            # Fetch up to 5 results per query
            urls = harvest_search_images_playwright(q_str, max_results=5)
            for u in urls:
                if u not in seen_urls:
                    seen_urls.add(u)
                    all_candidates.append({
                        "url": u,
                        "branch_angle": angle_tag,
                        "priority": p_tier,
                        "source": f"Bing {source_desc}",
                        "title": f"{product_title} ({angle_tag})",
                        "query": q_str
                    })

            # If we've gathered enough raw candidates from high-priority tiers, continue
            if len(all_candidates) >= max_candidates * 3:
                break

        logger.info(f"Harvested {len(all_candidates)} candidate URLs from Bing search queries")

        # 4. Fetch candidate images into RAM in parallel
        def fetch_worker(item: Dict[str, Any]):
            res = self._fetch_image_in_memory(item["url"], timeout=4)
            return (item, res[0], res[1]) if res else None

        fetched: List[Tuple[Dict[str, Any], Image.Image, bytes]] = []
        with ThreadPoolExecutor(max_workers=6) as ex:
            for r in ex.map(fetch_worker, all_candidates[:30]):
                if r:
                    fetched.append(r)

        logger.info(f"Successfully downloaded {len(fetched)} candidate images into RAM")

        # 5. DINOv2 Feature Extraction & Candidate Ingestion (NO SEED VECTOR GATEKEEPING)
        evaluated_candidates: List[Dict[str, Any]] = []
        for item, pil_img, raw in fetched:
            try:
                c_vec = self.dinov2_engine.extract_cls_token(pil_img)

                # Skip identical copies of the seed image (if seed is known)
                if seed_cls_vec is not None:
                    seed_sim = DinoV2Engine.cosine_similarity(seed_cls_vec, c_vec)
                    if seed_sim >= 0.995:
                        continue

                evaluated_candidates.append({
                    "id": f"img-{uuid.uuid4().hex[:8]}",
                    "url": item["url"],
                    "title": item["title"],
                    "branch_angle": item["branch_angle"],
                    "priority": item["priority"],
                    "source": item["source"],
                    "score": round(0.88 + (0.10 / max(1, item["priority"])), 3),
                    "cls_vector": c_vec,
                    "raw_bytes": raw
                })
            except Exception as e:
                logger.debug(f"Error extracting features for candidate {item['url']}: {e}")
                continue

        # 6. Intra-Pool Deduplication via DINOv2 (< 0.95 Cosine Similarity)
        # Distribute accepted candidates across standard view buckets
        buckets: Dict[str, List[Dict[str, Any]]] = {
            "Front Reference": [],
            "Side Profile": [],
            "Rear View": [],
            "Isometric Angle": []
        }

        for c in evaluated_candidates:
            tag = c["branch_angle"] if c["branch_angle"] in buckets else "Isometric Angle"
            buckets[tag].append(c)

        # Sort each bucket by priority tier (Priority 1 first, then 2, 3...)
        for b in buckets:
            buckets[b].sort(key=lambda x: (x["priority"], -x["score"]))

        accepted: List[Dict[str, Any]] = []
        accepted_vectors: List[np.ndarray] = []

        # Step 6a: Select the top unique candidate for each standard viewpoint bucket
        for b_name in ["Front Reference", "Side Profile", "Rear View", "Isometric Angle"]:
            for c in buckets[b_name]:
                # Intra-pool deduplication check: cosine_similarity >= 0.95 is duplicate
                is_duplicate = any(
                    DinoV2Engine.cosine_similarity(c["cls_vector"], v) >= INTRA_POOL_DEDUP_THRESHOLD
                    for v in accepted_vectors
                )
                if not is_duplicate:
                    c["angle"] = b_name
                    c["selected"] = True
                    accepted.append(c)
                    accepted_vectors.append(c["cls_vector"])
                    break

        # Step 6b: Fill remaining slots up to max_candidates while enforcing intra-pool deduplication
        all_remaining = sorted(evaluated_candidates, key=lambda x: (x["priority"], -x["score"]))
        for c in all_remaining:
            if len(accepted) >= max_candidates:
                break
            if c not in accepted:
                is_duplicate = any(
                    DinoV2Engine.cosine_similarity(c["cls_vector"], v) >= INTRA_POOL_DEDUP_THRESHOLD
                    for v in accepted_vectors
                )
                if not is_duplicate:
                    c["angle"] = c["branch_angle"]
                    c["selected"] = True
                    accepted.append(c)
                    accepted_vectors.append(c["cls_vector"])

        logger.info(f"Intra-pool deduplication complete: {len(accepted)} unique viewpoints accepted")

        # 7. Write accepted images to local candidate cache
        for c in accepted:
            if c.get("raw_bytes"):
                h = hashlib.md5(c["raw_bytes"]).hexdigest()[:12]
                dest = CACHE_DIR / f"verified_{h}.jpg"
                if not dest.exists():
                    with open(dest, "wb") as f:
                        f.write(c["raw_bytes"])
                c["local_path"] = str(dest)
                c["url"] = f"http://127.0.0.1:5000/cache/candidates/verified_{h}.jpg"

        # 8. Compute 2D PCA Coordinates for vector space visualizer
        vector_pool = []
        if seed_cls_vec is not None:
            vector_pool.append(seed_cls_vec)
        vector_pool.extend([c["cls_vector"] for c in accepted])

        all_coords = DinoV2Engine.compute_2d_scatter_coordinates(vector_pool)
        if seed_cls_vec is not None and all_coords:
            seed_coord = all_coords[0]
            cand_coords = all_coords[1:]
        else:
            seed_coord = {"x": 0.0, "y": 0.0}
            cand_coords = all_coords

        final_cards: List[Dict[str, Any]] = []
        for i, c in enumerate(accepted):
            final_cards.append({
                "id": c["id"],
                "url": c["url"],
                "title": c["title"],
                "source": c["source"],
                "score": c["score"],
                "selected": c["selected"],
                "coordinates": cand_coords[i] if i < len(cand_coords) else {"x": 0.0, "y": 0.0},
                "angle": c.get("angle", "Isometric Angle")
            })

        return {
            "seed_coordinates": seed_coord,
            "total_harvested": len(all_candidates),
            "total_evaluated": len(evaluated_candidates),
            "total_accepted": len(final_cards),
            "candidates": final_cards
        }


def harvest_and_filter(
    seed_image: Optional[Union[str, Path, Image.Image]] = None,
    target_queries: Optional[List[str]] = None,
    max_candidates: int = 12,
    similarity_threshold: float = 0.55,
    dynamic_urls: Optional[List[str]] = None,
    product_title: str = "Product Asset",
    product_sku: str = "",
    product_id: str = "",
    model_number: str = "",
    category: str = ""
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
        category=category
    )


scrape_and_rank_views = harvest_and_filter
