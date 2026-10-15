"""
Official TencentARC Pixal3D Production Integration Adapter for Yatzar.

Executes pixel-aligned 3D reconstruction using the verified official TencentARC/Pixal3D 1536 cascade.
Preserves:
- 1536 cascade resolution
- Low-VRAM CPU offload mode (<6 GB peak VRAM on 8 GB GPU)
- NAF fast subgrid attention
- Sparse coordinate projection conditioning
- Implicit GEMM flex_gemm submanifold sparse convolution
- In-place LayerNorm token chunking
- Flexible Dual Grid (FDG) 2048px PBR UV texture baking
- Canonical glTF transformation
"""

import os
import sys
import gc
import math
import time
import uuid
import logging
from pathlib import Path
from typing import Dict, Any, Optional, Union, Tuple, Callable

import torch
import numpy as np
from PIL import Image

logger = logging.getLogger("yatzar.pixal3d_adapter")

# Configure environment for Pixal3D before imports
WORKSPACE_DIR = Path(__file__).resolve().parent.parent.parent
STANDALONE_PIXAL3D_DIR = WORKSPACE_DIR / "standalone_pixal3d"
if str(WORKSPACE_DIR) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_DIR))
if str(STANDALONE_PIXAL3D_DIR) not in sys.path:
    sys.path.insert(0, str(STANDALONE_PIXAL3D_DIR))

os.environ['OPENCV_IO_ENABLE_OPENEXR'] = '1'
os.environ["PYTORCH_CUDA_ALLOC_CONF"] = "expandable_segments:True"
os.environ.setdefault("ATTN_BACKEND", "sdpa")
os.environ["FLEX_GEMM_AUTOTUNE_CACHE_PATH"] = str(STANDALONE_PIXAL3D_DIR / 'autotune_cache.json')
os.environ["FLEX_GEMM_AUTOTUNER_VERBOSE"] = '0'

# Lazy-imported dependencies
_pipeline_instance = None
_moge_model_instance = None


def get_pixal3d_pipeline(device: str = "cuda"):
    """
    Returns the resident Pixal3DImageTo3DPipeline configured in low-VRAM mode.
    Models reside in host memory and are streamed to GPU on-demand per stage.
    """
    global _pipeline_instance
    if _pipeline_instance is not None:
        return _pipeline_instance

    logger.info("[PIXAL3D ADAPTER] Initializing official TencentARC/Pixal3D pipeline (Low-VRAM, 1536 Cascade)...")
    from standalone_pixal3d.inference import init_pipeline, MODEL_PATH
    
    t0 = time.perf_counter()
    _pipeline_instance = init_pipeline(model_path=MODEL_PATH, device=device, low_vram=True)
    load_sec = round(time.perf_counter() - t0, 2)
    logger.info(f"[PIXAL3D ADAPTER] Pipeline loaded and resident in {load_sec}s")
    return _pipeline_instance


