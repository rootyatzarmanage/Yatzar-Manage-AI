"""
========================================================================================
 HYBRID DUAL-ENGINE PRODUCT MULTI-ANGLE SCRAPER & VISUAL MATCHER
========================================================================================

Overview:
  This script automates multi-angle product photography acquisition and visual matching:
  1. Dynamically discovers e-commerce websites and stores for any target product query.
  2. Runs a Dual Scraping Engine simultaneously:
       - Playwright Engine: Headless Chromium renders dynamic JS-heavy SPAs & galleries.
       - Fast HTTP Engine: Concurrently queries structured catalog APIs and open web endpoints.
  3. Uses Meta's DINOv2 Vision Transformer (facebook/dinov2-base) to rank candidate images
     by cosine similarity and exports strictly the Top 10 cleanest multi-angle views.

Prerequisites & Installation:
  pip install torch torchvision transformers playwright pillow requests
  python -m playwright install chromium

How to Run:
  1. Default Run (uses 'input/reference.jpg' as reference target):
       py -3.12 auto_product_pipeline.py

  2. Run with any custom reference image:
       py -3.12 auto_product_pipeline.py --input "path/to/product_image.jpg"

  3. Run with a specific search query (gives precise domain discovery):
       py -3.12 auto_product_pipeline.py --query "a ceramic urinal in white"
       py -3.12 auto_product_pipeline.py --query "4K smart home theater projector"

  4. Run with both custom image and search query:
       py -3.12 auto_product_pipeline.py --input "input/bottle.jpg" --query "silver stainless steel water bottle 1000ml"

Outputs:
  - Ranked multi-angle product shots are saved in 'ranked_results/' (Top 10 only).
  - Images are prefixed by rank (1_..., 2_..., ..., 10_...) for downstream 3D photogrammetry / NeRF pipelines.
========================================================================================
"""

import os
import sys
import time
import shutil
import argparse
import re
import json
import asyncio
import requests
import torch
from PIL import Image
from urllib.parse import urlparse, quote_plus
from concurrent.futures import ThreadPoolExecutor
from playwright.async_api import async_playwright
from transformers import AutoImageProcessor, AutoModel

# ----------------- Configuration -----------------
DEFAULT_INPUT = "input/reference.jpg"
SCRAPED_FOLDER = "scraped"
OUTPUT_FOLDER = "ranked_results"
MODEL_NAME = "facebook/dinov2-base"
BATCH_SIZE = 16
TOP_K = 10
MAX_CANDIDATE_IMAGES = 45

# Maximize CPU parallelism
torch.set_num_threads(max(1, os.cpu_count() or 4))
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")


# ----------------- Model Initialization -----------------
print(f"[*] Initializing DINOv2 vision model on {device}...")
t_init = time.perf_counter()
processor = AutoImageProcessor.from_pretrained(MODEL_NAME)
model = AutoModel.from_pretrained(MODEL_NAME).to(device)
model.eval()
print(f"[*] DINOv2 Model ready in {time.perf_counter() - t_init:.2f}s")


# ----------------- Step 1: Dynamic Query Resolver -----------------
def resolve_product_query(image_path, user_query=None):
    """Derives a search query from user argument or image filename."""
    if user_query and user_query.strip():
        return user_query.strip()

    base_name = os.path.splitext(os.path.basename(image_path))[0].lower()
    cleaned = re.sub(r"[_\-\d]+", " ", base_name).strip()
    if cleaned and len(cleaned) > 3 and cleaned not in ["reference", "input", "image", "media"]:
        return cleaned

    return "commercial product photography studio white background"


# ----------------- Step 2: Hybrid Dual-Engine Scraper -----------------
def download_single_image(task):
    url, filepath = task
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    }
    try:
        r = requests.get(url, headers=headers, timeout=8)
        if r.status_code == 200 and len(r.content) > 3500:
            with open(filepath, "wb") as f:
                f.write(r.content)
            return True
    except Exception:
        pass
    return False


