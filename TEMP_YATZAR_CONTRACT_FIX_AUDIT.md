# Master Audit Report: Contract & State Bug Fixes (Bug 1 & Bug 2)

**Document:** `TEMP_YATZAR_CONTRACT_FIX_AUDIT.md`  
**Date:** 2026-10-12  
**Target:** Live Contract & State Fix Audit across Backend & Frontend  
**Audience:** Both Technical Supervisors  
**Status:** IMPLEMENTED, REGRESSION-TESTED & LIVE-VERIFIED ON RTX 4060 GPU  

---

## 1. Executive Summary

During the previous read-only live trace (`TEMP_YATZAR_RESEARCH_AND_3D_FAILURE_TRACE.md`), two distinct contract and state disconnection bugs were proven:
1. **Bug 1 (Reconstruction Status Contract Collision):** When Pixal3D successfully produced a watertight 3D mesh (`.glb`), `GET /api/reconstruct/status/<id>` merged `status_dict["result"]` into `resp_data`, allowing mesh metadata `result.status = "MODEL_READY"` to overwrite the top-level job lifecycle status `status = "COMPLETED"`. Because `ProductContext.jsx` specifically polls for `res.status === "COMPLETED"`, the frontend never acknowledged completion, and the generated GLB was ignored.
2. **Bug 2 (Research Candidate UI State Disconnect):** In `ScrapeStage.jsx`, candidate gallery tabs and cards were initialized exclusively from `activeProduct.scrapedImages` (the curated pool). When research evaluated 39 candidates and rejected 27 (with 0 surviving curation, e.g. for *Mahr MarSurf PS 10*), the UI displayed `All Candidates (0)`, `Verified (0)`, `Rejected (0)` despite `activeProduct.rejectedImages` holding 27 rejected candidates.

**Implementation Status:**
- **Bug 1:** Fixed in `backend/app.py` and `frontend/src/context/ProductContext.jsx`. Canonical job lifecycle status (`COMPLETED`, `QUEUED`, `RUNNING`/`RECONSTRUCTING`, `FAILED`, `CANCELLED`) is strictly preserved at the top level and never overwritten by `result.status`. Polling cleanly recognizes `COMPLETED`, stores `modelUrl`/`model_3d`, and renders the GLB in `ThreeCADViewer`.
- **Bug 2:** Fixed in `frontend/src/components/stages/ScrapeStage.jsx`. Candidate counts and tabs are now completely truthful: `All Candidates` displays all evaluated candidates, `Verified` displays curated candidates eligible for 3D approval, and `Rejected` displays rejected candidates with non-selectable badges and explicit rejection reasons. Rejected images cannot be selected or approved as 3D references.
- **Search Logic Untouched:** As strictly mandated, search harvesting (`scraper_service.py`, Bing/DDG extraction, DINO thresholds, query planning) was **not** touched and remains the next isolated milestone.

---

## 2. Bug 1 — Reconstruction Status Contract

### Previous Behavior
1. Frontend enqueued reconstruction via `POST /api/reconstruct/queue`.
2. Pixal3D completed inference on RTX 4060, generated a real `.glb`, and set `job.status = "COMPLETED"` and `job.result = {"status": "MODEL_READY", ...}`.
3. `GET /api/reconstruct/status/<id>` constructed `resp_data = {"status": "COMPLETED", ...}`, but executed `resp_data.update(status_dict["result"])`.
4. Because `result` contains `"status": "MODEL_READY"`, the top-level `resp_data["status"]` became `"MODEL_READY"`.
5. `ProductContext.jsx` checked `if (res.status === 'COMPLETED')`, which evaluated to `false`. Polling looped indefinitely or timed out, discarding the generated model.

### Root Cause
Unrestricted dictionary unpacking (`resp_data.update(status_dict["result"])`) in `get_reconstruct_status()` without enforcing job lifecycle precedence over mesh metadata status.

