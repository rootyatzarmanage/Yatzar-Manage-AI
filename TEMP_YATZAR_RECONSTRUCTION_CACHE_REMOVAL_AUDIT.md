# TEMP YATZAR RECONSTRUCTION CACHE REMOVAL AUDIT

**Branch:** `Sanjay-R`  
**Date:** 2026-10-13  
**Status:** COMPLETE & VERIFIED  
**Deliverable Type:** Temporary Supervisor-Facing Audit Document (DO NOT COMMIT)

---

## 1. Repository / Cache Audit

A repository-wide audit was conducted across the codebase to identify every caching mechanism, distinguishing strictly between:
1. **Reconstruction / Model-Output Cache:** Generated `.glb` models, meshes, or completion states reused between requests (TARGET FOR COMPLETE REMOVAL).
2. **Research / Download Cache:** Candidate image downloads, scraping outputs, DINO feature caches, and research job logs (`backend/cache/candidates/`, `backend/cache/jobs/`, `backend/cache/uploads/`) (STRICTLY PRESERVED).
3. **Runtime Ephemeral Output:** Necessary request-scoped output paths served via HTTP to the 3D viewer (`backend/cache/models/`), which must function purely as an ephemeral output sink without indexing, hashing, or reuse.
4. **Resident GPU Model Weights:** `tsr.system.TSR` weights resident in GPU memory (RTX 4060 Laptop GPU) across calls for low-latency neural inference (PRESERVED).

### Files Inspected:
- `backend/services/reconstruction_service.py`
- `backend/services/job_manager.py`
- `backend/app.py`
- `frontend/src/components/stages/Generate3DStage.jsx`
- `frontend/src/components/stages/Approval3DStage.jsx`
- `frontend/src/components/stages/ImageApprovalStage.jsx`
- `frontend/src/components/stages/ReferenceSheetStage.jsx`
- `frontend/src/services/api.js`
- `tests/test_reconstruction_and_reference_selection.py`
- `backend/tests/test_lifecycle_and_queue.py`

---

## 2. Reconstruction-Cache Mechanisms Found

The initial audit uncovered several reconstruction-output caching artifacts:

| # | Location | Mechanism Found | Impact Before Removal |
|---|----------|-----------------|------------------------|
| 1 | `backend/services/reconstruction_service.py` | Docstrings referencing MD5 hash-based GLB lookup ("Checks cache for existing generated model (MD5-based filename)") | Documented an explicit intent to reuse models by image hash |
| 2 | `backend/services/reconstruction_service.py` | `is_cache_hit = False` and `result["cache_hit"] = False` flags across `Pixal3DEngine`, `TripoSREngine`, and `Pixel3DEngine` | Exposed cache status in API and internal signatures |
| 3 | `backend/services/job_manager.py` | `"cache_hit": result.get("cache_hit", False)` in `ReconstructionJob.result` payload | Propagated cache hit indicators to queue consumers |
| 4 | `backend/app.py` (lines 547-558) | Completion short-circuit: `if job.status == ReconstructionStatus.COMPLETED.value and job.result: return jsonify(...)` | Attempting to enqueue an existing job or product ID short-circuited to previously completed results instead of returning a fresh 202 Queued job |
| 5 | `backend/cache/models/` | Predictable naming structure (`{safe_id}_{engine}_{timestamp}.glb`) without request-token association | Potential for collision or retention of superseded models across iterations |
| 6 | `frontend/src/components/stages/ImageApprovalStage.jsx` (line 97) | Code comment referencing `cached model stats` | Contained misleading cache terminology |

---

## 3. Files Changed

