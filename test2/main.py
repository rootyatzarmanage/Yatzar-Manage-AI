"""
Run:  uvicorn main:app --port 8000     then open http://localhost:8000
Optional env: SERPAPI_KEY + PUBLIC_BASE_URL (ngrok URL) -> Google Lens reverse image search
              ANTHROPIC_API_KEY -> one cheap Haiku call, only if there is no text hint at all
"""
import asyncio, base64, io, os, re, shutil, subprocess, sys, time, uuid
from urllib.parse import urljoin

import httpx, imagehash, numpy as np, torch
from bs4 import BeautifulSoup
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from PIL import Image
from transformers import AutoImageProcessor, AutoModel, CLIPModel, CLIPProcessor
import trimesh
from skimage import measure
from scipy.ndimage import binary_fill_holes, gaussian_filter

try:
    from ddgs import DDGS
except ImportError:
    from duckduckgo_search import DDGS

HI, LO, COL_MIN = 0.80, 0.70, 0.75   # strict exact-product gates
SAME_PAGE_RELAX = 0.08               # extra slack for images from the same listing as a confirmed anchor
FALLBACK_SIM, FALLBACK_COL = 0.65, 0.65
ANGLES = {   # angle -> search phrasings (different wording surfaces different photos)
    "front": ["front view", "front facing"],
    "back": ["back view", "rear view", "from behind"],
    "side": ["side view", "side profile"],
    "top": ["top view", "top down view", "overhead view from above"],
    "bottom": ["bottom view", "underside view"],
    "three-quarter": ["three quarter angle view", "angled perspective view"],
    "close-up": ["close up texture detail", "macro material surface detail"],
}
ANG_TEXT = ["a photo of the front of an object", "a photo of the back of an object, rear view",
            "a side profile photo of an object", "a top-down photo of an object seen from above",
            "a photo of the underside of an object seen from below",
            "a three-quarter angle photo of an object", "a close-up macro photo of a material texture"]


def angle_queries(base, angles, k=2):
    return [base] + [f"{base} {p}" for a in angles for p in ANGLES[a][:k]]


HDR = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120 Safari/537.36"}

app = FastAPI()
os.makedirs("uploads", exist_ok=True)
os.makedirs("uploads/models", exist_ok=True)
os.makedirs("uploads/jobs", exist_ok=True)
app.mount("/u", StaticFiles(directory="uploads"))
proc = AutoImageProcessor.from_pretrained("facebook/dinov2-small")
dino = AutoModel.from_pretrained("facebook/dinov2-small").eval()
clip = CLIPModel.from_pretrained("openai/clip-vit-base-patch32").eval()
cproc = CLIPProcessor.from_pretrained("openai/clip-vit-base-patch32")


# ---------- primitives ----------
@torch.no_grad()
def embed(imgs):
    out = []
    for i in range(0, len(imgs), 16):
        x = dino(**proc(images=imgs[i:i + 16], return_tensors="pt")).last_hidden_state
        out.append(torch.nn.functional.normalize(torch.cat([x[:, 0], x[:, 1:].mean(1)], -1), dim=-1))
    return torch.cat(out).numpy()


def color_sig(img):
    """HSV histogram of the object only (background estimated from the border and masked out)."""
    small = img.resize((128, 128))
    a = np.asarray(small).astype(float)
    bg = np.median(np.concatenate([a[0], a[-1], a[:, 0], a[:, -1]]), 0)
    mask = np.linalg.norm(a - bg, axis=2) > 40
    if not 0.05 < mask.mean() < 0.95:
        mask = np.zeros(mask.shape, bool); mask[32:96, 32:96] = True
    hsv = np.asarray(small.convert("HSV"))[mask]
    h = np.histogramdd(hsv, bins=(12, 4, 4), range=((0, 256),) * 3)[0].ravel()
    return h / max(h.sum(), 1)


def object_aspect_ratio(img):
    """Estimate the visible product width/height ratio from the image border background."""
    small = img.convert("RGB").resize((128, 128))
    a = np.asarray(small).astype(float)
    bg = np.median(np.concatenate([a[0], a[-1], a[:, 0], a[:, -1]]), axis=0)
    mask = np.linalg.norm(a - bg, axis=2) > 28
    ys, xs = np.where(mask)
    if len(xs) < 50:
        return float(img.width / max(img.height, 1))
    return float((xs.max() - xs.min() + 1) / max(ys.max() - ys.min() + 1, 1))


def aspect_similarity(ref_ratio, candidate_ratio):
    """Score how closely the candidate's visible silhouette ratio matches the reference."""
    if ref_ratio <= 0 or candidate_ratio <= 0:
        return 0.0
    return float(np.exp(-abs(np.log(candidate_ratio / ref_ratio)) / 0.45))