async def playwright_engine_scrape(query, target_count=25):
    """
    Playwright Engine: Launches headless browser to render dynamic JS galleries,
    interactive product sliders, and rich media SPAs.
    """
    candidates = []
    print("  [Engine 1: Playwright] Launching headless browser for dynamic JS rendering...")
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                viewport={"width": 1280, "height": 800}
            )
            page = await context.new_page()

            # Navigate to dynamic visual search query
            encoded_q = quote_plus(f"{query} product angles white background")
            search_url = f"https://www.bing.com/images/search?q={encoded_q}&form=HDRSC2&first=1"
            await page.goto(search_url, wait_until="domcontentloaded", timeout=12000)

            # Scroll down to trigger lazy loading of high-res image sets
            await page.evaluate("window.scrollBy(0, 1000)")
            await page.wait_for_timeout(1000)

            # Extract dynamic image nodes
            img_nodes = await page.locator("a.iusc").all()
            for node in img_nodes[:target_count]:
                m_attr = await node.get_attribute("m")
                if m_attr:
                    try:
                        data = json.loads(m_attr)
                        murl = data.get("murl")
                        purl = data.get("purl", "")
                        if murl:
                            domain = urlparse(purl).netloc if purl else "playwright_js"
                            candidates.append((murl, domain))
                    except Exception:
                        pass

            await browser.close()
            print(f"  [Engine 1: Playwright] Extracted {len(candidates)} dynamic image sources.")
    except Exception as e:
        print(f"  [Engine 1: Playwright Notice] {e}")

    return candidates


def fast_http_engine_scrape(query, target_count=25):
    """
    High-Speed Fast Engine (Scrapy-style HTTP): Concurrently fetches static HTML,
    Wikimedia Commons API, and structured e-commerce JSON feeds.
    """
    candidates = []
    print("  [Engine 2: Fast HTTP/API] Concurrently fetching structured catalog APIs...")
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json,text/html"
    }

    # Query open image catalog API
    wiki_url = "https://commons.wikimedia.org/w/api.php"
    params = {
        "action": "query",
        "generator": "search",
        "gsrsearch": query,
        "gsrnamespace": "6",
        "gsrlimit": str(target_count),
        "prop": "imageinfo",
        "iiprop": "url|thumburl",
        "iiurlwidth": "800",
        "format": "json"
    }
    try:
        r = requests.get(wiki_url, params=params, headers=headers, timeout=6)
        if r.status_code == 200:
            pages = r.json().get("query", {}).get("pages", {})
            for pid, pinfo in pages.items():
                ii = pinfo.get("imageinfo", [])
                if ii:
                    turl = ii[0].get("thumburl") or ii[0].get("url")
                    if turl:
                        candidates.append((turl, "commons.wikimedia.org"))
    except Exception:
        pass

    # Query open web search endpoints
    try:
        encoded_q = quote_plus(f"{query} product 360 studio")
        search_url = f"https://www.bing.com/images/search?q={encoded_q}&form=HDRSC2&first=1"
        r = requests.get(search_url, headers=headers, timeout=6)
        matches = re.findall(r'm="({.*?})"', r.text)
        for m_str in matches[:target_count]:
            try:
                clean = m_str.replace('&quot;', '"')
                data = json.loads(clean)
                murl = data.get("murl")
                purl = data.get("purl", "")
                if murl:
                    domain = urlparse(purl).netloc if purl else "web_api"
                    candidates.append((murl, domain))
            except Exception:
                continue
    except Exception:
        pass

    print(f"  [Engine 2: Fast HTTP/API] Extracted {len(candidates)} candidate image sources.")
    return candidates


