# TEMP YATZAR PIXAL3D ENGINE AND STANDALONE BASELINE AUDIT

**Date:** 2026-10-13  
**Auditor / Engineer:** Antigravity (Grav)  
**Status:** IN PROGRESS (Phases 1-3 Complete, Ladder Execution Active)  
**Target:** Prove current Yatzar reconstruction engine identity + Execute maximum-quality official TencentARC Pixal3D baseline comparison on ViewSonic LS800HD reference image.

---

## 1. Executive Summary & Engine Identity Proof (Phase 1)

### Conclusive Finding:
**The engine currently executed by Yatzar is 100% Stability AI TripoSR (`stabilityai/TripoSR`). It is NOT TencentARC Pixal3D, despite being wrapped in a class named `Pixal3DEngine` and labeled "Pixal3D (TencentARC)" in the frontend UI and server logs.**

### Source Code & Runtime Trace:
1. **Frontend Trigger:**
   - File: `frontend/src/components/stages/Generate3DStage.jsx`
   - User clicks "Generate 3D Model".
   - Calls `handleGenerate()` -> `reconstructModel()` in `frontend/src/context/ProductContext.jsx`.
   - Sends HTTP POST payload `{"engine": "Pixal3D"}` to `/api/reconstruct/queue`.
2. **Backend API Route:**
   - File: `backend/routes/reconstruct_routes.py` lines 86-98:
     ```python
     @reconstruct_bp.route('/queue', methods=['POST'])
     def queue_reconstruction():
         ...
         job_id = job_manager.submit_job(sku, candidate_id, engine, ...)
     ```
3. **Queue / Job Manager:**
   - File: `backend/services/job_manager.py` lines 122-127:
     ```python
     worker_thread = threading.Thread(
         target=self._run_job,
         args=(job_id, sku, candidate_id, engine, manual_reference_path, product_data)
     )
     ```
   - In `_run_job` (lines 142-146):
     ```python
     reconstruction_service = get_reconstruction_service()
     result = reconstruction_service.reconstruct(...)
     ```
4. **Reconstruction Service:**
   - File: `backend/services/reconstruction_service.py` lines 108-118:
     ```python
     engine_type = engine_type or self.engine_type
     if engine_type == 'Pixal3D':
         from models.pixal3d_engine import Pixal3DEngine
         engine = Pixal3DEngine()
     ```
5. **Model Initialization & Actual Imported Package / Weights:**
   - File: `backend/models/pixal3d_engine.py` lines 27-31:
     ```python
     from tsr.system import TSR
     ...
     class Pixal3DEngine:
         def __init__(self, device: str = "cuda:0", ...):
             ...
             self.model = TSR.from_pretrained(
                 "stabilityai/TripoSR",
                 config_name="config.yaml",
                 weight_name="model.ckpt"
             )
     ```
   - Lines 188-193:
     ```python
     with torch.no_grad():
         scene_codes = self.model(image, device=self.device)
     meshes = self.model.extract_mesh(scene_codes, True, resolution=256)
     ```
6. **Verdict:**
   - **Import:** `from tsr.system import TSR` (TripoSR repository)
   - **HuggingFace Checkpoint:** `stabilityai/TripoSR`
   - **Weights File:** `model.ckpt`
   - **Inference Call:** `self.model(image)`
   - **Mesh Extraction:** `self.model.extract_mesh(..., resolution=256)` (Marching Cubes on Triplane)
   - **Conclusion:** Yatzar's entire 3D generation history to date has been produced by TripoSR at 256³ voxel grid resolution. Zero TencentARC Pixal3D code has ever executed in production Yatzar.

---

## 2. Official TencentARC Pixal3D Repository & Commit (Phase 2)

- **Official Repository URL:** `https://github.com/TencentARC/Pixal3D`
- **Target Branch:** `master` (TRELLIS.2 backbone, proj-conditioning mode)
- **Checked-Out Directory:** `e:\SANJAY\YatzarCreations\Yatzar-Manage-AI\standalone_pixal3d`
- **Git Commit Hash:** `f7cf38429b0bd264f1995f0f8743a88b1c728b94`
- **Commit Details:** `feat: support multi-view image input (Tue Sep 1 12:47:37 2026 +0800)`
- **Clean Checkout Verification:** Verified clean clone directly from TencentARC/Pixal3D.

---

## 3. Environment & Official Stack Verification (Phase 3)