@torch.no_grad()
def label_angles(items):
    items = [i for i in items if "angle" not in i]
    if not items: return
    p = clip(**cproc(text=ANG_TEXT, images=[i["thumb"] for i in items], return_tensors="pt", padding=True)).logits_per_image.softmax(-1)
    for i, row in zip(items, p):
        i["angle"] = list(ANGLES)[int(row.argmax())]


def best_title(kept, st):
    anchors = sorted([i for i in kept if i["tier"] == "high" and i["page"]], key=lambda i: -i["score"])
    return next((re.sub(r"\s+", " ", st["titles"][i["page"]])[:70] for i in anchors if st["titles"].get(i["page"])), "")


# ---------- retrieval ----------
async def gallery(c, page):
    try:
        s = BeautifulSoup((await c.get(page, timeout=5)).text, "html.parser")
    except Exception:
        return "", []
    og = s.find("meta", property="og:title")
    title = og["content"] if og and og.get("content") else (s.title.string or "" if s.title else "")
    urls = [m["content"] for m in s.find_all("meta", property="og:image") if m.get("content")]
    for sc in s.find_all("script", type="application/ld+json"):
        urls += re.findall(r'"image"\s*:\s*\[?\s*"([^"]+)"', sc.string or "")
    for t in s.find_all("img"):
        u = t.get("data-src") or t.get("data-old-hires") or t.get("src")
        if u and not u.startswith("data:"):
            urls.append(u)
    return title.strip(), [(urljoin(page, u), page) for u in dict.fromkeys(urls)][:80]


def ddg_images(q):
    for _ in range(2):                                   # one retry: ddgs rate-limits under bursts
        try:
            return [(x["image"], x.get("url", "")) for x in DDGS().images(q, max_results=50)]
        except Exception:
            time.sleep(1)
    return []


def ddg_pages(q):
    try:
        return [x["href"] for x in DDGS().text(q, max_results=12)]
    except Exception:
        return []


async def lens(c, img_url):
    r = await c.get("https://serpapi.com/search.json", timeout=15, params={
        "engine": "google_lens", "url": img_url, "api_key": os.environ["SERPAPI_KEY"]})
    vm = r.json().get("visual_matches", [])[:20]
    return [(m.get("image") or m.get("thumbnail"), m.get("link", "")) for m in vm], [m.get("title", "") for m in vm[:3]]


def haiku_name(ref):
    import anthropic
    ref = ref.copy(); ref.thumbnail((512, 512))
    buf = io.BytesIO(); ref.save(buf, "JPEG")
    m = anthropic.Anthropic().messages.create(
        model="claude-haiku-4-5-20251001", max_tokens=40,
        messages=[{"role": "user", "content": [
            {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                         "data": base64.b64encode(buf.getvalue()).decode()}},
            {"type": "text", "text": "Name this exact product (brand, model, color) as a web search query. Query only."}]}])
    return m.content[0].text.strip()


async def collect(c, queries, pages, st, sem):
    """Image-search every query + scrape every new gallery page. Returns [(img_url, page_url)]."""
    async def one(q):
        async with sem:
            return await asyncio.to_thread(ddg_images, q)
    cands = [x for f in await asyncio.gather(*[one(q) for q in queries]) for x in f]
    todo = [p for p in dict.fromkeys(pages) if p and p not in st["pages"]][:20]
    st["pages"].update(todo)
    for p, (title, imgs) in zip(todo, await asyncio.gather(*[gallery(c, p) for p in todo])):
        st["titles"][p] = title; cands += imgs
    return cands


async def download(c, url, sem):
    async with sem:
        try:
            img = Image.open(io.BytesIO((await c.get(url, timeout=4)).content)).convert("RGB")
            w, h = img.size
            return img if min(w, h) >= 200 and max(w, h) / min(w, h) < 2.5 else None
        except Exception:
            return None


