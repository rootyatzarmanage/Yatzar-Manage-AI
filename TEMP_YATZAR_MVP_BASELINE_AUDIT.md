# YATZAR MVP PRODUCTION BASELINE AUDIT

**Baseline Date:** October 15, 2026  
**Git Branch:** `Sanjay-R`  
**Baseline Git Tag:** `v0.1.0-pixal3d-mvp`  
**Baseline Commit Hash:** `3dafa0a5772768feb48246f056fe940a457a1151` (Pre-audit record)  
**System Platform:** Windows 11 / NVIDIA GeForce RTX 4060 Laptop GPU (8 GB VRAM) / 16 GB System RAM  
**Project:** Yatzar Manage AI (`e:\SANJAY\YatzarCreations\Yatzar-Manage-AI`)  
**Status:** **FROZEN & VERIFIED MVP BASELINE**

---

## 1. Executive Summary & Purpose

This document freezes the current Yatzar state as the project's first verified production MVP baseline. This baseline serves as the official, known-good rollback point for all future development.

The verified capabilities preserved in this baseline:
1. **Official TencentARC Pixal3D** is the SOLE active production reconstruction engine.
2. **Pixal3D 1536 Cascade Resolution** (Stages 2, 3a, 3b, 4) with Flexible Dual Grid (FDG) 2048x2048 PBR texture synthesis.
3. **Low-VRAM CPU/RAM Offloading** (<5.8 GB peak VRAM on an 8 GB RTX 4060 GPU).
4. **Three.js "Throw Light"** viewer inspection rig with interactive ON/OFF and intensity controls (0.5x – 3.5x).
5. **Complete TripoSR Eradication**: zero TripoSR production code, zero TSR imports, zero TripoSR dependencies, and deletion of obsolete `tools/triposr_poc`.
6. **Robust Multi-Pass Research & Harvesting**: DINOv2 visual deduplication, brand/SKU query planning, and candidate scoring.
7. **Serialized GPU Queue**: Single-slot GPU reconstruction lock preventing VRAM exhaustion or CUDA thrashing.
8. **Verified ViewSonic LS800HD Asset**: High-density 12.3 MB watertight/near-watertight GLB asset with 256,360 vertices and 299,972 faces.

---

## 2. Production Engine Architecture & Path

The verified end-to-end execution path is strictly:

```
[React Frontend]
  │
  ├── Stage 0 (InputStage): Product Identity Entry (Brand, Model, SKU, Dimensions)
  │
  ├── Stage 1 (ScrapeStage): Multi-Pass Research & Candidate Harvesting
  │     └── DINOv2 Visual Deduplication + Geometric Uncertainty Ranking
  │
  ├── Stage 2 (ImageApprovalStage / ReferenceSheetStage):
  │     └── Human/Auto Reference Selection (Approved 2D image)
  │
  ├── Stage 3 (Generate3DStage):
  │     └── POST /api/reconstruct/queue (Payload: {"engine": "Pixal3D", ...})
  │           │
  │           ▼
  │     [ProductContext.jsx / api.js]
  │           │
  │           ▼
  │     [Flask API Route: POST /api/reconstruct/queue (`backend/app.py`)]
  │           │
  │           ▼
  │     [ReconstructionQueueManager (`backend/services/job_manager.py`)]
  │           └── Acquires Serialized GPU Lock (Concurrency = 1)
  │           │
  │           ▼
  │     [ReconstructionService (`backend/services/reconstruction_service.py`)]
  │           └── Unconditionally routes to Pixal3DEngine
  │           │
  │           ▼
  │     [Pixal3DProductionAdapter (`backend/services/pixal3d_adapter.py`)]
  │           │
  │           ├── MoGe-2 Camera Intrinsics & Extrinsics Estimation
  │           ├── Low-VRAM CPU Weight Offload (Models reside in RAM, stream to CUDA)
  │           ├── Sparse Structure DiT (12 steps)
  │           ├── Shape 512 DiT (12 steps)
  │           ├── High-Resolution Shape 1536 DiT (12 steps)
  │           ├── Texture 1536 DiT (12 steps)
  │           ├── In-Place Sparse Residual Addition (Eliminates 1.55 GiB VAE spike)
  │           ├── Pre-CuMesh Garbage Collection & CUDA Cache Clear
  │           └── Flexible Dual Grid (FDG) + 2048x2048 PBR UV Texture Baking
  │           │
  │           ▼
  │     [Binary GLB Asset Output (`backend/cache/models/<ID>_pixal3d_<HASH>_<TS>.glb`)]
  │
  └── Stage 4 (Approval3DStage / ThreeCADViewer.jsx):
        ├── Serves via GET /api/models/<filename>
        ├── Three.js OrbitControls + ACESFilmic Tone Mapping
        ├── Camera Presets: Front, Side, Rear, Iso, Top
        ├── Wireframe Inspection Mode
        └── Throw Light Inspection Rig (Camera-Mounted Key + Neutral Ambient Lift)
```