1. **`backend/services/reconstruction_service.py`**:
   - Re-scoped `MODELS_CACHE_DIR` to `MODELS_OUTPUT_DIR = Path(...) / "cache" / "models"`, explicitly designating it as an ephemeral runtime output sink (not a cache). Maintained `MODELS_CACHE_DIR = MODELS_OUTPUT_DIR` alias for backward-compatible imports.
   - Introduced global and engine-level `self.call_count = 0` counters, incremented on every neural inference run (`reconstruct_from_image`, `TripoSREngine.generate_mesh`, `Pixel3DEngine.generate_mesh`).
   - Implemented unique per-request naming containing a random UUID token and timestamp: `{safe_id}_{engine_tag}_{uuid4[:8]}_{timestamp_ms}.glb`.
   - Added `_cleanup_superseded_models(safe_id, keep_latest_n=1)` to automatically purge old temporary GLBs on subsequent runs for the same asset.
   - Completely eradicated `is_cache_hit` parameter from return signatures and helper methods; removed `result["cache_hit"]` across all engines.
   - Added `call_count`, `inference_call_count`, and `request_token` to all reconstruction output dictionaries.
   - Updated execution telemetry logging: `EXECUTION: FRESH NEURAL INFERENCE (Call #{self.call_count})`.

2. **`backend/services/job_manager.py`**:
   - Removed `"cache_hit"` from `ReconstructionJob.result` dictionary.
   - Added `"call_count"` and `"request_token"` to `ReconstructionJob.result`.
   - Added `retry_reconstruction(product_id_or_job_id)` method on `ReconstructionQueueManager` to guarantee fresh job creation with a new UUID and fresh inference execution.

3. **`backend/app.py`**:
   - Removed lines 547-558 in `enqueue_reconstruction` that short-circuited to completed results. All async requests now strictly return `202 Queued`.
   - Added `@app.route("/api/reconstruct/retry/<product_or_job_id>", methods=["POST"])` and `@app.route("/api/v1/reconstruct/retry/<product_or_job_id>", methods=["POST"])` delegating to `reconstruct_queue_manager.retry_reconstruction`.
   - Added `@app.route("/models/<path:filename>")` alias alongside `/cache/models/<path:filename>`, serving directly from `MODELS_OUTPUT_DIR`.
   - Increased synchronous mode polling timeout from 75s to 180s to prevent premature timeout during cold neural model initialization.

4. **`frontend/src/components/stages/ImageApprovalStage.jsx`**:
   - Cleaned obsolete comment from `cached model stats` to `downstream model stats`.

5. **`tests/test_reconstruction_and_reference_selection.py`**:
   - Updated tests 1, 2, 3, and 4: replaced assertions expecting `cache_hit: False` with `assertNotIn("cache_hit", data)` and assertions checking `assertIn("call_count", data)`, `assertIn("request_token", data)`, and strictly incremented call counts across repeated requests.

6. **`tests/test_reconstruction_cache_removal.py`** *(NEW dedicated verification suite)*:
   - Created comprehensive verification suite covering all 6 mandatory test requirements.

---

## 4. Exact Behavioral Changes

| Scenario | Previous Behavior | New Behavior |
|----------|-------------------|--------------|
| **Reconstruct Image A, then Image A again** | Could potentially reuse previous GLB or return same result | Executes fresh neural inference twice. Generates 2 distinct GLB files with distinct UUID tokens; call count increments from `N` to `N+1`. |
| **Reconstruct Product X, then Product X again** | Job lookup could short-circuit if existing job was completed | Old job is superseded; a fresh `rec-job-<uuid>` is enqueued; fresh neural inference executes; supersedes old GLB. |
| **Reconstruct Image A, then Image B sequentially** | Concurrency serialized | Concurrency remains serialized (1 GPU slot at a time), but Request B executes fresh inference and generates a distinct model. |
| **Retry completed/failed reconstruction** | No dedicated retry API | Dedicated POST `/api/v1/reconstruct/retry/<id>` enqueues fresh job with new UUID and executes fresh inference. |
| **Response Payload** | Contained `"cache_hit": False` | Contains zero cache fields; contains `"call_count"`, `"request_token"`, and fresh timestamps. |
| **Model Serving** | Served from static cache path | Served as ephemeral output from `MODELS_OUTPUT_DIR`. |
| **GPU Model Residency** | Resident in GPU memory | Resident in GPU memory (RTX 4060 Laptop GPU) for inference efficiency, but NEVER bypasses neural execution. |