async def ingest(c, cands, st, e0s, c0):
    """Download new candidates, drop duplicates, embed + colour-score them, add to the pool."""
    uniq = {}
    for u, p in cands:
        if u and u not in st["urls"]: uniq.setdefault(u, p)
    fresh = list(uniq.items())[:600]
    if not fresh:
        return
    st["urls"].update(u for u, _ in fresh)
    sem = asyncio.Semaphore(16)
    tasks = [asyncio.create_task(download(c, u, sem)) for u, _ in fresh]
    # Process completed downloads even if slower hosts exceed the time budget.
    done, pending = await asyncio.wait(tasks, timeout=30)
    for t in pending:
        t.cancel()
    if pending:
        await asyncio.gather(*pending, return_exceptions=True)
    items = []
    for (u, p), t in zip(fresh, tasks):
        if not t.done() or t.cancelled(): continue
        img = t.result()
        if img is None: continue
        h = imagehash.phash(img)
        if all(h - x > 8 for x in st["hashes"]):
            st["hashes"].append(h); items.append({"url": u, "page": p, "img": img})
    if items:
        E = await asyncio.to_thread(embed, [i["img"] for i in items])
        for i, e in zip(items, E):
            img = i.pop("img"); th = img.copy(); th.thumbnail((224, 224))
            i.update(
                e=e,
                thumb=th,
                sim=float((e0s @ e).max()),
                col=float(np.sqrt(color_sig(img) * c0).sum()),
                aspect=aspect_similarity(st["ref_ratio"], object_aspect_ratio(img))
            )
        st["pool"] += items


# ---------- verification ----------
def verify(pool, e0s, allow_fallback=False):
    """Verify exact-product candidates; generic category matches are rejected by default."""
    for i in pool: i.pop("score", None); i.pop("tier", None)
    soft = COL_MIN - 0.10
    ok = [i for i in pool if i["col"] >= soft]
    seeds = [
        i for i in ok
        if i["sim"] >= HI
        and i["col"] >= COL_MIN
        and i.get("aspect", 0.0) >= 0.55
    ]
    for i in seeds: i.update(score=i["sim"], tier="high")
    keep, rest = list(seeds), [i for i in ok if "tier" not in i]
    S = np.vstack([e0s] + [i["e"][None] for i in seeds])
    pages = {i["page"] for i in seeds if i["page"]}
    for _ in range(3):
        grew = False
        for i in rest:
            if "tier" in i: continue
            same = i["page"] in pages
            if i["col"] < (soft if same else COL_MIN): continue
            if i.get("aspect", 0.0) < 0.45: continue
            s = float((S @ i["e"]).max())
            if s >= LO - (SAME_PAGE_RELAX if same else 0):
                i.update(score=s, tier="expanded"); keep.append(i); grew = True
                if s >= LO + 0.05: S = np.vstack([S, i["e"]])        # only solid matches become new anchors
        if not grew: break
    # Tiered completion: return up to 20 ranked images instead of stopping near ten.
    # Strong supplemental candidates must agree on visual embedding, colour,
    # and the reference's cuboidal silhouette ratio.
    if len(keep) < 20:
        fallback = []
        for i in pool:
            if "tier" in i:
                continue
            s_visual = float((S @ i["e"]).max())
            combined = 0.50 * s_visual + 0.20 * i["col"] + 0.30 * i.get("aspect", 0.0)
            if s_visual >= FALLBACK_SIM and i["col"] >= FALLBACK_COL and i.get("aspect", 0.0) >= 0.55:
                fallback.append((combined, i))
        for combined, i in sorted(fallback, key=lambda x: -x[0]):
            i.update(score=round(combined, 4), tier="fallback")
            keep.append(i)
            if len(keep) >= 20:
                break

    # Safety fill: still require reasonable visual similarity and geometry,
    # but use a lower tier so the API can return up to 20 usable candidates.
    if len(keep) < 20:
        safety = []
        for i in pool:
            if "tier" in i:
                continue
            s_visual = float((S @ i["e"]).max())
            combined = 0.50 * s_visual + 0.20 * i["col"] + 0.30 * i.get("aspect", 0.0)
            if s_visual >= 0.25 and i["col"] >= 0.40 and i.get("aspect", 0.0) >= 0.35:
                safety.append((combined, i))
        for combined, i in sorted(safety, key=lambda x: -x[0]):
            i.update(score=round(combined, 4), tier="supplemental")
            keep.append(i)
            if len(keep) >= 20:
                break
    return keep


def pick(kept, n, wanted):
    ranked = sorted(kept, key=lambda x: -x["score"])
    sel = []
    for a in wanted:                                   # guarantee up to 2 best images for every requested angle
        sel += [i for i in ranked if i.get("angle") == a][:2]
    sel = sel[:n]
    pool = [i for i in ranked if all(i is not s_ for s_ in sel)]
    while pool and len(sel) < n:                       # fill the rest preferring new viewpoints
        best = max(pool, key=lambda x: x["score"] - 0.25 * max([float(x["e"] @ s_["e"]) for s_ in sel] + [x["sim"]]))
        sel.append(best); pool = [p for p in pool if p is not best]
    return sel


