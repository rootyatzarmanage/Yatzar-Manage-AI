"""
Multi-Source Web Scraping and Viewpoint Harvesting Pipeline.
Uses Playwright Headless Chromium to harvest genuine search engine image results,
bypassing bot-detection and sponsored ad grids.
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
from PIL import Image

import requests
import numpy as np

from services.dinov2_service import DinoV2Engine, get_dinov2_engine

logger = logging.getLogger(__name__)

CACHE_DIR = Path(__file__).resolve().parent.parent / "cache" / "candidates"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
)
HARD_FLOOR_THRESHOLD = 0.45
MIN_IMAGE_DIMENSION = 100


def harvest_search_images_playwright(query: str, max_results: int = 8) -> List[str]:
    """
    Launches headless Chromium to navigate to Bing/Search Images, waits for real image
    DOM nodes, and extracts genuine product images without getting ad feeds.
    """
    image_urls = []
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent=DEFAULT_USER_AGENT,
                viewport={"width": 1280, "height": 800}
            )
            page = context.new_page()

            # Navigate to Search Images with full DOM rendering
            b_url = f"https://www.bing.com/images/search?q={urllib.parse.quote(query)}&form=HDRSC2&first=1"
            page.goto(b_url, wait_until="commit", timeout=8000)
            page.wait_for_timeout(900)
            page.evaluate("window.scrollBy(0, 600)")
            page.wait_for_timeout(500)

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

            # Fallback to direct img elements
            if len(image_urls) < 4:
                for img in page.locator("img.mimg, div.imgpt img, img").all():
                    for attr in ["src", "data-src"]:
                        val = img.get_attribute(attr)
                        if val and val.startswith("http") and "bing.com" not in val and not any(val.lower().endswith(ext) for ext in [".svg", ".ico"]):
                            image_urls.append(val)

            browser.close()
    except Exception as e:
        logger.warning(f"Playwright search error for '{query}': {e}")

    # Fallback to direct HTTP regex if browser encountered an issue
    if len(image_urls) < 3:
        try:
            b_url = f"https://html.duckduckgo.com/html/?q={urllib.parse.quote(query + ' product photo')}"
            headers = {"User-Agent": DEFAULT_USER_AGENT}
            resp = requests.get(b_url, headers=headers, timeout=6)
            if resp.status_code == 200:
                raw_imgs = re.findall(r'src=\"(https?://[^\"]+)\"', resp.text)
                for u in raw_imgs:
                    if "duckduckgo.com" not in u and not u.lower().endswith((".svg", ".ico")):
                        image_urls.append(u)
        except Exception:
            pass

    # Deduplicate
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
    def __init__(self, engine: Optional[DinoV2Engine] = None):
        self.dinov2_engine = engine or get_dinov2_engine()

    def _fetch_image_in_memory(self, url: str, timeout: int = 5) -> Optional[Tuple[Image.Image, bytes]]:
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

    def _cosine_similarity(self, vec1: np.ndarray, vec2: np.ndarray) -> float:
        dot = np.dot(vec1, vec2)
        n1, n2 = np.linalg.norm(vec1), np.linalg.norm(vec2)
        return float(dot / (n1 * n2)) if (n1 > 0 and n2 > 0) else 0.0

    def execute_pipeline(
        self,
        seed_image: Union[str, Path, Image.Image],
        target_queries: Optional[List[str]] = None,
        max_candidates: int = 12,
        similarity_threshold: float = 0.55,
        dynamic_urls: Optional[List[str]] = None,
        product_title: str = "Product Asset"
    ) -> Dict[str, Any]:
        # 1. Compute Seed Reference Vector
        seed_pil = self.dinov2_engine._load_image(seed_image)
        seed_features = self.dinov2_engine.extract_features(seed_pil)
        seed_cls = seed_features["cls_token"]
        seed_cls_vec = (
            seed_cls.detach().cpu().numpy().flatten()
            if hasattr(seed_cls, "detach")
            else np.array(seed_cls).flatten()
        )

        # 2. Formulate Precision Angle Queries
        clean_name = f'"{product_title.strip()}"' if not (product_title.strip().startswith('"') and product_title.strip().endswith('"')) else product_title.strip()
        angle_branches = [
            ("Front Reference", f"{clean_name} front view official product" if "fan" not in product_title.lower() else f"{clean_name} electric desk fan front view"),
            ("Side Profile", f"{clean_name} side profile angle" if "fan" not in product_title.lower() else f"{clean_name} table fan side profile blade cage"),
            ("Rear View", f"{clean_name} rear back view details" if "fan" not in product_title.lower() else f"{clean_name} oscillating desk fan rear motor housing"),
            ("Isometric Angle", f"{clean_name} 45 degree perspective" if "fan" not in product_title.lower() else f"{clean_name} electric table fan perspective view")
        ]

        if target_queries:
            for q in target_queries:
                ql = q.lower()
                tag = "Rear View" if ("rear" in ql or "back" in ql) else ("Side Profile" if ("side" in ql or "profile" in ql) else "Isometric Angle")
                angle_branches.append((tag, q))

        # 3. Harvest candidate image links
        all_candidates = []
        seen = set()

        for tag, q_str in angle_branches[:4]:
            urls = harvest_search_images_playwright(q_str, max_results=5)
            for u in urls:
                if u not in seen:
                    seen.add(u)
                    all_candidates.append({
                        "url": u,
                        "branch_angle": tag,
                        "title": f"{product_title} ({tag})"
                    })

        # 4. Fetch candidate images into RAM in parallel
        from concurrent.futures import ThreadPoolExecutor

        def fetch_worker(item: Dict[str, Any]):
            res = self._fetch_image_in_memory(item["url"], timeout=4)
            return (item, res[0], res[1]) if res else None

        fetched = []
        with ThreadPoolExecutor(max_workers=6) as ex:
            for r in ex.map(fetch_worker, all_candidates[:20]):
                if r:
                    fetched.append(r)

        # 5. DINOv2 Scoring & Rejection of Irrelevant Noise
        evaluated = []
        for item, pil_img, raw in fetched:
            try:
                cand_feat = self.dinov2_engine.extract_features(pil_img)
                cand_cls = cand_feat["cls_token"]
                c_vec = (
                    cand_cls.detach().cpu().numpy().flatten()
                    if hasattr(cand_cls, "detach")
                    else np.array(cand_cls).flatten()
                )
                sim = self.dinov2_engine.compute_similarity(seed_features, cand_feat)

                comp = round(float(sim["composite_score"]), 4)
                g_sim = round(float(sim["global_similarity"]), 4)
                p_sim = round(float(sim["patch_score"]), 4)

                # Skip identical copies of the seed image
                if g_sim >= 0.985:
                    continue

                # Hard filter: drop noise (perfumes, motorcycles, unrelated pages)
                if comp < HARD_FLOOR_THRESHOLD and p_sim < 0.55:
                    continue

                evaluated.append({
                    "id": f"img-{uuid.uuid4().hex[:8]}",
                    "url": item["url"],
                    "title": item["title"],
                    "branch_angle": item["branch_angle"],
                    "source": f"Harvest Fleet ({item['branch_angle']})",
                    "score": comp,
                    "global_similarity": g_sim,
                    "patch_score": p_sim,
                    "cls_vector": c_vec,
                    "raw_bytes": raw
                })
            except Exception:
                continue

        # 6. Diversified Angle Selection & Intra-Pool Duplicate Suppression (< 0.96)
        buckets = {"Front Reference": [], "Side Profile": [], "Rear View": [], "Isometric Angle": []}
        for c in evaluated:
            tag = c["branch_angle"] if c["branch_angle"] in buckets else "Isometric Angle"
            buckets[tag].append(c)

        for b in buckets:
            buckets[b].sort(key=lambda x: x["score"], reverse=True)

        accepted = []
        accepted_vectors = [seed_cls_vec]

        # Take the top unique match from each available angle branch
        for b_name in ["Side Profile", "Rear View", "Isometric Angle", "Front Reference"]:
            for c in buckets[b_name]:
                if not any(self._cosine_similarity(c["cls_vector"], v) >= 0.96 for v in accepted_vectors[1:]):
                    c["angle"] = b_name
                    c["selected"] = True
                    accepted.append(c)
                    accepted_vectors.append(c["cls_vector"])
                    break

        # Fill remaining slots up to max_candidates
        remaining = sorted(evaluated, key=lambda x: x["score"], reverse=True)
        for c in remaining:
            if len(accepted) >= max_candidates:
                break
            if c not in accepted:
                if not any(self._cosine_similarity(c["cls_vector"], v) >= 0.96 for v in accepted_vectors[1:]):
                    c["angle"] = c["branch_angle"]
                    c["selected"] = True
                    accepted.append(c)
                    accepted_vectors.append(c["cls_vector"])

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

        # 8. Compute 2D PCA Coordinates
        all_vecs = [seed_cls_vec] + [c["cls_vector"] for c in accepted]
        all_coords = DinoV2Engine.compute_2d_scatter_coordinates(all_vecs)
        seed_coord = all_coords[0] if all_coords else {"x": 0.0, "y": 0.0}
        cand_coords = all_coords[1:] if len(all_coords) > 1 else []

        final_cards = []
        for i, c in enumerate(accepted):
            final_cards.append({
                "id": c["id"],
                "url": c["url"],
                "title": c["title"],
                "source": c["source"],
                "score": c["score"],
                "global_similarity": c["global_similarity"],
                "patch_score": c["patch_score"],
                "selected": c["selected"],
                "coordinates": cand_coords[i] if i < len(cand_coords) else {"x": 0.0, "y": 0.0},
                "angle": c.get("angle", "Isometric Angle")
            })

        return {
            "seed_coordinates": seed_coord,
            "total_harvested": len(all_candidates),
            "total_evaluated": len(evaluated),
            "total_accepted": len(final_cards),
            "candidates": final_cards
        }


def harvest_and_filter(
    seed_image: Union[str, Path, Image.Image],
    target_queries: Optional[List[str]] = None,
    max_candidates: int = 12,
    similarity_threshold: float = 0.55,
    dynamic_urls: Optional[List[str]] = None,
    product_title: str = "Product Asset"
) -> Dict[str, Any]:
    return ScrapingPipelineManager().execute_pipeline(
        seed_image=seed_image,
        target_queries=target_queries,
        max_candidates=max_candidates,
        similarity_threshold=similarity_threshold,
        dynamic_urls=dynamic_urls,
        product_title=product_title
    )


scrape_and_rank_views = harvest_and_filter