---

## 5. Backend Verification

- **Code Inspection:** Verified that `ReconstructionService.generate_3d_asset`, `Pixal3DEngine.reconstruct_from_image`, and `ReconstructionQueueManager._process_queue_item` contain zero cache lookup branches, zero hash-to-model maps, zero dictionary caches, and zero short-circuit logic.
- **Queue Semantics:** Verified that `ReconstructionQueueManager` serializes jobs (maximum concurrency = 1 GPU active task) and always submits each job to `_executor.submit(self._process_queue_item, job)`.
- **API Surface:** Verified `/api/v1/reconstruct/queue` always issues `202 Accepted` with a new unique `rec-job-<hex>` ID.

---

## 6. Frontend Verification

An automated AST and text audit across all JSX components in `frontend/src/` verified zero user-facing cache UI or state:
- Scanned for: `reconstruction cache`, `cache hit`, `cache miss`, `cached model`, `model reused from cache`, `cache age`, `cached result`.
- **Violations Found:** 0.
- All stages (`Generate3DStage.jsx`, `Approval3DStage.jsx`, `ImageApprovalStage.jsx`, `ReferenceSheetStage.jsx`) render authentic real-time progress, mesh statistics, watertight status, and 3D preview without any cache indicators.

---

## 7. Tests Executed + Results

All test suites executed against the live Python 3.13 virtual environment with GPU acceleration (`NVIDIA GeForce RTX 4060 Laptop GPU`):

| Test Suite | Scope | Ran | Passed | Failed | Status |
|------------|-------|-----|--------|--------|--------|
| `tests/test_reconstruction_cache_removal.py` | Mandatory cache removal tests 1–6 | 6 | 6 | 0 | **100% PASS** |
| `tests/test_reconstruction_and_reference_selection.py` | Full Pixal3D, reference routing & fresh inference | 6 | 6 | 0 | **100% PASS** |
| `tests/test_identifier_policy.py` | Identifier policy & query generation | 10 | 10 | 0 | **100% PASS** |
| `backend/tests/test_scraper_harvesting.py` | Scraper harvesting & pipeline | 6 | 6 | 0 | **100% PASS** |
| `backend/tests/test_research_correctness.py` | Research pipeline ranking & DINO | 8 | 8 | 0 | **100% PASS** |
| `backend/tests/test_lifecycle_and_queue.py` | Job lifecycle, cancel, canonical status | 14 | 14 | 0 | **100% PASS** |
| `backend/tests/test_end_to_end_baseline.py` | End-to-end pipeline & static model serving | 4 | 4 | 0 | **100% PASS** |
| **TOTAL** | | **54** | **54** | **0** | **100% PASS** |