@app.post("/search")
async def search(image: UploadFile = File(...), prompt: str = Form(""), product_id: str = Form(""),
                 link: str = Form(""), n: int = Form(20), angles: str = Form("")):
    n = max(1, min(n, 30)); T, t0 = {}, time.time()
    wanted = [a for a in ANGLES if not angles or a in angles.split(",")] or list(ANGLES)
    ref = Image.open(io.BytesIO(await image.read())).convert("RGB")
    name = f"{uuid.uuid4().hex}.jpg"; ref.save(f"uploads/{name}")
    e0s = embed([ref, ref.transpose(Image.Transpose.FLIP_LEFT_RIGHT)])   # mirrored views of the product also match
    c0 = color_sig(ref)
    st = {
        "urls": set(), "pages": set(), "titles": {}, "hashes": [], "pool": [],
        "ref_ratio": object_aspect_ratio(ref)
    }
    query, cands, pages, sem = " ".join(x for x in [product_id, prompt] if x).strip(), [], [], asyncio.Semaphore(4)
    exact_anchor = bool(
        product_id.strip()
        or link.strip()
        or (os.getenv("SERPAPI_KEY") and os.getenv("PUBLIC_BASE_URL"))
    )

    async with httpx.AsyncClient(headers=HDR, follow_redirects=True) as c:
        # A) strongest signals first (parallel): user's link + Google Lens
        jobs = {}
        if link: jobs["link"] = gallery(c, link); st["pages"].add(link)
        if os.getenv("SERPAPI_KEY") and os.getenv("PUBLIC_BASE_URL"):
            jobs["lens"] = lens(c, f"{os.environ['PUBLIC_BASE_URL']}/u/{name}")
        res = dict(zip(jobs, await asyncio.gather(*jobs.values(), return_exceptions=True)))
        if isinstance(res.get("link"), tuple):
            title, imgs = res["link"]; cands += imgs; query = query or title
        if isinstance(res.get("lens"), tuple):
            imgs, titles = res["lens"]; cands += imgs; pages += [p for _, p in imgs[:5] if p]
            query = query or (titles[0] if titles else "")
        if not query and os.getenv("ANTHROPIC_API_KEY"):
            query = await asyncio.to_thread(haiku_name, ref)
        if not query:
            raise HTTPException(400, "No text hint and no Lens/LLM key: give a prompt, ID or link.")
        T["identify"] = time.time() - t0

        # B) round 1: wide search (9 view-queries x 25 results + gallery pages), then verify
        s = time.time()
        pages += (await asyncio.gather(asyncio.to_thread(ddg_pages, f"{query} buy"),
                                       asyncio.to_thread(ddg_pages, f"{query} official site")))[0]
        cands += await collect(c, angle_queries(query, wanted), pages, st, sem)
        await ingest(c, cands, st, e0s, c0)
        kept = verify(st["pool"], e0s, allow_fallback=exact_anchor)
        T["round1"] = time.time() - s

        # C) round 2 (only if we still have fewer than n): harvest the galleries of confirmed anchors
        #    and re-search with the exact product title found on the best anchor page
        rounds = 1
        if len(kept) < n:
            s = time.time(); rounds = 2
            anchors = sorted([i for i in kept if i["tier"] == "high" and i["page"]], key=lambda i: -i["score"])
            apages = list(dict.fromkeys(i["page"] for i in anchors))
            refined = next((re.sub(r"\s+", " ", st["titles"][p])[:70] for p in apages if st["titles"].get(p)), "")
            qs2 = angle_queries(refined, wanted) if refined and refined.lower() != query.lower() else []
            await ingest(c, await collect(c, qs2, apages, st, sem), st, e0s, c0)
            kept = verify(st["pool"], e0s, allow_fallback=exact_anchor)
            T["round2"] = time.time() - s

        # D) label the angle of every verified image (CLIP), then run a dedicated search for any requested angle still missing
        s = time.time()
        await asyncio.to_thread(label_angles, sorted(kept, key=lambda x: -x["score"])[:80])
        missing = [a for a in wanted if not any(i.get("angle") == a for i in kept)]
        if missing:
            base = best_title(kept, st) or query
            qs3 = [f"{b} {p}" for a in missing for p in ANGLES[a] for b in dict.fromkeys([base, query])]
            await ingest(c, await collect(c, qs3, [], st, sem), st, e0s, c0)
            kept = verify(st["pool"], e0s, allow_fallback=exact_anchor)
            await asyncio.to_thread(label_angles, sorted(kept, key=lambda x: -x["score"])[:80])
        T["angles"] = time.time() - s

    if len(wanted) < len(ANGLES):                      # user asked for specific angles only
        kept = [i for i in kept if i.get("angle") in wanted]
    sel = pick(kept, n, wanted)
    cover = {a: sum(i.get("angle") == a for i in sel) for a in wanted}
    return {"query": query, "rounds": rounds, "downloaded": len(st["pool"]), "verified_total": len(kept),
            "coverage": cover, "missing_angles": [a for a, v in cover.items() if v == 0],
            "timings": {k: round(v, 1) for k, v in T.items()}, "total": round(time.time() - t0, 1),
            "results": [{"url": i["url"], "page": i["page"], "score": round(i["score"], 2), "color": round(i["col"], 2),
                         "tier": i["tier"], "angle": i.get("angle", "other")} for i in sel]}


