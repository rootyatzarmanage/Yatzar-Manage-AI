# Yatzar Candidate-Evidence Diagnostic Audit: ViewSonic LS800HD
**Document ID**: `TEMP_VIEWSONIC_CANDIDATE_EVIDENCE_AUDIT.md`  
**Date**: October 12, 2026  
**Target SKU**: `LS800HD` | **Brand**: `ViewSonic`  
**Run Reference**: Job `res-job-d4411f64` (`backend/cache/jobs/research_LS800HD.json`)  
**Audit Type**: READ-ONLY Diagnostic (Strictly Zero Production Code Modifications)  

---

## 1. Executive Summary

Following the fix to `backend/services/identifier_policy.py` that successfully resolved the identifier erasure bug (preserving `LS800HD` as canonical model), exact-model queries were properly planned and dispatched. However, the research run still resulted in **0 curated reference images**, reporting 32 downloaded candidates with DINO similarities between `-0.07` and `+0.09`, triggering the zero-result fallback.

This diagnostic was commissioned to answer the decisive supervisor question:
> **"Are genuinely good ViewSonic LS800HD product images being retrieved but rejected by our evidence/filtering pipeline, OR are the search results themselves mostly wrong/irrelevant?"**

### Definite Empirical Conclusion:
**THE SEARCH RESULTS THEMSELVES ARE 100% WRONG AND IRRELEVANT.**

- **Genuine LS800HD Images Retrieved**: **0 out of 32 (0.0%)**.
- **Good Images Rejected by Pipeline**: **0 out of 32 (0.0%)**.
- **Bad Search Results Harvested**: **32 out of 32 (100.0%)**.
- **Pipeline Filter Performance**: **100% Correct Rejections**. Every single rejected candidate was completely unrelated web noise (e.g., Hindu devotional paintings of Radha & Krishna, photos of cricket player Shubman Gill, anime figurines, Islamic prayer videos, Gujarati Navratri festival banners, clip-art flip-flops, police press conferences, pharmacology slide notes, and cartoon cat sketches).
- **DINOv2 Performance**: **Behaving Exactly as Intended**. DINO assigned cosine similarities of `-0.07` to `+0.09` because it was comparing an authentic, pristine ViewSonic laser projector against cricketers, deities, and festival dancers. If DINO had scored these >= 0.45, that would have represented model catastrophic failure.
- **Root Cause**: **Search Retrieval Engine Failure**. When DuckDuckGo HTML yielded 0 image matches, the pipeline fell back to unauthenticated public HTTP GET scraping of Bing Image Search (`bing.com/images/search?q=...`). Because exact quoted queries like `"ViewSonic LS800HD"` return zero or few images on Bing's public HTTP endpoint without a browser session, Bing silently defaulted to displaying regional/trending carousels (trending Indian cultural events, cricketers, and festival media). The scraper's regex (`murl&quot;:&quot;...&quot;`) indiscriminately captured those trending carousel URLs and injected them as candidate images.


---

## 2. Target Product Profile

| Field | Target Value | Policy Status |
|---|---|---|
| **Product Name** | `ViewSonic Laser Projector` | Verified |
| **Brand** | `ViewSonic` | Preserved |
| **Product ID / SKU** | `LS800HD` | Preserved |
| **Model Number** | `LS800HD` | Preserved as Canonical Model (Identifier fix confirmed) |
| **Category** | `Consumer Electronics` | Defaulted |
| **Seed Image** | `upload_b64_1791704463.jpg` | 467x340 PNG (Alpha=255) |


---

## 3. Exact Queries Used

The query planner correctly produced 14 planned queries targeting the canonical identifier `LS800HD`:

| Pass | Query String | Query Family | Target Evidence | Tagged Angle |
|---|---|---|---|---|
| Pass 1 | `"ViewSonic LS800HD"` | EXACT_PRODUCT | EXACT_MATCH | Isometric Angle |
| Pass 1 | `"ViewSonic Laser Projector" "LS800HD"` | EXACT_PRODUCT | EXACT_MATCH | Isometric Angle |
| Pass 1 | `"ViewSonic" "LS800HD" official photo` | EXACT_PRODUCT | EXACT_MATCH | Front Reference |
| Pass 2 | `"ViewSonic LS800HD" front view` | PRODUCT_VIEWPOINT | FRONT | Front Reference |
| Pass 2 | `"ViewSonic LS800HD" side profile` | PRODUCT_VIEWPOINT | SIDE | Side Profile |
| Pass 2 | `"ViewSonic LS800HD" rear view` | PRODUCT_VIEWPOINT | REAR | Rear View |
| Pass 2 | `"ViewSonic LS800HD" top view` | PRODUCT_VIEWPOINT | TOP | Front Reference |
| Pass 2 | `"ViewSonic LS800HD" underside bottom view` | PRODUCT_VIEWPOINT | BOTTOM | Rear View |
| Pass 2 | `"ViewSonic LS800HD" isometric 3D angle` | PRODUCT_VIEWPOINT | ISOMETRIC | Isometric Angle |
| Pass 3 | `"ViewSonic LS800HD" technical drawing dimensions` | PRODUCT_TECHNICAL | TECHNICAL_DRAWING | Front Reference |
| Pass 3 | `"ViewSonic LS800HD" dimensional specification sheet` | PRODUCT_TECHNICAL | DIMENSIONS | Front Reference |
| Pass 3 | `"ViewSonic LS800HD" installation manual mounting diagram` | PRODUCT_TECHNICAL | INSTALLATION | Side Profile |
| Pass 3 | `"ViewSonic LS800HD" camera module interface ports` | PRODUCT_COMPONENT | COMPONENT | Rear View |
| Pass 4 | `"ViewSonic" Consumer Electronics product view` | CATEGORY_ATTRIBUTE | CATEGORY_CONTEXT | Isometric Angle |


---

## 4. Reference / Seed Image Diagnostic

- **Path**: `E:\SANJAY\YatzarCreations\Yatzar-Manage-AI\backend\cache\uploads\upload_b64_1791704463.jpg`
- **Format**: PNG (mode `RGBA`, solid alpha channel 255)
- **Dimensions**: 467 x 340 pixels
- **Aspect Ratio**: 1.37
- **File Size**: 107,409 bytes
- **Origin**: User upload via product creation payload
- **Visual Depiction**: Pristine, studio-grade 3/4 isometric product photograph of the white ViewSonic LS800HD Laser Projector on a clean white background. Shows the front projector lens with blue optical illumination, the side ventilation grid, the top control sliders, and chassis branding.
- **Suspicion Check**: **NO SEED REFERENCE PROBLEM**. The seed image is 100% authentic, correct, and representative of the exact target product. It provides an ideal visual embedding anchor.


---

## 5. Candidate Inventory

- **Total Image URLs Discovered in Harvest**: 45 URLs (across DuckDuckGo and Bing HTTP)
- **Valid Unique Image URLs Successfully Downloaded**: 32 images
- **Prefilter Status**: 32 accepted (all met >300px dimensions, valid aspect ratio, valid format)
- **DINOv2 Embedding Extracted**: 32 / 32
- **Semantic Evaluated**: 32 / 32
- **Accepted into Curated Pool**: 0
- **Rejected by Scraper / Curation**: 32


---

## 6. Candidate-by-Candidate Evidence Table