---

## 3. Three.js "Throw Light" Implementation

### Location
- File: `frontend/src/components/viewport/ThreeCADViewer.jsx`

### Behavior
- **Inspection Problem Solved:** Dark and black industrial products (e.g. projectors, monitors, servers, heat exchangers, black plastics) were previously difficult to inspect against dark slate viewer backgrounds.
- **Client-Side Only:** Pure presentation enhancement; zero alterations to underlying GLB geometry, PBR materials, UV textures, or backend reconstruction parameters.
- **Lighting Rig:**
  - Neutral white camera-mounted inspection key light (`THREE.DirectionalLight(0xffffff)` at camera coordinate `(1.2, 1.8, 1.8)`). Because it is attached directly to `camera`, it tracks the inspector's viewpoint across any orbit angle.
  - Neutral ambient lift (`THREE.HemisphereLight(0xffffff, 0x1e293b)`).
- **Controls:**
  - Clearly visible standalone button in top-right viewport overlay: `[Flashlight] Throw Light ON/OFF`.
  - When enabled, button turns active amber (`bg-amber-500/25 border-amber-500/50`) and exposes an adjacent intensity pill.
  - Interactive range slider from `0.5x` to `3.5x` (default: `1.8x`) with live numeric readout.
- **Verification:**
  - Verified via Playwright headless browser automation (`backend/scratch/verify_viewer_throw_light.py`):
    - WebGL Canvas mounted: `1`
    - Asset Load Error: `False`
    - Throw Light toggled OFF -> ON successfully.
    - Intensity slider appeared and updated smoothly from `1.8x` to `2.5x`.
    - Camera view angle presets (Front, Side, Iso) and Wireframe mode confirmed responsive and non-regressed.

---

## 4. TripoSR Complete Eradication Audit

| Area | Status | Verification Proof |
| :--- | :--- | :--- |
| **Production Runtime Imports** | **ZERO** | `tsr` and `tsr.system` absent from `sys.modules`; zero TSR imports in `backend/` |
| **ReconstructionService** | **ZERO** | `self.pixal3d_engine` active; `hasattr(service, 'triposr_engine') == False` |
| **Backend Dependencies** | **CLEAN** | `backend/requirements.txt` contains only Flask, PyTorch, PIL, OpenCV, trimesh |
| **Frontend UI / Stepper** | **ZERO** | No TripoSR buttons, labels, or engine selectors exist in active UI |
| **Legacy Request Routing** | **INTERCEPTED** | Legacy requests with `engine="TripoSR"` are logged and routed strictly to Pixal3D |
| **Obsolete POC Folder** | **REMOVED** | `tools/triposr_poc` completely deleted; benchmark data saved to `reports/` |
| **Historical Evidence** | **ISOLATED** | Historical benchmark JSON preserved in `reports/triposr_historical_benchmark_result.json` |

---

## 5. Research & Scraping Pipeline Baseline

### Validated Components
1. **Identifier Policy:** `backend/services/identifier_policy.py` strictly prevents internal IDs (e.g. `PROD-01`, `PROD-IPHONE-08`, UUIDs) from leaking into external search queries while preserving OEM part numbers (e.g. `LS800HD`, `AL-HEX-9000`, `43218000`).
2. **Query Planner:** `backend/services/query_planner.py` generates up to 14 structured multi-pass search queries across 4 distinct passes (Exact/SKU, Viewpoints, Technical Drawings, Category contexts).
3. **Scraper Harvesting:** Both BeautifulSoup and Playwright extract candidate images, deduplicate identical URLs, and download high-resolution candidates.
4. **DINOv2 Deduplication & Scoring:** Visual feature vectors extracted via `dinov2_vits14` on CUDA, computing cosine similarities against seed images and removing visual duplicates.
5. **Image Approval Handoff:** Selected or best-reference image is passed directly into the 3D generation queue without losing image fidelity.