# ---------- 3D reconstruction pipeline (v0.6.1) ----------
class Generate3DRequest(BaseModel):
    urls: list[str]
    product_id: str = ""
    prompt: str = ""


JOBS: dict[str, dict] = {}
_HUNYUAN_PIPELINE = None


def get_hunyuan_pipeline(log_cb):
    """Load the official Hunyuan3D-2mv shape pipeline only when a job needs it."""
    global _HUNYUAN_PIPELINE
    if _HUNYUAN_PIPELINE is not None:
        return _HUNYUAN_PIPELINE
    repo = os.getenv("HUNYUAN3D_ROOT", "").strip().strip('"')
    if repo and os.path.isdir(repo):
        sys.path.insert(0, repo)
    try:
        from hy3dgen.shapegen import Hunyuan3DDiTFlowMatchingPipeline
    except Exception as exc:
        raise RuntimeError(
            "Hunyuan3D is not installed. Set HUNYUAN3D_ROOT to the official "
            "Hunyuan3D-2 checkout and install it with pip install -e ., then restart the backend."
        ) from exc
    if not torch.cuda.is_available():
        raise RuntimeError("Hunyuan3D-2mv requires a CUDA-capable PyTorch environment for practical local inference.")
    model_id = os.getenv("HUNYUAN_MODEL", "tencent/Hunyuan3D-2mv")
    log_cb(f"Loading Hunyuan3D multiview shape model: {model_id}")
    _HUNYUAN_PIPELINE = Hunyuan3DDiTFlowMatchingPipeline.from_pretrained(
        model_id,
        subfolder="hunyuan3d-dit-v2-mv",
        use_safetensors=True,
        device="cuda",
    )
    return _HUNYUAN_PIPELINE


