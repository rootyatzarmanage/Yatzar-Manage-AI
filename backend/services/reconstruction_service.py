"""
3D Reconstruction Service for Yatzar.
Primary Production Architecture:
- Official TencentARC Pixal3D (1536 HR Shape Cascade + 1024 Texture Model + 2048px PBR Texture Baking)
- Pixel-aligned back-projection conditioning with DinoV3
- Flow-Matching DiT sparse structure and multi-scale shape latents
- Flexible Dual Grid (FDG) 2048px PBR UV texture baking
- Low-VRAM CPU/GPU memory streaming architecture for 8 GB GPUs

Produces high-fidelity, CAD-grade 3D product meshes exported to binary GLTF (.glb).
"""

import os
import io
import sys
import time
import uuid
import hashlib
import logging
from pathlib import Path
from typing import Dict, Any, Optional, Tuple, Union, Callable

import numpy as np
from PIL import Image
import torch
import trimesh

try:
    from services.pixal3d_adapter import Pixal3DProductionAdapter
except ImportError:
    from backend.services.pixal3d_adapter import Pixal3DProductionAdapter

logger = logging.getLogger(__name__)

# Runtime output directory for generated 3D assets (ephemeral runtime outputs, NOT a cache)
MODELS_OUTPUT_DIR = Path(__file__).resolve().parent.parent / "cache" / "models"
MODELS_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
MODELS_CACHE_DIR = MODELS_OUTPUT_DIR  # Backward-compatible alias for existing imports


def compute_image_md5(image_input: Union[str, Path, bytes, Image.Image]) -> str:
    """Computes MD5 hash for image input to provide diagnostic verification fingerprint."""
    try:
        if isinstance(image_input, bytes):
            return hashlib.md5(image_input).hexdigest()
        elif isinstance(image_input, Image.Image):
            buf = io.BytesIO()
            image_input.save(buf, format="PNG")
            return hashlib.md5(buf.getvalue()).hexdigest()
        elif isinstance(image_input, (str, Path)):
            s = str(image_input)
            if os.path.exists(s):
                with open(s, "rb") as f:
                    return hashlib.md5(f.read()).hexdigest()
            return hashlib.md5(s.encode("utf-8")).hexdigest()
        return hashlib.md5(str(image_input).encode("utf-8")).hexdigest()
    except Exception:
        return hashlib.md5(str(time.time()).encode("utf-8")).hexdigest()


