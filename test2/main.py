"""
Run:  uvicorn main:app --port 8000     then open http://localhost:8000
Optional env: SERPAPI_KEY + PUBLIC_BASE_URL (ngrok URL) -> Google Lens reverse image search
              ANTHROPIC_API_KEY -> one cheap Haiku call, only if there is no text hint at all
"""
import asyncio, base64, io, os, re, time, uuid
from urllib.parse import urljoin

import httpx, imagehash, numpy as np, torch
from bs4 import BeautifulSoup
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image
from transformers import AutoImageProcessor, AutoModel, CLIPModel, CLIPProcessor

try:
    from ddgs import DDGS
except ImportError:
    from duckduckgo_search import DDGS

HI, LO, COL_MIN = 0.70, 0.60, 0.70   # accuracy gates (unchanged); tune on your real images
SAME_PAGE_RELAX = 0.08               # extra slack for images from the same listing as a confirmed anchor
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
    return title.strip(), [(urljoin(page, u), page) for u in dict.fromkeys(urls)][:40]


def ddg_images(q):
    for _ in range(2):                                   # one retry: ddgs rate-limits under bursts
        try:
            return [(x["image"], x.get("url", "")) for x in DDGS().images(q, max_results=25)]
        except Exception:
            time.sleep(1)
    return []


def ddg_pages(q):
    try:
        return [x["href"] for x in DDGS().text(q, max_results=8)]
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
    todo = [p for p in dict.fromkeys(pages) if p and p not in st["pages"]][:10]
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
    fresh = list(uniq.items())[:300]
    st["urls"].update(u for u, _ in fresh)
    sem = asyncio.Semaphore(24)
    tasks = [asyncio.create_task(download(c, u, sem)) for u, _ in fresh]
    await asyncio.wait(tasks, timeout=12)
    items = []
    for (u, p), t in zip(fresh, tasks):
        if not t.done(): t.cancel(); continue
        img = t.result()
        if img is None: continue
        h = imagehash.phash(img)
        if all(h - x > 3 for x in st["hashes"]):
            st["hashes"].append(h); items.append({"url": u, "page": p, "img": img})
    if items:
        E = await asyncio.to_thread(embed, [i["img"] for i in items])
        for i, e in zip(items, E):
            img = i.pop("img"); th = img.copy(); th.thumbnail((224, 224))
            i.update(e=e, thumb=th, sim=float((e0s @ e).max()), col=float(np.sqrt(color_sig(img) * c0).sum()))
        st["pool"] += items


# ---------- verification ----------
def verify(pool, e0s):
    """colour gate -> confident anchors -> iterative expansion (up to 3 rounds) -> same-listing relaxation."""
    for i in pool: i.pop("score", None); i.pop("tier", None)
    soft = COL_MIN - 0.10
    ok = [i for i in pool if i["col"] >= soft]
    seeds = [i for i in ok if i["sim"] >= HI and i["col"] >= COL_MIN]
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
            s = float((S @ i["e"]).max())
            if s >= LO - (SAME_PAGE_RELAX if same else 0):
                i.update(score=s, tier="expanded"); keep.append(i); grew = True
                if s >= LO + 0.05: S = np.vstack([S, i["e"]])        # only solid matches become new anchors
        if not grew: break
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
                 link: str = Form(""), n: int = Form(15), angles: str = Form("")):
    n = max(1, min(n, 30)); T, t0 = {}, time.time()
    wanted = [a for a in ANGLES if not angles or a in angles.split(",")] or list(ANGLES)
    ref = Image.open(io.BytesIO(await image.read())).convert("RGB")
    name = f"{uuid.uuid4().hex}.jpg"; ref.save(f"uploads/{name}")
    e0s = embed([ref, ref.transpose(Image.Transpose.FLIP_LEFT_RIGHT)])   # mirrored views of the product also match
    c0 = color_sig(ref)
    st = {"urls": set(), "pages": set(), "titles": {}, "hashes": [], "pool": []}
    query, cands, pages, sem = " ".join(x for x in [product_id, prompt] if x).strip(), [], [], asyncio.Semaphore(4)

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
        kept = verify(st["pool"], e0s)
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
            kept = verify(st["pool"], e0s)
            T["round2"] = time.time() - s

        # D) label the angle of every verified image (CLIP), then run a dedicated search for any requested angle still missing
        s = time.time()
        await asyncio.to_thread(label_angles, sorted(kept, key=lambda x: -x["score"])[:80])
        missing = [a for a in wanted if not any(i.get("angle") == a for i in kept)]
        if missing:
            base = best_title(kept, st) or query
            qs3 = [f"{b} {p}" for a in missing for p in ANGLES[a] for b in dict.fromkeys([base, query])]
            await ingest(c, await collect(c, qs3, [], st, sem), st, e0s, c0)
            kept = verify(st["pool"], e0s)
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


@app.get("/")
def home():
    return FileResponse("index.html")