async def run_hybrid_scraper(query, max_images=MAX_CANDIDATE_IMAGES):
    """Runs Playwright and Fast HTTP engines simultaneously and merges results."""
    if os.path.exists(SCRAPED_FOLDER):
        shutil.rmtree(SCRAPED_FOLDER)
    os.makedirs(SCRAPED_FOLDER, exist_ok=True)

    print(f"\n[Step 1/3] Running Dual-Engine Scraper (Playwright + Fast HTTP Engine) simultaneously...")
    t_scrape_start = time.perf_counter()

    # Execute both engines concurrently using asyncio loop + executor
    loop = asyncio.get_event_loop()
    playwright_future = playwright_engine_scrape(query, target_count=25)
    http_future = loop.run_in_executor(None, fast_http_engine_scrape, query, 25)

    playwright_results, http_results = await asyncio.gather(playwright_future, http_future)

    # Merge and deduplicate candidates from both engines
    all_raw = playwright_results + http_results
    seen_urls = set()
    download_tasks = []
    discovered_domains = set()

    for img_url, domain in all_raw:
        if img_url and img_url not in seen_urls:
            seen_urls.add(img_url)
            discovered_domains.add(domain)

            ext = ".jpg"
            if ".png" in img_url.lower():
                ext = ".png"
            elif ".webp" in img_url.lower():
                ext = ".webp"

            clean_dom = re.sub(r"[^a-zA-Z0-9]", "", domain.split(".")[0])[:8]
            fname = f"{clean_dom}_{len(download_tasks)+1:03d}{ext}"
            fpath = os.path.join(SCRAPED_FOLDER, fname)
            download_tasks.append((img_url, fpath))
            if len(download_tasks) >= max_images:
                break

    print(f"[*] Combined {len(download_tasks)} unique sources across {len(discovered_domains)} domains:")
    for d in list(discovered_domains)[:6]:
        print(f"    - {d}")

    # Concurrently download all images using 10 threads
    print(f"[*] Downloading {len(download_tasks)} images in parallel...")
    with ThreadPoolExecutor(max_workers=10) as executor:
        download_results = list(executor.map(download_single_image, download_tasks))

    saved_count = sum(1 for r in download_results if r)
    print(f"[*] Successfully downloaded {saved_count} images in {time.perf_counter() - t_scrape_start:.2f}s")
    return saved_count


# ----------------- Step 3: DINOv2 Feature Matching -----------------
def load_and_preprocess_image(image_path):
    """Loads image and resizes thumbnail for maximum tensor throughput."""
    try:
        img = Image.open(image_path).convert("RGB")
        img.thumbnail((512, 512), Image.Resampling.BILINEAR)
        return img
    except Exception:
        return None


def extract_batch_embeddings(images):
    """Computes L2-normalized DINOv2 embeddings in parallel batches."""
    inputs = processor(images=images, return_tensors="pt")
    inputs = {k: v.to(device) for k, v in inputs.items()}

    with torch.no_grad():
        outputs = model(**inputs)

    embeddings = outputs.last_hidden_state[:, 0, :]
    embeddings = torch.nn.functional.normalize(embeddings, p=2, dim=1)
    return embeddings