### Exact Files & Functions
- **Backend File:** [backend/app.py](file:///e:/SANJAY/YatzarCreations/Yatzar-Manage-AI/backend/app.py)
  - `get_reconstruct_status(product_or_job_id)`
  - `enqueue_reconstruction()`
- **Frontend File:** [frontend/src/context/ProductContext.jsx](file:///e:/SANJAY/YatzarCreations/Yatzar-Manage-AI/frontend/src/context/ProductContext.jsx)
  - Polling loop inside `useEffect` (lines 484–520)

### Fix
In `backend/app.py`:
```python
resp_data = {
    "success": True,
    "job": status_dict,
    "status": canonical_status,
    "queue_position": status_dict.get("queue_position", 0)
}
if canonical_status == ReconstructionStatus.COMPLETED.value and status_dict.get("result"):
    result_payload = dict(status_dict["result"])
    resp_data.update(result_payload)
    # CANONICAL STATUS GUARANTEE:
    # Result metadata contains {"status": "MODEL_READY"}, but top-level lifecycle
    # status MUST remain the canonical job status (COMPLETED).
    resp_data["status"] = ReconstructionStatus.COMPLETED.value
    resp_data["result"] = result_payload
```
In `frontend/src/context/ProductContext.jsx`:
- The polling loop recognizes `res.status === 'COMPLETED'` and extracts `modelUrl` from `res.model_url || res.result?.model_url`.
- Sets `modelUrl`, `model_3d`, `meshStats`, and preserves `meshStatus: res.result?.status || 'MODEL_READY'`.
- Updates `reconstructionJobs` so the product transitions to terminal state and polling stops immediately.

### API Contract After Fix
```json
{
  "success": true,
  "status": "COMPLETED",
  "queue_position": 0,
  "model_url": "http://127.0.0.1:5000/cache/models/TEST-LIVE-AUDIT-01_pixal3d_1791818018298.glb",
  "model_path": "E:\\SANJAY\\YatzarCreations\\Yatzar-Manage-AI\\backend\\cache\\models\\TEST-LIVE-AUDIT-01_pixal3d_1791818018298.glb",
  "generation_time_sec": 3.917,
  "mesh_stats": {
    "vertex_count": 60530,
    "face_count": 120988,
    "watertight": true
  },
  "result": {
    "status": "MODEL_READY",
    "model_url": "http://127.0.0.1:5000/cache/models/TEST-LIVE-AUDIT-01_pixal3d_1791818018298.glb",
    "mesh_stats": { "vertex_count": 60530, "face_count": 120988, "watertight": true }
  },
  "job": {
    "job_id": "rec-job-5c82d20d",
    "status": "COMPLETED"
  }
}
```

---

## 3. Bug 2 — Research Candidate UI State

### Previous Behavior
- When research completed, `ProductContext.jsx` set:
  - `activeProduct.scrapedImages` = curated candidates (survived filtering)
  - `activeProduct.rejectedImages` = rejected candidates (failed filtering)
- `ScrapeStage.jsx` built its state and gallery tabs strictly from `images = activeProduct.scrapedImages || []`.
- When `scrapedImages` had 0 items, all tabs reported 0: `All Candidates (0)`, `Verified (0)`, `Rejected (0)`.
- The user was presented with an empty gallery even though 27 candidates had been downloaded and evaluated.

### Root Cause
`ScrapeStage.jsx` completely ignored `activeProduct.rejectedImages` in its tab counts, gallery rendering, and empty-state evaluations.

### Exact Files & Functions
- **Frontend File:** [frontend/src/components/stages/ScrapeStage.jsx](file:///e:/SANJAY/YatzarCreations/Yatzar-Manage-AI/frontend/src/components/stages/ScrapeStage.jsx)
  - Candidate pool memoization (lines 33–50)
  - Summary metrics computation (lines 55–65)
  - Tab counts and filter logic (lines 235–270)
  - Candidate card rendering and proceed button disable state (lines 280–400)

### Fix & Candidate-Count Semantics
1. **Explicit Separation of Pools:**
   - `curatedImages = activeProduct?.scrapedImages || []` (eligible for 3D approval)
   - `rejectedImages = (activeProduct?.rejectedImages || []).map(...)` (rejected by pipeline)
2. **Truthful Tab Counts:**
   - `All Candidates`: `curatedImages.length + rejectedImages.length`
   - `Verified`: `curatedImages.length`
   - `Rejected`: `rejectedImages.length`
3. **Card Rendering:**
   - Curated cards: Rendered with `Verified` badge and selectable for reference.
   - Rejected cards: Rendered with red `Rejected` badge, dimmed styling, `Non-selectable (Rejected by Research)` tag, and explicit rejection reason (`Reason: LOW_VISUAL_SIMILARITY`, etc.).
4. **Approval Safety:**
   - Rejected candidates can **never** be selected as an approved reference.
   - If `curatedImages.length === 0`, `Proceed to Image Approval` button is disabled (`disabled={curatedImages.length === 0 || isRunning}`).
   - An informative alert banner informs the user that all candidates were rejected by evidence thresholds and cannot be used for 3D reconstruction.

---

## 4. Cache Behavior

- **What Remains:**
  - Persisted background research jobs in `backend/cache/jobs/` (e.g. `research_6910232.json`, `research_LS800HD.json`).
  - Candidate images in `backend/cache/candidates/`.
  - Generated GLB binary assets in `backend/cache/models/`.
- **What Does Not Remain:**
  - No stale hardcoded responses or bypasses.
- **Fresh Reconstruction Preserved:**
  - Every explicit user request to `POST /api/reconstruct/queue` enqueues a fresh serialized job to the GPU queue.
  - The Pixal3D engine re-evaluates the approved conditioning image, runs neural inference on CUDA (`cuda:0`), extracts a fresh watertight mesh, and returns fresh telemetry.
  - No persistent reconstruction result reuse is introduced.

---

## 5. Test Results

### 1. Reconstruction Lifecycle & Canonical Contract Test Suite
File: [backend/tests/test_lifecycle_and_queue.py](file:///e:/SANJAY/YatzarCreations/Yatzar-Manage-AI/backend/tests/test_lifecycle_and_queue.py)
```
Ran 14 tests in 2.548s
OK
```
Tests passed:
- `test_01_job_creation_and_initial_status`
- `test_02_job_completion_with_results`
- `test_03_job_failure_handling`
- `test_04_job_cancellation`
- `test_05_concurrent_research_jobs`
- `test_06_stage_timeouts`
- `test_07_in_memory_and_cache_retrieval`
- `test_08_retry_failed_job`
- `test_09_reconstruction_queue_serialized_one_at_a_time`
- `test_10_approved_reference_preservation`
- `test_11_cancel_queued_reconstruction`
- `test_12_completion_persists_after_reload`
- `test_13_reconstruction_status_canonical_contract` (NEW REGRESSION PROOF)
- `test_14_lifecycle_statuses_not_overwritten_by_metadata` (NEW REGRESSION PROOF)

### 2. Research Correctness Tests
File: [backend/tests/test_research_correctness.py](file:///e:/SANJAY/YatzarCreations/Yatzar-Manage-AI/backend/tests/test_research_correctness.py)
```
Ran 8 tests in 0.022s
OK
```

### 3. Frontend Production Build
```
vite v8.3.0 building client environment for production...
built in 1.57s
0 errors
```

---

## 6. Live 3D Validation (Real RTX 4060 GPU Execution)

- **Target Product:** Mahr MarSurf PS 10 Test (`TEST-LIVE-AUDIT-01`)
- **Reference Image:** `backend/cache/candidates/cand_14c3cd5f54c5.jpg`
- **Engine:** Pixal3D (TencentARC)
- **Job ID:** `rec-job-5c82d20d`
- **State Transitions Observed:**
  - `t=0.00s`: Enqueued via `POST /api/reconstruct/queue` -> `QUEUED` (HTTP 202)
  - `t=1.85s`: GPU slot acquired -> `RECONSTRUCTING`
  - `t=23.00s`: PyTorch/CUDA neural pipeline initialized on `cuda:0`
  - `t=26.91s`: Neural inference + marching cubes watertight extraction complete
  - `t=29.46s`: Job status transition -> `COMPLETED`
- **API Status Contract Check:**
  - `response.status` = `"COMPLETED"` (CANONICAL)
  - `response.job.status` = `"COMPLETED"`
  - `response.result.status` = `"MODEL_READY"`
  - `response.model_url` = `http://127.0.0.1:5000/cache/models/TEST-LIVE-AUDIT-01_pixal3d_1791818018298.glb`
- **Generated 3D Asset Telemetry:**
  - **Triangles:** 120,988
  - **Vertices:** 60,530
  - **Euler Characteristic:** 36
  - **Is Watertight:** True
  - **GLB File Size:** 2,421,328 bytes (~2.36 MB)
  - **Backend Neural Inference Duration:** 3.917s
- **Frontend Three.js Load & Visible Rendering:**
  - ProductContext stored `modelUrl` and `meshStats`.
  - `Generate3DStage.jsx` received `modelUrl`.
  - `ThreeCADViewer` loaded the binary GLB, generated the 3D viewport canvas, and rendered the model with lighting, orbit controls, and wireframe options.
  - Confirmed via live browser capture: `final_state_1791818475211.png`.

---

## 7. Live Research UI Validation

- **Target Product:** Mahr MarSurf PS 10 (Article Number: 6910232)
- **Backend Research State:**
  - Total Retrieved: 41
  - Duplicates Removed: 0
  - Rejected as Irrelevant: 32
  - Verified Candidates: 0
  - Best Reference: `null`
- **Frontend ScrapeStage UI Verification:**
  - **Summary Metrics Header:** Total Retrieved: 41, Duplicates Removed: 0, Rejected as Irrelevant: 32, Verified Candidates: 0, Selected Reference: 0.
  - **Tabs Rendered:**
    - `All Candidates (32)`
    - `Verified (0)`
    - `Rejected (32)`
  - **Gallery View:**
    - All 32 rejected candidate cards rendered with red `Rejected` badge and `Non-selectable (Rejected by Research)`.
    - Specific rejection reasons visible on every card (`Reason: LOW_VISUAL_SIMILARITY`).
    - Proceed to Image Approval button disabled (`disabled`).
  - Confirmed via live browser capture: `scrape_stage_verification_1791818382565.png`.

---

## 8. Files Changed

1. [backend/app.py](file:///e:/SANJAY/YatzarCreations/Yatzar-Manage-AI/backend/app.py):
   - Enforced canonical lifecycle status (`COMPLETED`) in `get_reconstruct_status()` and `enqueue_reconstruction()`, preventing overwrite by `result.status = "MODEL_READY"`.
2. [backend/tests/test_lifecycle_and_queue.py](file:///e:/SANJAY/YatzarCreations/Yatzar-Manage-AI/backend/tests/test_lifecycle_and_queue.py):
   - Added `test_13_reconstruction_status_canonical_contract` proving `response.status == "COMPLETED"`.
   - Added `test_14_lifecycle_statuses_not_overwritten_by_metadata` proving all lifecycle states are preserved.
3. [frontend/src/context/ProductContext.jsx](file:///e:/SANJAY/YatzarCreations/Yatzar-Manage-AI/frontend/src/context/ProductContext.jsx):
   - Updated polling loop to extract `modelUrl` from `res.model_url || res.result?.model_url` and persist `model_3d`, `meshStats`, and `meshStatus`.
4. [frontend/src/components/stages/ScrapeStage.jsx](file:///e:/SANJAY/YatzarCreations/Yatzar-Manage-AI/frontend/src/components/stages/ScrapeStage.jsx):
   - Integrated `curatedImages` and `rejectedImages` into truthful candidate counts, tabs, and gallery cards. Disabled proceed when curated pool is empty and marked rejected candidates non-selectable.

---

## 9. Search Issue Still Remaining

**CRITICAL NOTICE:**  
In strict compliance with instructions, **search harvesting was NOT modified in this task**.
- The search retrieval issue identified in `TEMP_VIEWSONIC_CANDIDATE_EVIDENCE_AUDIT.md` (where Bing returns irrelevant thumbnail collections for specific industrial part numbers) remains the next independent blocker.
- DINO thresholds and semantic validation logic were intentionally left intact.

---

## 10. Remaining Limitations

1. **Search Harvesting Quality for Niche Hardware:** Because Bing/DDG harvesting returns general manufacturer branding or unrelated trending images, niche hardware items (e.g. Mahr MarSurf PS 10, ViewSonic LS800HD) correctly yield 0 verified candidates under DINO validation.
2. **Seed Image Dependency:** In the absence of verified search results, 3D reconstruction currently relies on user-provided seed images or curated local references until search harvesting is overhauled.

---

## 11. Next Yatzar Milestone

**Milestone: Robust Multi-Engine Search Retrieval & Datasheet Direct Harvesting**
- Enhance search harvesting in `scraper_service.py` to extract high-resolution product photography directly from manufacturer specification sheets and verified distributor domains.
- Eliminate dependency on consumer image engine trending thumbnails.

---

## 12. Draft Reply to Both Supervisors

```markdown
Dear Supervisors,

We have implemented and verified the two proven contract/state bugs identified in the live trace:

1. Bug 1 (Reconstruction Status Contract Collision):
   - Root Cause: Unpacking status_dict["result"] overwrote top-level status="COMPLETED" with result.status="MODEL_READY", causing ProductContext polling to ignore completed reconstructions.
   - Fix: Backend GET /api/reconstruct/status/<id> now strictly preserves the canonical job lifecycle status ("COMPLETED") at the top level while retaining "MODEL_READY" within result metadata. ProductContext polls for COMPLETED, extracts the model URL, and displays the GLB.
   - Regression Test: Added test_13 and test_14 to test_lifecycle_and_queue.py. All 14 tests pass.
   - Live Validation on RTX 4060: Tested end-to-end. Pixal3D completed inference in 3.917s, exported a 120,988-triangle watertight GLB (2.42 MB), and ThreeCADViewer visibly rendered the 3D model in the browser.

2. Bug 2 (Research Candidate UI State Disconnect):
   - Root Cause: ScrapeStage.jsx derived its gallery and tabs strictly from activeProduct.scrapedImages, ignoring activeProduct.rejectedImages.
   - Fix: ScrapeStage.jsx now consumes both pools with truthful semantics: All Candidates (32), Verified (0), Rejected (32). Rejected cards are displayed with clear "Non-selectable (Rejected by Research)" badges and rejection reasons. The user cannot approve rejected candidates, and Proceed to Image Approval is disabled when 0 candidates pass verification.

Search harvesting was intentionally untouched as instructed and remains the next research blocker.

Detailed audit report and live screenshots: TEMP_YATZAR_CONTRACT_FIX_AUDIT.md
```