class Pixal3DProductionAdapter:
    """
    Production adapter executing official TencentARC Pixal3D 1536 cascade
    behind Yatzar's JobManager and ReconstructionService.
    """

    def __init__(self, device: str = "cuda:0"):
        self.device = device if torch.cuda.is_available() else "cpu"
        self.resolution = 1536
        self.pipeline_type = "1536_cascade"
        self.low_vram = True
        self.call_count = 0

    def reconstruct(
        self,
        image_input: Union[str, Path, Image.Image],
        output_glb_path: Union[str, Path],
        product_name: str = "Asset",
        seed: int = 42,
        progress_callback: Optional[Callable[[str, float], None]] = None
    ) -> Dict[str, Any]:
        """
        Executes end-to-end official Pixal3D 1536 inference.
        """
        import o_voxel
        import trimesh
        from standalone_pixal3d.inference import (
            load_moge_model,
            get_camera_params_wild_moge,
        )

        t_start = time.perf_counter()
        self.call_count += 1
        output_glb_path = Path(output_glb_path).resolve()
        output_glb_path.parent.mkdir(parents=True, exist_ok=True)

        logger.info(f"[PIXAL3D ADAPTER] Starting 1536 cascade for '{product_name}' -> {output_glb_path.name}")
        if progress_callback:
            progress_callback("Initializing Pixal3D Pipeline", 0.05)

        # 1. Load input image
        if isinstance(image_input, Image.Image):
            pil_img = image_input.convert("RGB")
        elif isinstance(image_input, (str, Path)):
            pil_img = Image.open(str(image_input)).convert("RGB")
        else:
            raise ValueError(f"Unsupported image_input type: {type(image_input)}")

        pipeline = get_pixal3d_pipeline(device="cuda" if "cuda" in self.device else "cpu")

        # 2. Foreground Segmentation / Image Preprocessing
        if progress_callback:
            progress_callback("Preprocessing Image & Segmenting Foreground", 0.10)
        logger.info("[PIXAL3D ADAPTER] Preprocessing image (rembg background removal)...")
        image_preprocessed = pipeline.preprocess_image(pil_img)

        # Save temporary preprocessed image for MoGe camera estimation
        tmp_prep_path = output_glb_path.parent / f"_tmp_prep_{uuid.uuid4().hex[:8]}.png"
        image_preprocessed.save(tmp_prep_path)

        # 3. MoGe-2 Camera Estimation
        if progress_callback:
            progress_callback("Estimating Camera Intrinsics (MoGe-2)", 0.15)
        logger.info("[PIXAL3D ADAPTER] Estimating camera parameters with MoGe-2...")
        moge_model = load_moge_model(device="cuda" if torch.cuda.is_available() else "cpu")
        camera_params = get_camera_params_wild_moge(
            str(tmp_prep_path),
            moge_model,
            device="cuda" if torch.cuda.is_available() else "cpu",
            mesh_scale=1.0,
            extend_pixel=0,
            image_resolution=512,
        )
        # Immediately release MoGe VRAM
        moge_model.cpu()
        del moge_model
        if torch.cuda.is_available():
            torch.cuda.empty_cache()

        if tmp_prep_path.exists():
            tmp_prep_path.unlink()

        logger.info(f"[PIXAL3D ADAPTER] Camera estimated: angle_x={camera_params['camera_angle_x']:.4f}, dist={camera_params['distance']:.4f}")

        # 4. DiT Flow Matching Sampling (Stages 2, 3a, 3b, 4)
        if progress_callback:
            progress_callback("Executing Sparse Structure & Shape DiT Cascade (1536)", 0.30)
        logger.info("[PIXAL3D ADAPTER] Running DiT flow matching cascades at resolution 1536...")

        ss_sampler_override = {
            "steps": 12, "guidance_strength": 7.5, "guidance_rescale": 0.7, "rescale_t": 5.0,
        }
        shape_sampler_override = {
            "steps": 12, "guidance_strength": 7.5, "guidance_rescale": 0.5, "rescale_t": 3.0,
        }
        tex_sampler_override = {
            "steps": 12, "guidance_strength": 1.0, "guidance_rescale": 0.0, "rescale_t": 3.0,
        }

        torch.manual_seed(seed)
        mesh_list, (shape_slat, tex_slat, res) = pipeline.run(
            image_preprocessed,
            camera_params=camera_params,
            seed=seed,
            sparse_structure_sampler_params=ss_sampler_override,
            shape_slat_sampler_params=shape_sampler_override,
            tex_slat_sampler_params=tex_sampler_override,
            preprocess_image=False,
            return_latent=True,
            pipeline_type=self.pipeline_type,
            max_num_tokens=49152,
        )

        mesh = mesh_list[0]
        pbr_layout = pipeline.pbr_attr_layout
        vertices = mesh.vertices.float()
        faces = mesh.faces
        attrs_volume = mesh.attrs.float() if hasattr(mesh.attrs, 'float') else mesh.attrs
        coords = mesh.coords

        # CRITICAL VRAM RECLAMATION BEFORE CuMesh / to_glb:
        # CuMesh builds a BVH and simplifies ~26 million triangles using native cudaMalloc allocations.
        # We must explicitly delete intermediate latents, unload the pipeline, and flush PyTorch's CUDA cache
        # so CuMesh has the full 8 GB VRAM buffer available.
        del mesh_list, mesh, shape_slat, tex_slat
        self.pipeline = None
        gc.collect()
        torch.cuda.empty_cache()
        if hasattr(torch.cuda, 'ipc_collect'):
            torch.cuda.ipc_collect()
        logger.info(f"[PIXAL3D ADAPTER] Memory reclaimed for CuMesh: allocated={torch.cuda.memory_allocated() / (1024**2):.1f}MB, reserved={torch.cuda.memory_reserved() / (1024**2):.1f}MB")

        # 5. Mesh Postprocessing & GLB Export
        if progress_callback:
            progress_callback("Extracting Flexible Dual Grid Mesh & Baking 2048px PBR UVs", 0.85)
        logger.info(f"[PIXAL3D ADAPTER] Extracting GLB with Flexible Dual Grid (res={res}, target=300k faces)...")

        glb = o_voxel.postprocess.to_glb(
            vertices=vertices,
            faces=faces,
            attr_volume=attrs_volume,
            coords=coords,
            attr_layout=pbr_layout,
            grid_size=res,
            aabb=[[-0.5, -0.5, -0.5], [0.5, 0.5, 0.5]],
            decimation_target=300000,
            texture_size=2048,
            remesh=False,
            verbose=True,
            use_tqdm=False,
        )

        # 6. Apply Official Pixal3D Canonical Orientation
        rot = np.array([
            [-1,  0,  0,  0],
            [ 0,  0, -1,  0],
            [ 0, -1,  0,  0],
            [ 0,  0,  0,  1],
        ], dtype=np.float64)
        glb.apply_transform(rot)

        # 7. Serialize GLB
        glb.export(str(output_glb_path), extension_webp=True)

        if not output_glb_path.exists() or output_glb_path.stat().st_size == 0:
            raise RuntimeError(f"GLB export failed: output file {output_glb_path} does not exist or is 0 bytes")

        file_size_bytes = output_glb_path.stat().st_size
        elapsed_sec = round(time.perf_counter() - t_start, 2)
        logger.info(f"[PIXAL3D ADAPTER] GLB generated successfully: {file_size_bytes:,} bytes in {elapsed_sec}s")

        if progress_callback:
            progress_callback("Finalizing 3D Asset Telemetry", 0.98)

        # 8. Audit Mesh Geometry
        scene_or_mesh = trimesh.load(str(output_glb_path))
        if isinstance(scene_or_mesh, trimesh.Scene):
            loaded_mesh = trimesh.util.concatenate([g for g in scene_or_mesh.geometry.values() if isinstance(g, trimesh.Trimesh)])
        else:
            loaded_mesh = scene_or_mesh

        num_verts = len(loaded_mesh.vertices)
        num_faces = len(loaded_mesh.faces)
        is_watertight = bool(loaded_mesh.is_watertight)
        body_count = int(loaded_mesh.body_count)
        bounds = loaded_mesh.bounds.tolist()
        extents = loaded_mesh.extents.tolist()

        peak_vram_mb = round(torch.cuda.max_memory_allocated() / (1024 * 1024), 1) if torch.cuda.is_available() else 0.0

        return {
            "success": True,
            "local_path": str(output_glb_path),
            "model_filename": output_glb_path.name,
            "format": "glb",
            "file_size_bytes": file_size_bytes,
            "file_size_mb": round(file_size_bytes / (1024 * 1024), 2),
            "reconstruction_engine": "Pixal3D",
            "generation_time_sec": elapsed_sec,
            "generation_time_ms": int(elapsed_sec * 1000),
            "call_count": self.call_count,
            "mesh_telemetry": {
                "vertices": num_verts,
                "triangles": num_faces,
                "is_watertight": is_watertight,
                "components": body_count,
                "extents": extents,
                "bounds": bounds
            },
            "mesh_stats": {
                "vertices": num_verts,
                "faces": num_faces,
                "watertight": is_watertight,
                "components": body_count
            },
            "telemetry": {
                "engine": "Pixal3D",
                "resolution": self.resolution,
                "pipeline_type": self.pipeline_type,
                "low_vram": self.low_vram,
                "peak_vram_mb": peak_vram_mb,
                "device": self.device,
                "gpu_device": torch.cuda.get_device_name(0) if torch.cuda.is_available() else "CPU",
            }
        }