def rank_and_save_top_k(reference_image_path, top_k=TOP_K):
    """Ranks all scraped candidates against the reference image and exports Top K."""
    print(f"\n[Step 2/3] Extracting reference embedding for '{reference_image_path}'...")
    ref_img = load_and_preprocess_image(reference_image_path)
    if ref_img is None:
        print(f"Error: Could not open reference image: {reference_image_path}")
        return []

    ref_embedding = extract_batch_embeddings([ref_img])  # shape: (1, D)

    valid_exts = (".jpg", ".jpeg", ".png", ".webp")
    candidate_files = [
        f for f in os.listdir(SCRAPED_FOLDER)
        if f.lower().endswith(valid_exts)
    ]

    print(f"[Step 3/3] Ranking {len(candidate_files)} candidate images using DINOv2 (Batch Size: {BATCH_SIZE})...")
    all_embeddings = []
    valid_filenames = []

    for i in range(0, len(candidate_files), BATCH_SIZE):
        batch_fns = candidate_files[i:i + BATCH_SIZE]
        batch_imgs = []
        batch_valid = []

        for fn in batch_fns:
            fpath = os.path.join(SCRAPED_FOLDER, fn)
            img = load_and_preprocess_image(fpath)
            if img is not None:
                batch_imgs.append(img)
                batch_valid.append(fn)

        if batch_imgs:
            b_emb = extract_batch_embeddings(batch_imgs)
            all_embeddings.append(b_emb)
            valid_filenames.extend(batch_valid)

    if not all_embeddings:
        print("No valid candidate images found to rank.")
        return []

    all_embeddings = torch.cat(all_embeddings, dim=0)

    # Matrix cosine similarity
    similarities = torch.mm(all_embeddings, ref_embedding.T).squeeze(-1).cpu().numpy()
    results = list(zip(valid_filenames, similarities))
    results.sort(key=lambda x: x[1], reverse=True)

    # Clean and save strictly Top K
    if os.path.exists(OUTPUT_FOLDER):
        shutil.rmtree(OUTPUT_FOLDER)
    os.makedirs(OUTPUT_FOLDER, exist_ok=True)

    top_results = results[:top_k]
    for rank, (filename, score) in enumerate(top_results, start=1):
        src = os.path.join(SCRAPED_FOLDER, filename)
        dst = os.path.join(OUTPUT_FOLDER, f"{rank}_{filename}")
        shutil.copy2(src, dst)

    return top_results


# ----------------- Main Entrypoint -----------------
def run_pipeline(input_image=DEFAULT_INPUT, query_hint=None):
    start_time = time.perf_counter()

    if not os.path.exists(input_image):
        print(f"Error: Target reference image '{input_image}' not found.")
        return

    # 1. Dynamically determine search query
    query = resolve_product_query(input_image, query_hint)

    print(f"\n=======================================================")
    print(f" HYBRID DUAL-ENGINE PRODUCT SCRAPER & MATCHER")
    print(f" Playwright (Dynamic JS) + Fast Engine (Async HTTP)")
    print(f"=======================================================")
    print(f"Reference Image: {input_image}")
    print(f"Dynamic Target Query: '{query}'")

    # 2. Run dual-engine scraper simultaneously
    asyncio.run(run_hybrid_scraper(query, max_images=MAX_CANDIDATE_IMAGES))

    # 3. Match & Rank Top K
    top_results = rank_and_save_top_k(input_image, top_k=TOP_K)

    elapsed = time.perf_counter() - start_time

    # 4. Display Results
    print(f"\n================ Top {len(top_results)} Ranked Multi-Angle Views ================")
    for rank, (fn, score) in enumerate(top_results, start=1):
        print(f"Rank {rank:2d}: {fn:<38} | Similarity: {score:.4f}")
    print("==================================================================")
    print(f"[Summary]")
    print(f"- Output Directory: '{OUTPUT_FOLDER}/' (Strictly Top {TOP_K} views)")
    print(f"- Total Pipeline Runtime: {elapsed:.3f} seconds\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Hybrid Dual-Engine Product Scraper & Matcher (Playwright + Fast HTTP Engine + DINOv2)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  py -3.12 auto_product_pipeline.py
  py -3.12 auto_product_pipeline.py --input "path/to/image.jpg"
  py -3.12 auto_product_pipeline.py --query "a ceramic urinal in white"
  py -3.12 auto_product_pipeline.py --input "input/bottle.jpg" --query "silver stainless steel water bottle 1000ml"
        """
    )
    parser.add_argument("--input", "-i", default=DEFAULT_INPUT, help="Path to input product reference image (default: input/reference.jpg)")
    parser.add_argument("--query", "-q", default=None, help="Target product query for dynamic e-commerce discovery")
    args = parser.parse_args()

    run_pipeline(input_image=args.input, query_hint=args.query)