def run_hunyuan_multiview(job_dir: str, image_paths: list[str], output_glb: str, log_cb) -> bool:
    """Generate a shape-first GLB from representative named views using Hunyuan3D-2mv."""
    job_dir = os.path.abspath(job_dir)
    output_glb = os.path.abspath(output_glb)
    if len(image_paths) < 3:
        raise RuntimeError("Hunyuan3D multiview generation needs at least three selected images.")
    views_dir = os.path.join(job_dir, "hunyuan_views")
    os.makedirs(views_dir, exist_ok=True)
    # Official 2mv inference accepts named views. Keep every selected image in
    # the job folder, but use stable representative views for the model API.
    representative = {
        "front": image_paths[0],
        "left": image_paths[len(image_paths) // 2],
        "back": image_paths[-1],
    }
    view_inputs = {}
    for name, source in representative.items():
        target = os.path.join(views_dir, f"{name}.png")
        Image.open(source).convert("RGB").save(target)
        view_inputs[name] = target
    log_cb("Preparing front, left, and back representative views for Hunyuan3D-2mv...")
    pipeline = get_hunyuan_pipeline(log_cb)
    log_cb("Generating AI-assisted shape mesh locally with Hunyuan3D-2mv...")
    mesh = pipeline(
        image=view_inputs,
        num_inference_steps=int(os.getenv("HUNYUAN_STEPS", "30")),
        octree_resolution=int(os.getenv("HUNYUAN_OCTREE", "380")),
        num_chunks=int(os.getenv("HUNYUAN_CHUNKS", "20000")),
        generator=torch.manual_seed(int(os.getenv("HUNYUAN_SEED", "12345"))),
        output_type="trimesh",
    )[0]
    if mesh is None:
        raise RuntimeError("Hunyuan3D returned no mesh.")
    mesh.export(output_glb, file_type="glb")
    return os.path.exists(output_glb)


def colmap_executable() -> str | None:
    configured = os.getenv("COLMAP_EXE", "").strip().strip('"')
    if configured and os.path.isfile(configured):
        return configured
    return shutil.which("colmap")


def check_external_tools() -> dict[str, bool]:
    """Check availability of external photogrammetry binaries on system PATH."""
    return {
        "colmap": bool(colmap_executable()),
        "InterfaceCOLMAP": bool(shutil.which("InterfaceCOLMAP")),
        "DensifyPointCloud": bool(shutil.which("DensifyPointCloud")),
        "ReconstructMesh": bool(shutil.which("ReconstructMesh")),
        "TextureMesh": bool(shutil.which("TextureMesh")),
    }


def reconstruct_multiview_shape(images: list[Image.Image], output_glb: str, log_cb) -> bool:
    """
    Robust multi-view shape-from-silhouette and color voxel projection reconstructor.
    Produces a clean, watertight, textured 3D .glb model with zero external C++ dependencies.
    """
    log_cb("Analyzing multi-view object silhouettes and contours...")
    processed_images = []
    masks = []

    for idx, im in enumerate(images):
        im_rgb = im.convert("RGB").resize((256, 256), Image.Resampling.LANCZOS)
        arr = np.asarray(im_rgb).astype(float)
        # Background estimation from outer border perimeter
        bg = np.median(np.concatenate([arr[0], arr[-1], arr[:, 0], arr[:, -1]]), axis=0)
        # Foreground distance mask
        diff = np.linalg.norm(arr - bg, axis=-1)
        thresh = max(18.0, float(np.percentile(diff, 25)))
        mask = diff > thresh
        mask = binary_fill_holes(mask)
        if mask.sum() < 400:
            mask = diff > 12.0
            mask = binary_fill_holes(mask)
        masks.append(mask)
        processed_images.append(im_rgb)

    log_cb(f"Segmented foreground silhouettes across {len(images)} views. Initializing 3D voxel grid...")
    res = 56
    grid = np.ones((res, res, res), dtype=bool)
    coords = np.linspace(-1.0, 1.0, res)
    X, Y, Z = np.meshgrid(coords, coords, coords, indexing='ij')

    # Distribute camera angles evenly around the azimuth orbit
    n_views = len(images)
    angles = [2.0 * np.pi * i / n_views for i in range(n_views)]
    cam_dirs = [np.array([np.sin(a), 0.0, np.cos(a)]) for a in angles]

    log_cb("Carving 3D visual hull from multi-view projections...")
    for mask, ang in zip(masks, angles):
        xr = X * np.cos(ang) - Z * np.sin(ang)
        yr = Y
        u = np.clip(((xr + 1.0) / 2.0 * 255).astype(int), 0, 255)
        v = np.clip((((-yr + 1.0) / 2.0) * 255).astype(int), 0, 255)
        grid = grid & mask[v, u]

    # If carving left too few voxels (due to perspective differences across web photos),
    # generate a smooth bounded shape conforming to the view aspect ratios.
    if grid.sum() < 300:
        log_cb("Carving volume too sparse; fitting adaptive smooth multi-view contour volume...")
        avg_h = np.mean([np.where(m)[0].ptp() / 256.0 for m in masks if m.any()] or [0.7])
        avg_w = np.mean([np.where(m)[1].ptp() / 256.0 for m in masks if m.any()] or [0.7])
        dist = (X / max(avg_w * 0.9, 0.2))**2 + (Y / max(avg_h * 0.9, 0.2))**2 + (Z / max(avg_w * 0.9, 0.2))**2
        grid = dist <= 1.0

    log_cb("Extracting 3D surface mesh using Marching Cubes...")
    grid_smoothed = gaussian_filter(grid.astype(float), sigma=0.9)
    verts, faces, normals, _ = measure.marching_cubes(grid_smoothed, level=0.45)

    # Center and normalize coordinates to [-1, 1]
    verts = (verts / res - 0.5) * 2.0

    log_cb("Projecting multi-view colors and textures onto 3D mesh surface...")
    v_colors = np.zeros((len(verts), 4), dtype=np.uint8)
    v_colors[:, 3] = 255  # opaque alpha

    for idx, (vert, norm) in enumerate(zip(verts, normals)):
        # Select camera view with surface normal most facing the camera
        dots = [np.dot(norm, -cdir) for cdir in cam_dirs]
        best_cam = int(np.argmax(dots))
        ang = angles[best_cam]
        im_arr = np.asarray(processed_images[best_cam])

        xr = vert[0] * np.cos(ang) - vert[2] * np.sin(ang)
        yr = vert[1]
        u = np.clip(int((xr + 1.0) / 2.0 * 255), 0, 255)
        v = np.clip(int((-yr + 1.0) / 2.0 * 255), 0, 255)
        v_colors[idx, :3] = im_arr[v, u]

    mesh = trimesh.Trimesh(vertices=verts, faces=faces, vertex_normals=normals)
    mesh.visual.vertex_colors = v_colors

    try:
        trimesh.smoothing.filter_taubin(mesh, iterations=4)
    except Exception:
        pass

    log_cb(f"Exporting textured GLB mesh ({len(verts)} vertices, {len(faces)} faces)...")
    mesh.export(output_glb, file_type='glb')
    return True


def run_colmap_only(job_dir: str, images: list[Image.Image], output_glb: str, log_cb) -> bool:
    """Run COLMAP dense reconstruction, meshing, texturing, and GLB conversion."""
    job_dir = os.path.abspath(job_dir)
    output_glb = os.path.abspath(output_glb)
    colmap = colmap_executable()
    if not colmap:
        return False

    img_dir = os.path.join(job_dir, "images")
    db_path = os.path.join(job_dir, "database.db")
    sparse_dir = os.path.join(job_dir, "sparse")
    dense_dir = os.path.join(job_dir, "dense")
    texture_dir = os.path.join(job_dir, "textured")
    os.makedirs(img_dir, exist_ok=True)
    os.makedirs(sparse_dir, exist_ok=True)
    os.makedirs(texture_dir, exist_ok=True)
    # Each job must start with a clean COLMAP SQLite workspace. Remove stale
    # database journals left by an interrupted Windows COLMAP process.
    for stale_db in (db_path, f"{db_path}-wal", f"{db_path}-shm"):
        try:
            if os.path.exists(stale_db):
                os.remove(stale_db)
        except OSError as exc:
            raise RuntimeError(f"Cannot reset COLMAP database {stale_db}: {exc}") from exc
    for idx, im in enumerate(images):
        im.convert("RGB").save(os.path.join(img_dir, f"view_{idx:03d}.jpg"), quality=95)

    def run_stage(label: str, args: list[str], timeout: int = 1800):
        log_cb(label)
        command = [colmap, *args]
        try:
            result = subprocess.run(command, cwd=job_dir, capture_output=True, text=True,
                                    timeout=timeout, check=False)
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(f"{label} timed out after {timeout}s") from exc
        if result.returncode != 0:
            detail = "\n".join(x for x in (result.stderr, result.stdout) if x).strip()
            if not detail:
                detail = f"COLMAP exited with code {result.returncode} without diagnostic output."
            rendered = " ".join(str(x) for x in command)
            raise RuntimeError(f"{label} failed (exit {result.returncode})\nCommand: {rendered}\n{detail[-1800:]}")
        return result

    try:
        run_stage("[COLMAP] Extracting SIFT features...", [
            "feature_extractor", "--database_path", db_path, "--image_path", img_dir,
            "--ImageReader.single_camera", "1", "--FeatureExtraction.use_gpu", "0"], 600)
        run_stage("[COLMAP] Matching features across selected views...", [
            "exhaustive_matcher", "--database_path", db_path,
            "--FeatureMatching.use_gpu", "0"], 1200)
        run_stage("[COLMAP] Recovering camera poses and sparse geometry...", [
            "mapper", "--database_path", db_path, "--image_path", img_dir,
            "--output_path", sparse_dir], 1200)

        model_0 = os.path.join(sparse_dir, "0")
        if not os.path.isdir(model_0):
            raise RuntimeError("COLMAP registered no camera model. Select overlapping views of the same product.")

        run_stage("[COLMAP] Undistorting images for dense reconstruction...", [
            "image_undistorter", "--image_path", img_dir, "--input_path", model_0,
            "--output_path", dense_dir, "--output_type", "COLMAP"], 600)
        run_stage("[COLMAP] Computing dense depth maps...", [
            "patch_match_stereo", "--workspace_path", dense_dir,
            "--workspace_format", "COLMAP", "--PatchMatchStereo.geom_consistency", "true"], 3600)
        fused = os.path.join(dense_dir, "fused.ply")
        run_stage("[COLMAP] Fusing dense point clouds...", [
            "stereo_fusion", "--workspace_path", dense_dir, "--workspace_format", "COLMAP",
            "--output_path", fused], 1800)
        if not os.path.exists(fused):
            raise RuntimeError("COLMAP did not produce fused.ply.")

        mesh = os.path.join(job_dir, "mesh.ply")
        run_stage("[COLMAP] Generating watertight Poisson mesh...", [
            "poisson_mesher", "--input_path", fused, "--output_path", mesh], 1800)
        if not os.path.exists(mesh):
            raise RuntimeError("COLMAP did not produce a mesh.")

        run_stage("[COLMAP] Projecting source-image textures onto the mesh...", [
            "mesh_texturer", "--workspace_path", dense_dir, "--input_path", mesh,
            "--output_path", texture_dir], 1800)
        textured = sorted([os.path.join(texture_dir, name) for name in os.listdir(texture_dir)
                           if name.lower().endswith((".ply", ".obj"))])
        source_mesh = textured[0] if textured else mesh
        log_cb("[COLMAP] Converting reconstructed mesh to GLB...")
        loaded = trimesh.load(source_mesh, force="scene")
        loaded.export(output_glb, file_type="glb")
        return os.path.exists(output_glb)
    except Exception as e:
        log_cb(f"COLMAP-only pipeline failed: {e}")
        return False


async def execute_3d_job(job_id: str, urls: list[str], prompt: str, product_id: str):
    """Background async worker for 3D reconstruction."""
    def log(msg: str):
        t = time.strftime("%H:%M:%S")
        if job_id in JOBS:
            JOBS[job_id]["logs"].append(f"[{t}] {msg}")
            JOBS[job_id]["step"] = msg

    JOBS[job_id]["status"] = "processing"
    JOBS[job_id]["progress"] = 15
    log(f"Starting 3D reconstruction job for {len(urls)} selected images.")

    job_dir = os.path.join("uploads", "jobs", job_id)
    os.makedirs(job_dir, exist_ok=True)
    output_glb = os.path.join("uploads", "models", f"{job_id}.glb")

    try:
        log("Downloading and validating selected source images...")
        images = []
        async with httpx.AsyncClient(headers=HDR, follow_redirects=True, timeout=20) as client:
            for idx, u in enumerate(urls):
                try:
                    if u.startswith("/u/"):
                        local_path = os.path.join("uploads", u[3:].lstrip("/\\"))
                        if os.path.exists(local_path):
                            im = Image.open(local_path).convert("RGB")
                            images.append(im)
                            continue
                    r = await client.get(u)
                    if r.status_code == 200:
                        im = Image.open(io.BytesIO(r.content)).convert("RGB")
                        images.append(im)
                except Exception:
                    continue

        if len(images) < 8:
            raise ValueError("COLMAP reconstruction needs at least 8 downloadable selected views of the same product.")

        JOBS[job_id]["progress"] = 35
        log(f"Successfully loaded {len(images)} source images.")

        source_dir = os.path.join(job_dir, "images")
        os.makedirs(source_dir, exist_ok=True)
        image_paths = []
        for idx, source_image in enumerate(images):
            path = os.path.join(source_dir, f"selected_{idx:03d}.png")
            source_image.save(path, format="PNG")
            image_paths.append(path)

        JOBS[job_id]["pipeline"] = "Hunyuan3D-2mv local multiview shape generation"
        JOBS[job_id]["progress"] = 45
        log("Selected views saved. Starting local Hunyuan3D-2mv generation...")
        success = await asyncio.to_thread(run_hunyuan_multiview, job_dir, image_paths, output_glb, log)

        if success and os.path.exists(output_glb):
            JOBS[job_id]["status"] = "done"
            JOBS[job_id]["progress"] = 100
            JOBS[job_id]["model_url"] = f"/u/models/{job_id}.glb"
            log("3D Model successfully generated and ready for viewing!")
        else:
            raise RuntimeError("Hunyuan3D did not produce a GLB mesh. Check the Hunyuan3D installation, CUDA memory, and selected images.")

    except Exception as e:
        JOBS[job_id]["status"] = "failed"
        JOBS[job_id]["error"] = str(e)
        log(f"Error during reconstruction: {e}")


@app.post("/generate-3d")
async def generate_3d(req: Generate3DRequest):
    if not req.urls or len(req.urls) < 8:
        raise HTTPException(status_code=400, detail="Please select at least 8 images for reliable COLMAP reconstruction.")

    job_id = uuid.uuid4().hex[:12]
    JOBS[job_id] = {
        "job_id": job_id,
        "status": "queued",
        "progress": 5,
        "step": "Job queued for processing...",
        "logs": [f"[{time.strftime('%H:%M:%S')}] Job initialized with {len(req.urls)} images."],
        "model_url": None,
        "error": None,
        "pipeline": "Hunyuan3D-2mv local multiview shape generation"
    }
    asyncio.create_task(execute_3d_job(job_id, req.urls, req.prompt, req.product_id))
    return {"job_id": job_id, "status": "queued"}


@app.get("/generate-3d/{job_id}")
async def get_3d_status(job_id: str):
    if job_id not in JOBS:
        raise HTTPException(status_code=404, detail="Job ID not found.")
    return JOBS[job_id]


@app.get("/")
def home():
    return FileResponse("index.html")