### Hardware Specs:
- **Operating System:** Windows 11 Home (x64)
- **CPU:** Intel Core i7-13620H (16 threads)
- **System RAM:** 16.0 GB (15.7 GB usable)
- **GPU:** NVIDIA GeForce RTX 4060 Laptop GPU (Device 0)
- **GPU Dedicated VRAM:** 8188 MB (8.0 GB GDDR6)
- **CUDA Capability:** sm_89 (Ada Lovelace)

### Software & Dependency Stack:
- **Python Version:** 3.13.0 (`backend\venv`)
- **PyTorch:** `2.10.0+cu126` (Official PyTorch CUDA 12.6 Windows build)
- **Torchvision:** `0.25.0+cu126`
- **CUDA Runtime:** 12.6
- **Attention Backend:** `ATTN_BACKEND=sdpa` (PyTorch native scaled dot-product attention; fallback for Windows where triton-based flash_attn is omitted)

### Verified Official Specialized C++ / CUDA Extensions:
- **`o-voxel` (0.0.1):** `import o_voxel` -> `o_voxel._C` compiled against PyTorch 2.10 ABI verified.
- **`cumesh` (0.0.1):** `import cumesh` verified.
- **`flex-gemm` (1.0.0):** `import flex_gemm` verified; sparse convolution backend active.
- **`natten` (0.21.6):** `import natten` verified; neighborhood attention operators active.
- **`nvdiffrast` (0.4.0):** `import nvdiffrast` verified.
- **`moge` (3.0.0):** `import moge` (Microsoft MoGe v2) verified for camera estimation.
- **`utils3d` (0.0.2):** `import utils3d` verified.
- **`pixal3d.pipelines`:** `from pixal3d.pipelines import Pixal3DImageTo3DPipeline` verified.

---

## 4. Model & Checkpoint Identifiers

- **Backbone Model Repo:** `TencentARC/Pixal3D` (Hugging Face)
- **Sparse Structure Flow Model:** `sparse_structure_flow_model`
- **Sparse Structure Decoder:** `sparse_structure_decoder`
- **Shape SLat Flow Model 512:** `shape_slat_flow_model_512`
- **Shape SLat Flow Model 1024:** `shape_slat_flow_model_1024`
- **Shape SLat Decoder:** `shape_slat_decoder`
- **Texture SLat Flow Model 512:** `tex_slat_flow_model_512`
- **Texture SLat Flow Model 1024:** `tex_slat_flow_model_1024`
- **Texture SLat Decoder:** `tex_slat_decoder`
- **Conditioning Backbone:** `camenduru/dinov3-vitl16-pretrain-lvd1689m`
- **Camera Estimation Model:** `Ruicheng/moge-2-vitl`
- **Background Removal:** `briaai/RMBG-1.4` / RemBG

---

## 5. Quality Configuration Ladder (Phases 4–6)

| Ladder Stage | Configuration | Target Resolution | Offloading Strategy | Status | Peak VRAM / RAM | Notes / Errors |
|---|---|---|---|---|---|---|
| **Config A** | Official Pixal3D Standard | 1536 cascade | None (All models on GPU simultaneously) | PENDING | TBD | Testing standard full GPU load |
| **Config B** | Staged CPU/RAM Offload | 1536 cascade | Explicit CPU memory offload per pipeline stage | PENDING | TBD | Staging between SS, Shape, Tex |
| **Config C** | Official low_vram Mode | 1536 cascade | Pixal3D official `low_vram=True` with forced `--resolution 1536` | PENDING | TBD | Preserving maximum 1536 resolution |
| **Config D** | Fallback Low-VRAM | 1024 cascade | Pixal3D official `low_vram=True`, resolution 1024 | PENDING | TBD | Only if 1536 fails after all offloads |

---

## 6. Input Reference Image & Baseline Artifacts (Phases 4 & 8)

- **Reference Product:** ViewSonic LS800HD High Brightness Installation Laser Projector
- **Yatzar Approved Reference Image:** `backend/cache/candidates/verified_4d28321d64f4.jpg`
  - Dimensions: 800 x 533 RGB
  - Subject: Clean front perspective view of ViewSonic LS800HD with lens, exhaust vents, and top ViewSonic logo.
- **Current Yatzar Baseline GLBs (TripoSR):**
  - `backend/cache/models/VS-LS800HD_pixal3d_1791890700133.glb` (Size: 4.86 MB)
  - `backend/cache/models/VS-LS800HD_pixal3d_1791890711686.glb` (Size: 4.86 MB)

---

## 7. Comparative Analysis & Root-Cause Investigation (Phases 9 & 10)
*(To be populated following output capture)*

---

## 8. Definition of Done Evidence Log
*(To be populated as each criterion is completed)*