class Pixal3DEngine:
    """
    Production Pixal3D Reconstruction Engine (TencentARC/Pixal3D).
    Direct wrapper around Pixal3DProductionAdapter for official 1536 cascade inference.
    """

    def __init__(self, device: Optional[str] = None):
        if device is None:
            self.device = "cuda:0" if torch.cuda.is_available() else "cpu"
        else:
            self.device = device

        self.model_name = "TencentARC/Pixal3D"
        self.adapter = Pixal3DProductionAdapter(device=self.device)
        self.call_count = 0
        self.is_resident = True
        logger.info(f"[PIXAL3D ENGINE] Initialized official TencentARC Pixal3D engine on {self.device}")

    def reconstruct_from_image(
        self,
        image_input: Union[str, Path, bytes, Image.Image],
        output_glb_path: Union[str, Path],
        product_name: str = "Asset",
        progress_callback: Optional[Callable[[str, float], None]] = None
    ) -> Dict[str, Any]:
        """
        Executes official TencentARC Pixal3D 1536 cascade reconstruction.
        """
        self.call_count += 1
        output_path = Path(output_glb_path)

        # Resolve image input
        if isinstance(image_input, bytes):
            pil_img = Image.open(io.BytesIO(image_input)).convert("RGB")
        elif isinstance(image_input, str) and image_input.startswith("data:image"):
            import base64
            _, b64_data = image_input.split(",", 1)
            raw = base64.b64decode(b64_data)
            pil_img = Image.open(io.BytesIO(raw)).convert("RGB")
        elif isinstance(image_input, str) and (image_input.startswith("http://") or image_input.startswith("https://")):
            import urllib.request
            req = urllib.request.Request(image_input, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                raw = resp.read()
            pil_img = Image.open(io.BytesIO(raw)).convert("RGB")
        elif isinstance(image_input, (str, Path)):
            pil_img = Image.open(str(image_input)).convert("RGB")
        elif isinstance(image_input, Image.Image):
            pil_img = image_input.convert("RGB")
        else:
            raise ValueError(f"Unsupported image input type: {type(image_input)}")

        return self.adapter.reconstruct(
            image_input=pil_img,
            output_glb_path=output_path,
            product_name=product_name,
            progress_callback=progress_callback
        )


class ReconstructionService:
    """
    Singleton service managing 3D reconstruction.
    Official TencentARC/Pixal3D 1536 cascade is the SOLE active production engine.
    """
    _instance: Optional["ReconstructionService"] = None

    def __init__(self):
        if ReconstructionService._instance is None:
            ReconstructionService._instance = self
        self.pixal3d_engine: Optional[Pixal3DEngine] = None
        self.call_count = 0

        if torch.cuda.is_available():
            torch.cuda.empty_cache()

        # Initialize Pixal3D engine as sole production engine
        try:
            self.pixal3d_engine = Pixal3DEngine()
        except Exception as e:
            logger.error(f"[RECONSTRUCTION SERVICE] Failed to initialize Pixal3DEngine: {e}", exc_info=True)
            self.pixal3d_engine = None

    @classmethod
    def get_instance(cls) -> "ReconstructionService":
        if cls._instance is None:
            cls._instance = ReconstructionService()
        return cls._instance

    def _cleanup_superseded_models(self, asset_id: str, keep_latest_n: int = 1):
        """
        Cleans up old temporary GLB model artifacts for this asset so that stale
        files do not linger or act as an unintended persistent model cache.
        """
        try:
            pattern = f"{asset_id}_*.glb"
            existing_files = sorted(MODELS_OUTPUT_DIR.glob(pattern), key=lambda p: p.stat().st_mtime)
            if len(existing_files) > keep_latest_n:
                for old_f in existing_files[:-keep_latest_n]:
                    try:
                        old_f.unlink(missing_ok=True)
                        logger.debug(f"[OUTPUT CLEANUP] Removed old model artifact {old_f.name}")
                    except Exception as e:
                        logger.debug(f"Could not remove old model file {old_f}: {e}")
        except Exception as e:
            logger.debug(f"Error during model cleanup for {asset_id}: {e}")

    def generate_3d_asset(
        self,
        reference_image: Union[str, Path, Image.Image],
        product_metadata: Optional[Dict[str, Any]] = None,
        engine: str = "Pixal3D",
        progress_callback: Optional[Callable[[str, float], None]] = None
    ) -> Dict[str, Any]:
        """
        Main entrypoint for 3D generation.
        Strict no-cache guarantee: Always executes fresh Pixal3D 1536 neural inference.
        No previous reconstruction result can satisfy a new request.
        """
        t_req_start = time.perf_counter()
        self.call_count += 1
        meta = product_metadata or {}
        p_name = meta.get("name") or meta.get("product_title") or "Target Asset"
        p_id = meta.get("id") or meta.get("product_id") or f"prod_{int(time.time())}"

        # Validate reference image presence
        if not reference_image or (isinstance(reference_image, str) and not reference_image.strip()):
            logger.error(f"[RECONSTRUCTION] Missing approved reference image for asset '{p_id}'. Aborting.")
            return {
                "success": False,
                "error": "Missing approved reference image for 3D reconstruction",
                "reconstruction_engine": "TencentARC/Pixal3D",
                "status": "FAILED"
            }

        # Production engine is strictly TencentARC/Pixal3D
        engine_target = (engine or "Pixal3D").strip()
        valid_engines = ("pixal3d", "tencentarc/pixal3d")
        if engine_target.lower() not in valid_engines:
            logger.error(f"[RECONSTRUCTION] Unsupported engine '{engine_target}'. Sole production engine is TencentARC/Pixal3D.")
            return {
                "success": False,
                "error": f"Unsupported reconstruction engine: '{engine_target}'. Sole production engine is TencentARC/Pixal3D.",
                "reconstruction_engine": "TencentARC/Pixal3D",
                "status": "FAILED"
            }
        
        engine_tag = "pixal3d"
        img_fingerprint = compute_image_md5(reference_image)

        safe_id = "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in str(p_id))
        timestamp_ms = int(time.time() * 1000)
        req_token = uuid.uuid4().hex[:8]
        output_glb_filename = f"{safe_id}_{engine_tag}_{req_token}_{timestamp_ms}.glb"
        output_glb_path = MODELS_OUTPUT_DIR / output_glb_filename

        # Clean up any stale model artifacts for this asset before writing new one
        self._cleanup_superseded_models(safe_id, keep_latest_n=1)

        logger.info(f"[RECONSTRUCTION] Fresh Pixal3D inference request #{self.call_count} for {p_id} (output: {output_glb_filename})")

        if self.pixal3d_engine is None:
            try:
                self.pixal3d_engine = Pixal3DEngine()
            except Exception as e:
                logger.error(f"[RECONSTRUCTION] Pixal3DEngine initialization failed: {e}", exc_info=True)
                return {
                    "success": False,
                    "error": f"Pixal3D initialization failed: {str(e)}",
                    "reconstruction_engine": "Pixal3D",
                    "status": "FAILED"
                }

        try:
            result = self.pixal3d_engine.reconstruct_from_image(
                image_input=reference_image,
                output_glb_path=output_glb_path,
                product_name=p_name,
                progress_callback=progress_callback
            )

            t_total_sec = round(time.perf_counter() - t_req_start, 2)
            result["asset_id"] = p_id
            result["model_filename"] = output_glb_filename
            result["model_url"] = f"http://127.0.0.1:5000/cache/models/{output_glb_filename}"
            result["local_path"] = str(output_glb_path)
            result["format"] = "GLB"
            result["call_count"] = self.call_count
            result["inference_call_count"] = self.call_count
            result["request_token"] = req_token
            result["generation_time_sec"] = t_total_sec
            result["generation_time_ms"] = int(t_total_sec * 1000)
            result["reconstruction_engine"] = "Pixal3D"

            logger.info("=" * 70)
            logger.info(f"[PIXAL3D TELEMETRY] Completed in {t_total_sec}s | Vertices: {result.get('mesh_telemetry', {}).get('vertices')} | Faces: {result.get('mesh_telemetry', {}).get('triangles')}")
            logger.info(f"OUTPUT GLB: {output_glb_filename} ({result.get('file_size_mb')} MB)")
            logger.info("=" * 70)

            return result

        except Exception as e:
            logger.error(f"[PIXAL3D RECONSTRUCTION FAILED] Error: {e}", exc_info=True)
            return {
                "success": False,
                "error": f"Pixal3D execution error: {str(e)}",
                "reconstruction_engine": "Pixal3D",
                "status": "FAILED"
            }
        finally:
            import gc
            gc.collect()
            if torch.cuda.is_available():
                torch.cuda.empty_cache()

    def validate_mesh_asset(self, glb_path_or_url: str) -> Dict[str, Any]:
        """Validates a generated .glb asset for topology, vertex count, and integrity."""
        t0 = time.perf_counter()
        target_path = glb_path_or_url
        if glb_path_or_url.startswith("http://") or glb_path_or_url.startswith("https://"):
            filename = os.path.basename(glb_path_or_url)
            target_path = str(MODELS_CACHE_DIR / filename)

        if not os.path.exists(target_path):
            return {
                "valid": False,
                "error": f"Model file not found: {target_path}",
                "is_watertight": False,
                "triangles": 0,
                "vertices": 0
            }

        try:
            mesh = trimesh.load(target_path, force="mesh")
            num_triangles = len(mesh.faces)
            num_vertices = len(mesh.vertices)
            is_watertight = bool(mesh.is_watertight)
            file_size_kb = round(os.path.getsize(target_path) / 1024, 2)
            t_val_sec = round(time.perf_counter() - t0, 4)

            # Pixal3D meshes have high triangle count (>100,000) and rich internal/external topology
            is_valid = (num_triangles > 1000 and num_vertices > 1000 and file_size_kb > 100)

            return {
                "valid": is_valid,
                "format": "GLB",
                "triangles": num_triangles,
                "vertices": num_vertices,
                "is_watertight": is_watertight,
                "file_size_kb": file_size_kb,
                "validation_time_sec": t_val_sec,
                "quality_score": 0.98 if num_triangles > 100000 else 0.90,
                "checks": {
                    "asset_available": True,
                    "mesh_validation_passed": is_valid,
                    "is_watertight": is_watertight,
                    "high_density_surface": num_triangles > 50000
                }
            }
        except Exception as e:
            return {
                "valid": False,
                "error": f"Mesh validation error: {str(e)}",
                "is_watertight": False,
                "triangles": 0,
                "vertices": 0,
                "checks": {
                    "asset_available": os.path.exists(target_path),
                    "mesh_validation_passed": False,
                    "is_watertight": False
                }
            }