---

## 6. Verification Suite Results

### Frontend
- **Command:** `npm run build` (in `frontend/`)
- **Result:** Vite v8.3.0 built client environment for production in 1.50s with zero errors (`dist/` generated cleanly).

### Backend Regression Tests
- **`tests/test_pixal3d_production_integration.py`:**
  - Ran 5 tests in 0.164s — **5/5 PASSED (OK)**
- **`tests/test_identifier_policy.py`:**
  - Ran 10 tests in 0.009s — **10/10 PASSED (OK)**
- **`backend/tests/test_research_correctness.py`:**
  - Ran 8 tests in 0.017s — **8/8 PASSED (OK)**
- **`backend/tests/test_scraper_harvesting.py`:**
  - Ran 6 tests in 0.223s — **6/6 PASSED (OK)**
- **`backend/tests/test_lifecycle_and_queue.py`:**
  - Ran 14 tests in 1.047s — **14/14 PASSED (OK)**

### Total Passing Unit Tests: 43 / 43 (100% Pass Rate)

---

## 7. Known-Good ViewSonic E2E Reconstruction Evidence

- **Product:** ViewSonic LS800HD 5000 Lumens 1080p Laser Installation Projector
- **Input Image:** `backend/cache/candidates/verified_4d28321d64f4.jpg`
- **Output Asset:** `backend/cache/models/PROD-VIEWSONIC-E2E-1791979082_pixal3d_07c12b87_1791979084692.glb`
- **Asset Size:** 12.31 MB (12,611,868 bytes)
- **Vertex Count:** 256,360
- **Face Count:** 299,972
- **Mesh Validation:** `valid: True`, `high_density_surface: True`, `quality_score: 0.98`
- **HTTP Serving Verification:** HTTP 200 OK via `/api/models/PROD-VIEWSONIC-E2E-1791979082_pixal3d_07c12b87_1791979084692.glb`
- **Viewer Rendering:** Verified in Three.js WebGL canvas with active Throw Light inspection.

---

## 8. Startup Commands for Reproducing MVP

### Terminal 1: Backend Service
```powershell
cd e:\SANJAY\YatzarCreations\Yatzar-Manage-AI\backend
.\venv\Scripts\python.exe app.py
```
- Listens on `http://127.0.0.1:5000`
- Health check: `http://127.0.0.1:5000/api/health`

### Terminal 2: Frontend Dev Server
```powershell
cd e:\SANJAY\YatzarCreations\Yatzar-Manage-AI\frontend
npm run dev
```
- Serves on `http://127.0.0.1:3000`

---

## 9. Exact Rollback Command

To return the entire repository to this verified baseline at any point in the future:

```bash
git checkout v0.1.0-pixal3d-mvp
```

Or to hard-reset the working branch to this baseline:

```bash
git reset --hard v0.1.0-pixal3d-mvp
```

---

## 10. Known Limitations

1. **Reconstruction Latency:** Full 1536 cascade neural inference on an 8 GB RTX 4060 Laptop GPU takes ~15 to 16 minutes per product due to the heavy 4-stage DiT pipeline and host RAM offloading.
2. **Initial Weight Download:** If Hugging Face cache (`~/.cache/huggingface/hub`) is cleared, the initial run requires downloading ~14 GB of neural network weights (`TencentARC/Pixal3D`, `Ruicheng/moge-2-vitl`, `camenduru/dinov3-vitl16-pretrain-lvd1689m`).
3. **Serialized Queue:** Concurrency is intentionally capped at 1 to prevent GPU OOM on consumer 8 GB GPUs. Additional requests queue gracefully with live queue position telemetry.
4. **Live Web Scraping Variability:** External websites (Google Images, DuckDuckGo, OEM sites) occasionally apply rate limiting, which the 4-pass query fallback mitigates, but network timeouts can occur if offline.