### Detailed Results of `tests/test_reconstruction_cache_removal.py`:
- `test_01_same_image_reconstructed_twice`: PASSED (Executed independent inferences: calls 1 -> 2; files distinct, tokens distinct).
- `test_02_same_product_reconstructed_twice`: PASSED (Second request generated fresh GLB: `PROD-REUSE-CHECK_pixal3d_94cf8309_...glb` vs `PROD-REUSE-CHECK_pixal3d_2bd68b6f_...glb`).
- `test_03_different_images_reconstructed_sequentially`: PASSED (Sequential images generated distinct models: `PROD-SEQ-A_...glb` vs `PROD-SEQ-B_...glb`).
- `test_04_retry_reconstruction`: PASSED (Retry enqueued fresh job `rec-job-c0130e9f` -> `rec-job-275f30f6`, fresh inference call #8).
- `test_05_no_cache_lookup_in_execution_path`: PASSED (Zero forbidden cache lookup phrases in execution path).
- `test_06_frontend_contains_no_cache_ui`: PASSED (Zero forbidden cache UI strings across frontend JSX).

---

## 8. Real Runtime Verification Evidence

A live runtime verification was conducted directly against the running Flask daemon at `http://127.0.0.1:5000` via `runtime_verify_fresh_inference.py`.

### Test Execution:
Two consecutive reconstruction requests with an **identical reference image** (Base64 JPEG) and identical metadata were submitted to the live server.

### Observable Evidence Captured:

```json
{
  "verification": "SUCCESS",
  "request_1": {
    "job_id": "rec-job-29d9705a",
    "model_filename": "PROD-LIVE-VERIFY-01_pixal3d_a966b123_1791897317511.glb",
    "request_token": "a966b123",
    "call_count": 1,
    "generation_time_sec": 2.715,
    "mesh_stats": {
      "euler_characteristic": 12,
      "face_count": 234876,
      "vertex_count": 117450,
      "watertight": true
    },
    "cache_hit_present": false
  },
  "request_2": {
    "job_id": "rec-job-d38de50e",
    "model_filename": "PROD-LIVE-VERIFY-01_pixal3d_f87c2ef2_1791897321817.glb",
    "request_token": "f87c2ef2",
    "call_count": 2,
    "generation_time_sec": 2.586,
    "mesh_stats": {
      "euler_characteristic": 12,
      "face_count": 234876,
      "vertex_count": 117450,
      "watertight": true
    },
    "cache_hit_present": false
  }
}
```

### Key Telemetry Proof:
1. **Distinct Job IDs:** `rec-job-29d9705a` vs `rec-job-d38de50e`
2. **Distinct Output Artifacts:** `..._a966b123_1791897317511.glb` vs `..._f87c2ef2_1791897321817.glb`
3. **Distinct Request Tokens:** `a966b123` vs `f87c2ef2`
4. **Strictly Incremented Call Count:** `1` -> `2`
5. **Real Neural Inference Execution:** Both requests took ~2.6–2.7s on RTX 4060 GPU and extracted 117,450 vertices / 234,876 triangles.
6. **Zero Cache Flags:** `"cache_hit"` is completely absent from all response dictionaries.

---

## 9. Confirmation That Research / Download Caching Remains Intact

- Verified that `backend/cache/candidates/` and `backend/cache/jobs/` remain fully functional and were not deleted or modified.
- Verified that `backend/tests/test_end_to_end_baseline.py` successfully completed live research scraping:
  - Harvested 54 URLs -> 50 unique candidates.
  - Downloaded 31 images to RAM.
  - Evaluated with DINOv2 and curated 5 top reference images.
  - Completed research job `res-job-d09147fc` and persisted results to `backend/cache/jobs/research_res-job-d09147fc.json`.
- Research candidate image serving route `@app.route("/cache/candidates/<path:filename>")` remains intact and fully functional.

---

## 10. Confirmation That No Silent Reconstruction-Result Reuse Remains

1. **No Image Hash Lookup:** `compute_image_md5()` is retained purely as a diagnostic fingerprint log and is never used to query or load an existing model.
2. **No Product ID Lookup:** Submitting the same product ID enqueues a new job with a new UUID and processes fresh inference.
3. **No Short-Circuit:** The `if job.status == COMPLETED` bypass in `enqueue_reconstruction` was removed.
4. **Temporary File Management:** Superseded `.glb` files for the same product ID are pruned (`_cleanup_superseded_models`), preventing accumulation and guaranteeing stale models cannot be served.

---

## 11. Remaining Concerns / Blockers

- **None.** All 12 success conditions are met.
- The pipeline is fully prepared for the upcoming 3D-generation engine migration task without any interference from reconstruction caching.

---
*(End of Temporary Audit Deliverable)*