| Idx | ID | Query | Dimensions | DINO Sim | Actual Content Depicted | Rejection Reason | Final Classification |
|---|---|---|---|---|---|---|---|
| 00 | `img-521ddcb2` | `"ViewSonic LS800HD"` | 1805x1508 | `+0.05` | Painting: Lord Krishna combing Radha's hair by a pond with swans | `LOW_VISUAL_SIMILARITY` | **B. BAD SEARCH RESULT** |
| 01 | `img-21b70e84` | `"ViewSonic LS800HD"` | 1024x804 | `-0.04` | Painting: Radha and Krishna swinging on a flower swing | `LOW_VISUAL_SIMILARITY` | **B. BAD SEARCH RESULT** |
| 02 | `img-a96a4395` | `"ViewSonic LS800HD"` | 1440x1894 | `+0.01` | Painting: Radha and Krishna standing together in forest | `LOW_VISUAL_SIMILARITY` | **B. BAD SEARCH RESULT** |
| 03 | `img-028fe452` | `"ViewSonic LS800HD"` | 1195x1500 | `-0.03` | Painting: Radha and Krishna in traditional dance pose (framed) | `LOW_VISUAL_SIMILARITY` | **B. BAD SEARCH RESULT** |
| 04 | `img-53782f48` | `"ViewSonic LS800HD"` | 1689x2152 | `-0.03` | Painting: Colorful modern expressive painting of Radha and Krishna | `LOW_VISUAL_SIMILARITY` | **B. BAD SEARCH RESULT** |
| 05 | `img-3557d9c2` | `"ViewSonic LS800HD"` | 1024x1409 | `+0.01` | Painting: Krishna with flute and peacock in pastoral meadow | `LOW_VISUAL_SIMILARITY` | **B. BAD SEARCH RESULT** |
| 06 | `img-5398499a` | `"ViewSonic Laser Projector" "LS800HD"` | 960x540 | `+0.02` | Photograph: Indian cricketer Shubman Gill celebrating century in ODI jersey | `LOW_VISUAL_SIMILARITY` | **B. BAD SEARCH RESULT** |
| 07 | `img-a750cb4a` | `"ViewSonic Laser Projector" "LS800HD"` | 1200x800 | `+0.04` | Photograph: Indian cricketer Shubman Gill raising bat with helmet on | `LOW_VISUAL_SIMILARITY` | **B. BAD SEARCH RESULT** |
| 08 | `img-a6b1d36e` | `"ViewSonic Laser Projector" "LS800HD"` | 1600x900 | `+0.05` | Photograph: Indian cricketer Shubman Gill in Test cricket whites celebrating | `LOW_VISUAL_SIMILARITY` | **B. BAD SEARCH RESULT** |
| 09 | `img-e3460d84` | `"ViewSonic Laser Projector" "LS800HD"` | 1024x1024 | `-0.02` | Photograph: Shubman Gill in Gujarat Titans IPL jersey posing against dark background | `LOW_VISUAL_SIMILARITY` | **B. BAD SEARCH RESULT** |
| 10 | `img-ce6fc492` | `"ViewSonic Laser Projector" "LS800HD"` | 736x582 | `+0.05` | Photograph: Shubman Gill smiling portrait in blue polo shirt | `LOW_VISUAL_SIMILARITY` | **B. BAD SEARCH RESULT** |
| 11 | `img-46950ec0` | `"ViewSonic Laser Projector" "LS800HD"` | 1080x1125 | `+0.03` | Photograph: Shubman Gill close-up face portrait smiling | `LOW_VISUAL_SIMILARITY` | **B. BAD SEARCH RESULT** |
| 12 | `img-b4251cd0` | `"ViewSonic" "LS800HD" official photo` | 1024x1280 | `-0.04` | Art/Figurine: Dragon Ball Z Goku anime character action figure render | `LOW_VISUAL_SIMILARITY` | **B. BAD SEARCH RESULT** |
| 13 | `img-f9fc4f45` | `"ViewSonic LS800HD" front view` | 1280x720 | `+0.01` | Video Screenshot: Elderly man in white prayer robe reciting Quran at pulpit | `LOW_VISUAL_SIMILARITY` | **B. BAD SEARCH RESULT** |
| 14 | `img-81347315` | `"ViewSonic LS800HD" front view` | 1280x720 | `+0.08` | YouTube Thumbnail: Video frame with Arabic text 'تلاوة مؤثرة' (moving recitation) | `LOW_VISUAL_SIMILARITY` | **B. BAD SEARCH RESULT** |
| 15 | `img-06802705` | `"ViewSonic LS800HD" front view` | 480x360 | `+0.06` | Video Screenshot: Nighttime Islamic prayer gathering at mosque | `LOW_VISUAL_SIMILARITY` | **B. BAD SEARCH RESULT** |
| 16 | `img-25a55a34` | `"ViewSonic LS800HD" front view` | 480x360 | `-0.03` | Video Screenshot: Two men in Islamic white thobes at indoor prayer podium with microphone | `LOW_VISUAL_SIMILARITY` | **B. BAD SEARCH RESULT** |
| 17 | `img-374b639c` | `"ViewSonic LS800HD" front view` | 480x360 | `+0.00` | YouTube Thumbnail: Islamic religious lecture featuring Qari Abdul Aziz Falahi | `LOW_VISUAL_SIMILARITY` | **B. BAD SEARCH RESULT** |
| 18 | `img-dee21bef` | `"ViewSonic LS800HD" side profile` | 720x720 | `-0.00` | Graphic Banner: Chaitra Navratri Hindu festival greeting with Goddess Durga & Gujarati text | `LOW_VISUAL_SIMILARITY` | **B. BAD SEARCH RESULT** |
| 19 | `img-032657e8` | `"ViewSonic LS800HD" side profile` | 800x450 | `-0.07` | Graphic Banner: Gujarati religious greeting 'Happy Navratri' with Goddess Durga on tiger | `LOW_VISUAL_SIMILARITY` | **B. BAD SEARCH RESULT** |
| 20 | `img-9467d580` | `"ViewSonic LS800HD" side profile` | 1200x675 | `-0.00` | Graphic Artwork: Goddess Durga riding lion across desert landscape | `LOW_VISUAL_SIMILARITY` | **B. BAD SEARCH RESULT** |
| 21 | `img-1525b726` | `"ViewSonic LS800HD" rear view` | 1500x1600 | `+0.04` | Clip-art Vector: Black and white line drawing of a pair of flip-flop sandals | `LOW_VISUAL_SIMILARITY` | **B. BAD SEARCH RESULT** |
| 22 | `img-8155f2cc` | `"ViewSonic LS800HD" top view` | 2560x1920 | `+0.06` | Photograph: Surat / Gujarat corporate or government office meeting around conference table | `LOW_VISUAL_SIMILARITY` | **B. BAD SEARCH RESULT** |
| 23 | `img-ed2d7875` | `"ViewSonic LS800HD" top view` | 600x500 | `-0.00` | Photograph: Press conference with Gujarat / Surat Police DGP and officers seated at banner | `LOW_VISUAL_SIMILARITY` | **B. BAD SEARCH RESULT** |
| 24 | `img-34124285` | `"ViewSonic LS800HD" top view` | 1200x675 | `+0.03` | Document Scan: Official government registration certificate / vehicle pass document | `LOW_VISUAL_SIMILARITY` | **B. BAD SEARCH RESULT** |
| 25 | `img-ef54335f` | `"ViewSonic LS800HD" underside bottom view` | 1320x917 | `+0.01` | Photograph: Large crowd dancing Garba at night during Navratri festival | `LOW_VISUAL_SIMILARITY` | **B. BAD SEARCH RESULT** |
| 26 | `img-00d8416a` | `"ViewSonic LS800HD" underside bottom view` | 1024x700 | `+0.03` | Graphic Banner: Red festive banner depicting Goddess Durga and Garba dancers with 'Navratri' text | `LOW_VISUAL_SIMILARITY` | **B. BAD SEARCH RESULT** |
| 27 | `img-79f2e9d8` | `"ViewSonic LS800HD" underside bottom view` | 1024x631 | `+0.01` | Photograph: Women in traditional Gujarati chaniya choli dresses dancing Garba in circle | `LOW_VISUAL_SIMILARITY` | **B. BAD SEARCH RESULT** |
| 28 | `img-9943d0d9` | `"ViewSonic LS800HD" underside bottom view` | 2560x1707 | `-0.04` | Photograph: Stage performance of dancers in colorful Indian folk attire under stage lights | `LOW_VISUAL_SIMILARITY` | **B. BAD SEARCH RESULT** |
| 29 | `img-3403c150` | `"ViewSonic LS800HD" underside bottom view` | 1540x900 | `-0.03` | Photograph: Dancers performing folk dance outdoors in colorful traditional costumes | `LOW_VISUAL_SIMILARITY` | **B. BAD SEARCH RESULT** |
| 30 | `img-33b82a08` | `"ViewSonic LS800HD" isometric 3D angle` | 2048x1536 | `+0.09` | Slide Graphic: Academic medical pharmacology slide: 'Colour Tests' (Mandelin's Test, Nitric Acid Test) | `LOW_VISUAL_SIMILARITY` | **B. BAD SEARCH RESULT** |
| 31 | `img-a3147f0d` | `"ViewSonic LS800HD" technical drawing dimensions` | 2555x4009 | `+0.03` | Clip-art Line Art: Black and white coloring page outline of a cartoon smiling cat | `LOW_VISUAL_SIMILARITY` | **B. BAD SEARCH RESULT** |


---

## 7. Classification Summary

Every candidate was evaluated and placed into exactly one primary category:

| Category | Description | Count | Percentage |
|---|---|---|---|
| **A. GOOD IMAGE REJECTED** | Genuine LS800HD product image, but rejected by filtering/scoring | **0** | **0.0%** |
| **B. BAD SEARCH RESULT** | Search retrieved an unrelated product / image | **32** | **100.0%** |
| **C. WRONG VIEW** | Correct LS800HD, but unsuitable angle/view | **0** | **0.0%** |
| **D. WRONG PRODUCT** | Different ViewSonic product/model | **0** | **0.0%** |
| **E. DUPLICATE** | Same visual/product image already represented | **0** | **0.0%** |
| **F. LOW QUALITY** | Too small, corrupted, thumbnail | **0** | **0.0%** |
| **G. TECHNICAL/CAD** | Technical drawing / CAD rather than real photo | **0** | **0.0%** |
| **H. ACCEPTABLE / SURVIVE** | Valid reference candidate that should survive | **0** | **0.0%** |
| **TOTAL** | | **32** | **100.0%** |


---

## 8. DINOv2 Similarity Distribution

### Statistical Summary
- **Minimum Similarity**: `-0.0700`
- **Maximum Similarity**: `0.0900`
- **Mean Similarity**: `0.0119`
- **Median Similarity**: `0.0100`
- **Pipeline Threshold**: `0.4500`

### Bucket Distribution
| Similarity Range | Candidate Count | Percentage | Candidate Content in Bucket |
|---|---|---|---|
| `< 0.00` | 9 | 28.1% | Krishna paintings, cricketer Shubman Gill, anime Goku, Islamic prayer |
| `0.00 – 0.10` | 23 | 71.9% | Krishna paintings, cricketers, Navratri festival cards/dancers, sandals, cat drawing |
| `0.10 – 0.20` | 0 | 0.0% | None |
| `0.20 – 0.30` | 0 | 0.0% | None |
| `0.30 – 0.40` | 0 | 0.0% | None |
| `0.40 – 0.45` | 0 | 0.0% | None |
| `>= 0.45` | 0 | 0.0% | None |

### Critical Cross-Reference:
> **How many GOOD IMAGE REJECTED candidates have DINO < 0.45?**  
> **EXACTLY ZERO (0).**  
> There are zero genuine LS800HD images in the entire set. DINO assigned scores near 0.00 because the images depict human beings, deities, and festival events rather than an electronic projector.


---

## 9. Identity Evidence Analysis

1. **Source Page URLs were Empty**: Because the Bing HTTP fallback scraper only extracts the `murl` attribute from Bing's image search HTML and discards page context, `source_page_url` was recorded as `""` for all 32 candidates. No webpage HTML, DOM, or text could be scraped.
2. **No Text Corroboration**: None of the candidates had surrounding article text, brand mentions, or model text.
3. **False Positive Variant Conflicts**: In candidates `[00]`, `[04]`, and `[26]`, the analyzer parsed random digit sequences embedded in the media CDN URLs (`18369579`, `19081545`, `21163337`) as conflicting model numbers, generating `Model variant conflict: target is 'LS800HD', candidate is '...'`.
4. **Exact-ID Shield Inactive**: Because no candidate had genuine `LS800HD` text corroboration from an official domain, the exact-ID shield properly did not activate.


---

## 10. Viewpoint Analysis

The current scraper assigned viewpoint labels (`ISOMETRIC`, `FRONT`, `SIDE`, `REAR`, etc.) purely based on the query angle tag (`pq.angle_tag`) rather than image analysis:
- Candidate `[00]` (painting of Radha Krishna) was labeled `ISOMETRIC` because it came from the `"ViewSonic LS800HD"` query.
- Candidate `[06]` (cricketer Shubman Gill) was labeled `ISOMETRIC`.
- Candidate `[21]` (clip-art sandals) was labeled `REAR` because it came from `"ViewSonic LS800HD" rear view`.
- Candidate `[31]` (cat line art) was labeled `FRONT` because it came from `"ViewSonic LS800HD" technical drawing dimensions`.

Viewpoint filtering played zero role in rejecting good images, because there were no good images to begin with.


---

## 11. Initial vs Fallback Comparison

| Metric | Initial Phase (Passes 1-3) | Fallback Recovery (Pass 4) |
|---|---|---|
| **Harvested Candidates** | 32 | 13 additional attempted |
| **Relevant Candidates** | 0 | 0 |
| **Accepted / Curated** | 0 | 0 |
| **Rejected by Pipeline** | 32 | All rejected / none passed |
| **DINO Range** | -0.07 to +0.09 | N/A (did not reach curation) |
| **Dominant Outcome** | `ALL_SEMANTIC_REJECTED` | Zero curated references |

Fallback repeated broad queries (`"ViewSonic" Laser Projector product photo`, etc.) using the same underlying search engine, yielding identical irrelevant web noise. Fallback did not discover better candidates.


---

## 12. Search Quality vs Filter Quality

- **SEARCH QUALITY**: **0 / 32 (0.0% Relevant)**
- **FILTER QUALITY**: **32 / 32 (100.0% Precision)** — Successfully stopped 32 noise images from corrupting the 3D reconstruction pipeline.
- **GOOD-IMAGE-REJECTION RATE**: **0.0%** (0 valid images rejected)
- **BAD-SEARCH-RESULT RATE**: **100.0%** (32 / 32 irrelevant images)

### Dominant Failure Category:
**1. SEARCH RETRIEVAL (Specifically Bing HTTP Raw HTML Scraping Fallback)**


---

## 13. Exact Root Cause

1. **Dual Search Engine Failure in HTTP Scraper**:
   - DuckDuckGo is queried via `html.duckduckgo.com/html/?q=...` which is a textual web search page, not an image search endpoint. The regex `src=\"(https?://[^\"]+)\"` looks for `<img>` tags on DuckDuckGo's page, which returns 0 images.
   - When DuckDuckGo returns 0 images, `scraper_service.py` falls back to `https://www.bing.com/images/search?q={quote(q_str)}&form=HDRSC2&first=1`.
2. **Bing Public HTTP Behavior on Exact Quoted Queries**:
   - On Bing Image Search, when a raw HTTP GET request with default headers queries a strict exact query with quotation marks (e.g. `"ViewSonic LS800HD"`), Bing's unauthenticated interface returns few or zero direct matches, but populates the response with **localized trending search cards and popular regional carousels** (in this region: Indian cricket news, Navratri festival celebrations, Hindu devotional art, etc.).
   - The scraper's regex `r'murl&quot;:&quot;(https?://[^&]+)&quot;'` matches ANY image URL embedded in the HTML response, without distinguishing between actual search results and trending/sidebar recommendations.
3. **Pipeline Downstream Consequence**:
   - 32 completely unrelated images are downloaded and fed to DINOv2.
   - DINOv2 correctly compares a ViewSonic projector against cricketers and paintings and calculates similarity ~ 0.01.
   - Because 0.01 < 0.45 and there is no exact ID text match, the pipeline rejects all 32 images.
   - The pipeline reports 0 curated references and triggers fallback.


---

## 14. What Is Working

1. **Identifier Policy**: Canonical model `LS800HD` is now correctly extracted and retained when `product_id == model_number`.
2. **Query Planning**: All 14 queries correctly incorporate `LS800HD` and pass down exact-match and viewpoint requirements.
3. **Seed Image Integrity**: The uploaded seed image is an authentic, pristine ViewSonic LS800HD laser projector reference.
4. **DINOv2 Discrimination**: DINOv2 accurately identified that paintings, cricketers, and festival dancers do not match a laser projector.
5. **Quality Protection**: The semantic and visual gates successfully protected the Pixal3D reconstruction queue from reconstructing a 3D model out of cricketers or Hindu paintings.


---

## 15. What Is Failing

1. **HTTP Image Search Scraping**: Scraping raw HTML from DuckDuckGo/Bing HTTP endpoints is completely broken for exact model searches.
2. **Indiscriminate Regex Extraction**: `murl` regex grabs trending/popular images from Bing's error/empty page rather than actual search results.
3. **Absence of Page-Level Context**: No page URL, page title, or surrounding DOM text is captured by the HTTP fallback scraper, preventing text-based identity corroboration.


---

## 16. What We Should Fix Next

> [!IMPORTANT]
> **Do NOT touch DINO thresholds. The fix MUST be in Search Retrieval.**

1. **Fix Image Search Retrieval Engine**:
   - Ensure Playwright browser scraper runs for exact searches, OR integrate a reliable image search API (such as DuckDuckGo vqd API, Bing Search API, or Google Custom Search API), OR fix the DuckDuckGo image JSON API (`https://duckduckgo.com/i.js?q=...`) instead of the broken `html.duckduckgo.com` text endpoint.
2. **Validate Search Result Context**:
   - Verify that scraped images originate from actual result containers (`.iusc`, `imgpt`) rather than Bing's trending carousel or sidebar suggestions.
3. **Relax Strict Quotes if Yielding Zero Results**:
   - If `"ViewSonic LS800HD"` yields zero exact hits on a search engine, try `ViewSonic LS800HD` (unquoted) to allow search engines to match documents where the words appear in proximity.


---

## 17. What We Should NOT Change

1. **DO NOT LOWER THE DINO THRESHOLD (0.45)**: Lowering the threshold to 0.05 would have caused Yatzar to accept paintings of Radha and Krishna and photos of Shubman Gill as approved 3D reference angles for a ViewSonic Laser Projector.
2. **DO NOT REMOVE VISUAL CONSISTENCY GATES**: The visual cross-verification against the seed image is working flawlessly as a fraud/noise shield.
3. **DO NOT CHANGE IDENTIFIER POLICY**: The identifier policy fix is working correctly.
4. **DO NOT REPLACE THE SEED IMAGE**: The seed image is a valid, high-resolution ViewSonic LS800HD image.


---

## 18. Raw Measurements

```json
{
  "job_id": "res-job-d4411f64",
  "product_id": "LS800HD",
  "status": "COMPLETED",
  "failure_mode": "ALL_SEMANTIC_REJECTED",
  "total_harvested": 45,
  "downloaded_candidates": 32,
  "prefilter_accepted": 32,
  "curated_accepted": 0,
  "dino_similarity_stats": {
    "min": -0.07,
    "max": 0.09,
    "mean": 0.0119,
    "median": 0.01,
    "threshold": 0.45
  },
  "timings_ms": {
    "search_and_harvest_ms": 4909,
    "download_ms": 21787,
    "prefilter_ms": 341,
    "dinov2_extraction_ms": 1030,
    "semantic_verification_ms": 39,
    "reference_pool_curation_ms": 6,
    "total_pipeline_ms": 31759
  }
}
```


---

## 19. Draft Reply to Both Supervisors

```markdown
Supervisors,

We have completed the strict read-only candidate-evidence diagnostic for the ViewSonic LS800HD research run following the identifier-policy fix.

EXECUTIVE CONCLUSION:
The 0-candidate result is NOT caused by filtering rejecting good product images.
The search results themselves were 100% wrong/irrelevant.

KEY EVIDENCE:
- 32 candidates were harvested and inspected individually.
- Genuinely relevant LS800HD images: 0 / 32 (0.0%).
- Good images rejected: 0 / 32 (0.0%).
- Bad search results harvested: 32 / 32 (100.0%).
- Retrieved images consisted of: paintings of Radha & Krishna, photos of cricketer Shubman Gill, anime Goku figurines, Islamic prayer videos, Navratri festival cards/dancers, clip-art flip-flops, press conference photos, pharmacology slides, and cartoon cat sketches.
- DINOv2 similarities ranged from -0.07 to +0.09 (mean +0.01) against the authentic seed image of the ViewSonic laser projector.
- DINO and semantic filters correctly rejected all 32 noise images from corrupting the reconstruction pipeline.

ROOT CAUSE:
The fast HTTP scraper queries DuckDuckGo HTML (which returns 0 images for image search) and falls back to unauthenticated Bing HTTP scraping. On strict quoted queries like '"ViewSonic LS800HD"', Bing's public endpoint returns 0 exact matches and renders localized trending suggestions. The scraper's regex matched those trending carousel images.

RECOMMENDATION:
DO NOT lower DINO thresholds (0.45 is functioning correctly).
Fix the search retrieval harvest layer so actual product image search results are retrieved.
```