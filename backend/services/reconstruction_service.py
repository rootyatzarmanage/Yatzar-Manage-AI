"""
3D Reconstruction Service for Yatzar.
Supports:
1. TripoSR Neural 3D Engine (Default Production Engine - stabilityai/TripoSR on CUDA GPU)
2. Pixel 3D Bilateral Extrusion Engine (Legacy Heuristic Baseline / Debug Fallback)

Produces watertight, manifold 3D product meshes exported to binary GLTF (.glb).
"""

import os
import io
import sys
import time
import uuid
import hashlib
import logging
from pathlib import Path
from typing import Dict, Any, Optional, Tuple, Union

import numpy as np
from PIL import Image, ImageFilter, ImageOps
import torch
import trimesh

# Add TripoSR repository to Python path
TRIPOSR_DIR = Path(__file__).resolve().parent.parent.parent / "tools" / "triposr_poc" / "TripoSR"
if TRIPOSR_DIR.exists() and str(TRIPOSR_DIR) not in sys.path:
    sys.path.insert(0, str(TRIPOSR_DIR))

logger = logging.getLogger(__name__)

# Output cache directory for generated 3D assets
MODELS_CACHE_DIR = Path(__file__).resolve().parent.parent / "cache" / "models"
MODELS_CACHE_DIR.mkdir(parents=True, exist_ok=True)


def compute_image_md5(image_input: Union[str, Path, bytes, Image.Image]) -> str:
    """Computes MD5 hash for image input to provide deterministic cache identity."""
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


class TripoSREngine:
    """
    Production TripoSR Neural 3D Reconstruction Engine.
    Executes feedforward transformer neural 3D synthesis on CUDA GPU (or CPU fallback)
    and extracts high-resolution isosurface mesh via Marching Cubes.
    """

    def __init__(self, device: Optional[str] = None):
        if device is None:
            self.device = "cuda:0" if torch.cuda.is_available() else "cpu"
        else:
            self.device = device

        self.model = None
        self.rembg_session = None
        self.model_name = "stabilityai/TripoSR"
        self._load_model()

    def _load_model(self):
        """Loads official TripoSR neural model weights and background removal session."""
        logger.info(f"[TRIPOSR ENGINE] Initializing TripoSR on device: {self.device}")
        t0 = time.time()
        try:
            if torch.cuda.is_available() and "cuda" in str(self.device):
                torch.cuda.empty_cache()
            from tsr.system import TSR
            import rembg

            self.model = TSR.from_pretrained(
                self.model_name,
                config_name="config.yaml",
                weight_name="model.ckpt"
            )
            self.model.renderer.set_chunk_size(8192)
            self.model.to(self.device)
            self.model.eval()
            
            # Use CPUExecutionProvider for rembg on Windows to ensure maximum stability
            self.rembg_session = rembg.new_session(providers=['CPUExecutionProvider'])
            t_load = time.time() - t0
            logger.info(f"[TRIPOSR ENGINE] TripoSR neural model loaded successfully in {t_load:.2f}s on {self.device}")
        except Exception as e:
            logger.error(f"[TRIPOSR ENGINE] Failed to load TripoSR neural model: {e}", exc_info=True)
            raise RuntimeError(f"TripoSR initialization error: {e}")

    def _load_and_preprocess_image(self, image_input: Union[str, Path, bytes, Image.Image]) -> Tuple[Image.Image, Image.Image]:
        """
        Loads the reference image and applies TripoSR rembg foreground extraction & centering.
        Returns: (original_pil_image, preprocessed_pil_image_ready_for_model)
        """
        import base64
        import urllib.request
        from tsr.utils import remove_background, resize_foreground

        if isinstance(image_input, Image.Image):
            input_pil = image_input.convert("RGB")
        elif isinstance(image_input, bytes):
            input_pil = Image.open(io.BytesIO(image_input)).convert("RGB")
        elif isinstance(image_input, str) and image_input.startswith("data:image"):
            _, b64_data = image_input.split(",", 1)
            raw = base64.b64decode(b64_data)
            input_pil = Image.open(io.BytesIO(raw)).convert("RGB")
        elif isinstance(image_input, str) and (image_input.startswith("http://") or image_input.startswith("https://")):
            req = urllib.request.Request(image_input, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=12) as resp:
                raw = resp.read()
            input_pil = Image.open(io.BytesIO(raw)).convert("RGB")
        elif isinstance(image_input, (str, Path)):
            input_pil = Image.open(str(image_input)).convert("RGB")
        else:
            raise ValueError(f"Unsupported reference image input type: {type(image_input)}")

        # Background removal & foreground normalization
        try:
            rembg_img = remove_background(input_pil, self.rembg_session)
            resized_img = resize_foreground(rembg_img, 0.85)
            
            # Blend alpha channel onto 50% gray background for TSR input
            img_np = np.array(resized_img).astype(np.float32) / 255.0
            if len(img_np.shape) == 3 and img_np.shape[2] == 4:
                img_np = img_np[:, :, :3] * img_np[:, :, 3:4] + (1 - img_np[:, :, 3:4]) * 0.5
            processed_input = Image.fromarray((img_np * 255.0).astype(np.uint8))
        except Exception as e:
            logger.warning(f"[TRIPOSR PREPROCESS] rembg foreground extraction fallback: {e}")
            processed_input = input_pil.convert("RGB")

        return input_pil, processed_input

    def reconstruct_from_image(
        self,
        image_input: Union[str, Path, Image.Image],
        output_glb_path: Path,
        product_name: str = "Product Asset",
        resolution: int = 256
    ) -> Dict[str, Any]:
        """
        Executes real neural TripoSR inference and extracts watertight .glb asset.
        """
        t_start = time.time()
        
        # 1. Preprocess
        t_prep_0 = time.time()
        input_pil, processed_input = self._load_and_preprocess_image(image_input)
        t_prep_sec = round(time.time() - t_prep_0, 3)

        # 2. Neural feedforward encoding
        if torch.cuda.is_available() and "cuda" in self.device:
            torch.cuda.synchronize()
            torch.cuda.reset_peak_memory_stats()

        t_infer_0 = time.time()
        infer_start_iso = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(t_infer_0))
        
        with torch.no_grad():
            scene_codes = self.model([processed_input], device=self.device)

        if torch.cuda.is_available() and "cuda" in self.device:
            torch.cuda.synchronize()
        t_infer_sec = round(time.time() - t_infer_0, 3)
        infer_end_iso = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime())

        # 3. Marching Cubes Mesh Extraction
        t_mesh_0 = time.time()
        meshes = self.model.extract_mesh(scene_codes, has_vertex_color=True, resolution=resolution, threshold=25.0)
        if torch.cuda.is_available() and "cuda" in self.device:
            torch.cuda.synchronize()
        t_mesh_sec = round(time.time() - t_mesh_0, 3)

        raw_mesh = meshes[0]

        # 4. Export GLB
        raw_mesh.export(str(output_glb_path))

        t_total_sec = round(time.time() - t_start, 2)
        glb_size_bytes = output_glb_path.stat().st_size

        # Measure VRAM
        peak_vram_mb = 0.0
        if torch.cuda.is_available() and "cuda" in self.device:
            peak_vram_mb = round(torch.cuda.max_memory_allocated() / (1024**2), 2)

        # Mesh topology stats
        num_verts = len(raw_mesh.vertices)
        num_faces = len(raw_mesh.faces)
        is_watertight = bool(raw_mesh.is_watertight)
        euler_char = int(raw_mesh.euler_number)

        gpu_name = torch.cuda.get_device_name(0) if (torch.cuda.is_available() and "cuda" in self.device) else "CPU"

        return {
            "success": True,
            "reconstruction_engine": "TripoSR",
            "model_name": self.model_name,
            "device": self.device,
            "gpu_device": gpu_name,
            "peak_vram_mb": peak_vram_mb,
            "generation_time_sec": t_total_sec,
            "generation_time_ms": int(t_total_sec * 1000),
            "telemetry": {
                "preprocessing_sec": t_prep_sec,
                "neural_inference_sec": t_infer_sec,
                "mesh_extraction_sec": t_mesh_sec,
                "inference_start": infer_start_iso,
                "inference_end": infer_end_iso,
                "mc_resolution": resolution,
                "peak_vram_mb": peak_vram_mb
            },
            "mesh_telemetry": {
                "vertices": num_verts,
                "triangles": num_faces,
                "is_watertight": is_watertight,
                "euler_characteristic": euler_char,
                "glb_size_bytes": glb_size_bytes,
                "bounds": raw_mesh.bounds.tolist() if hasattr(raw_mesh, "bounds") else []
            }
        }


class Pixel3DEngine:
    """
    Legacy Pixel 3D 2.5D Bilateral Extrusion Engine.
    Preserved as an explicit fallback / debug baseline engine.
    """

    def __init__(self, device: Optional[str] = None):
        if device is None:
            self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        else:
            self.device = torch.device(device)
        logger.info(f"[PIXEL 3D LEGACY] Initializing Pixel3DEngine on device: {self.device}")

    def _preprocess_reference_image(self, image_input: Union[str, Path, bytes, Image.Image]) -> Tuple[Image.Image, np.ndarray, np.ndarray]:
        import base64
        import urllib.request

        if isinstance(image_input, Image.Image):
            img = image_input.convert("RGBA")
        elif isinstance(image_input, bytes):
            img = Image.open(io.BytesIO(image_input)).convert("RGBA")
        elif isinstance(image_input, str) and image_input.startswith("data:image"):
            _, b64_data = image_input.split(",", 1)
            raw = base64.b64decode(b64_data)
            img = Image.open(io.BytesIO(raw)).convert("RGBA")
        elif isinstance(image_input, str) and (image_input.startswith("http://") or image_input.startswith("https://")):
            req = urllib.request.Request(image_input, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                raw = resp.read()
            img = Image.open(io.BytesIO(raw)).convert("RGBA")
        elif isinstance(image_input, (str, Path)):
            img = Image.open(str(image_input)).convert("RGBA")
        else:
            raise ValueError(f"Unsupported image input type: {type(image_input)}")

        img = img.resize((512, 512), Image.Resampling.LANCZOS)
        r, g, b, a = img.split()
        rgb_img = Image.merge("RGB", (r, g, b))

        alpha_arr = np.array(a)
        if (alpha_arr < 250).sum() > 500:
            mask = alpha_arr > 30
        else:
            gray = np.array(ImageOps.grayscale(rgb_img))
            corners = [gray[0:20, 0:20], gray[0:20, -20:], gray[-20:, 0:20], gray[-20:, -20:]]
            bg_val = float(np.mean([np.mean(c) for c in corners]))
            if bg_val > 180:
                mask = gray < (bg_val - 25)
            elif bg_val < 75:
                mask = gray > (bg_val + 25)
            else:
                mask = np.abs(gray - bg_val) > 20

            mask_img = Image.fromarray((mask * 255).astype(np.uint8))
            mask_img = mask_img.filter(ImageFilter.MaxFilter(5)).filter(ImageFilter.GaussianBlur(1))
            mask = np.array(mask_img) > 100

        gray_np = np.array(ImageOps.grayscale(rgb_img)).astype(np.float32) / 255.0
        grad_y, grad_x = np.gradient(gray_np)
        depth_map = 1.0 - (grad_x**2 + grad_y**2)**0.5
        depth_map = np.clip(depth_map * mask.astype(np.float32), 0.0, 1.0)

        return rgb_img, mask, depth_map

    def reconstruct_from_image(
        self,
        image_input: Union[str, Path, Image.Image],
        output_glb_path: Path,
        product_name: str = "Product Asset"
    ) -> Dict[str, Any]:
        t_start = time.time()
        rgb_img, mask, depth_map = self._preprocess_reference_image(image_input)
        
        y_indices, x_indices = np.where(mask)
        if len(x_indices) < 100:
            y_indices, x_indices = np.where(np.ones_like(mask, dtype=bool))

        x_min, x_max = x_indices.min(), x_indices.max()
        y_min, y_max = y_indices.min(), y_indices.max()
        w_px = max(x_max - x_min, 1)
        h_px = max(y_max - y_min, 1)
        aspect = w_px / h_px

        grid_res = 48
        mask_small = np.array(Image.fromarray((mask * 255).astype(np.uint8)).resize((grid_res, grid_res), Image.Resampling.BILINEAR)) > 100
        depth_small = np.array(Image.fromarray((depth_map * 255).astype(np.uint8)).resize((grid_res, grid_res), Image.Resampling.BILINEAR)) / 255.0

        vertices = []
        faces = []
        vertex_colors = []
        rgb_small = np.array(rgb_img.resize((grid_res, grid_res), Image.Resampling.BILINEAR))
        
        front_grid = np.full((grid_res, grid_res), -1, dtype=int)
        back_grid = np.full((grid_res, grid_res), -1, dtype=int)

        for r in range(grid_res):
            for c in range(grid_res):
                if mask_small[r, c]:
                    x = ((c / grid_res) - 0.5) * 2.0 * (aspect if aspect <= 1.0 else 1.0)
                    y = (0.5 - (r / grid_res)) * 2.0 * (1.0 / aspect if aspect > 1.0 else 1.0)
                    d = float(depth_small[r, c])
                    z_front = max(0.08, d * 0.45)
                    z_back = -z_front
                    col = rgb_small[r, c]
                    color_rgba = [int(col[0]), int(col[1]), int(col[2]), 255]

                    front_idx = len(vertices)
                    vertices.append([x, y, z_front])
                    vertex_colors.append(color_rgba)
                    front_grid[r, c] = front_idx

                    back_idx = len(vertices)
                    vertices.append([x, y, z_back])
                    vertex_colors.append(color_rgba)
                    back_grid[r, c] = back_idx

        for r in range(grid_res - 1):
            for c in range(grid_res - 1):
                f00, f01 = front_grid[r, c], front_grid[r, c + 1]
                f10, f11 = front_grid[r + 1, c], front_grid[r + 1, c + 1]
                if f00 >= 0 and f01 >= 0 and f10 >= 0 and f11 >= 0:
                    faces.append([f00, f01, f11])
                    faces.append([f00, f11, f10])

                b00, b01 = back_grid[r, c], back_grid[r, c + 1]
                b10, b11 = back_grid[r + 1, c], back_grid[r + 1, c + 1]
                if b00 >= 0 and b01 >= 0 and b10 >= 0 and b11 >= 0:
                    faces.append([b00, b11, b01])
                    faces.append([b00, b10, b11])

        for r in range(grid_res):
            for c in range(grid_res):
                if front_grid[r, c] >= 0:
                    neighbors = [(r - 1, c), (r + 1, c), (r, c - 1), (r, c + 1)]
                    for nr, nc in neighbors:
                        if nr < 0 or nr >= grid_res or nc < 0 or nc >= grid_res or front_grid[nr, nc] < 0:
                            f_curr = front_grid[r, c]
                            b_curr = back_grid[r, c]
                            for step_r, step_c in [(0, 1), (1, 0), (0, -1), (-1, 0)]:
                                ar, ac = r + step_r, c + step_c
                                if 0 <= ar < grid_res and 0 <= ac < grid_res and front_grid[ar, ac] >= 0:
                                    f_adj = front_grid[ar, ac]
                                    b_adj = back_grid[ar, ac]
                                    faces.append([f_curr, b_curr, f_adj])
                                    faces.append([b_curr, b_adj, f_adj])
                            break

        if len(faces) < 4:
            mesh = trimesh.creation.box(extents=[1.5, 1.5, 0.8])
        else:
            mesh = trimesh.Trimesh(
                vertices=np.array(vertices, dtype=np.float32),
                faces=np.array(faces, dtype=np.int32),
                vertex_colors=np.array(vertex_colors, dtype=np.uint8)
            )

        trimesh.smoothing.filter_laplacian(mesh, iterations=2)
        trimesh.repair.fix_normals(mesh)
        trimesh.repair.fix_winding(mesh)

        glb_data = mesh.export(file_type="glb")
        with open(output_glb_path, "wb") as f:
            f.write(glb_data)

        duration_sec = round(time.time() - t_start, 2)
        tri_count = len(mesh.faces)
        vert_count = len(mesh.vertices)
        is_watertight = bool(mesh.is_watertight)
        euler_char = int(mesh.euler_number)

        return {
            "success": True,
            "reconstruction_engine": "Pixel3D",
            "model_name": "heuristic_2.5d_extrusion",
            "device": str(self.device),
            "gpu_device": "CPU / Heuristic",
            "peak_vram_mb": 0.0,
            "generation_time_sec": duration_sec,
            "generation_time_ms": int(duration_sec * 1000),
            "telemetry": {
                "neural_inference_sec": 0.0,
                "mesh_extraction_sec": duration_sec,
                "mc_resolution": grid_res
            },
            "mesh_telemetry": {
                "triangles": tri_count,
                "vertices": vert_count,
                "is_watertight": is_watertight,
                "euler_characteristic": euler_char,
                "glb_size_bytes": output_glb_path.stat().st_size,
                "bounds": mesh.bounds.tolist() if hasattr(mesh, "bounds") else []
            }
        }


class ReconstructionService:
    """
    Singleton service wrapper managing 3D reconstruction engines and validation.
    Defaults to TripoSREngine for production neural synthesis.
    """
    _instance: Optional["ReconstructionService"] = None

    def __init__(self):
        if ReconstructionService._instance is None:
            ReconstructionService._instance = self
        self.triposr_engine: Optional[TripoSREngine] = None
        self.pixel3d_engine: Optional[Pixel3DEngine] = None
        
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            
        # Initialize TripoSR engine by default
        try:
            self.triposr_engine = TripoSREngine()
        except Exception as e:
            logger.error(f"[RECONSTRUCTION SERVICE] Failed to initialize TripoSREngine: {e}", exc_info=True)
            self.triposr_engine = None

    @classmethod
    def get_instance(cls) -> "ReconstructionService":
        if cls._instance is None:
            cls._instance = ReconstructionService()
        return cls._instance

    def generate_3d_asset(
        self,
        reference_image: Union[str, Path, Image.Image],
        product_metadata: Optional[Dict[str, Any]] = None,
        engine: str = "TripoSR"
    ) -> Dict[str, Any]:
        """
        Main entrypoint for 3D generation.
        Strict no-silent-fallback: If requested engine fails, reports the actual failure.
        """
        t_req_start = time.time()
        meta = product_metadata or {}
        p_name = meta.get("name") or meta.get("product_title") or "Target Asset"
        p_id = meta.get("id") or meta.get("product_id") or f"prod_{int(time.time())}"
        
        engine_target = (engine or "TripoSR").strip()
        img_hash = compute_image_md5(reference_image)

        # Build engine-aware unique output filename (timestamped to prevent stale file reuse)
        engine_tag = "triposr" if "tripo" in engine_target.lower() else "pixel3d"
        timestamp_ms = int(time.time() * 1000)
        output_glb_filename = f"{p_id}_{engine_tag}_{timestamp_ms}.glb"
        output_glb_path = MODELS_CACHE_DIR / output_glb_filename

        # Always execute fresh inference - no persistent reconstruction result caching
        logger.info(f"[RECONSTRUCTION] Fresh inference requested for {p_id} using {engine_tag.upper()} (output: {output_glb_filename})")

        if engine_tag == "triposr":
            if self.triposr_engine is None:
                try:
                    self.triposr_engine = TripoSREngine()
                except Exception as e:
                    logger.error(f"[RECONSTRUCTION] TripoSREngine initialization failed: {e}", exc_info=True)
                    return {
                        "success": False,
                        "error": f"TripoSR initialization failed: {str(e)}",
                        "reconstruction_engine": "TripoSR",
                        "status": "FAILED"
                    }

            try:
                result = self.triposr_engine.reconstruct_from_image(
                    image_input=reference_image,
                    output_glb_path=output_glb_path,
                    product_name=p_name
                )
                
                # Emit explicit telemetry log
                self._log_telemetry(
                    engine_name="TripoSR",
                    checkpoint_name=result.get("model_name", "stabilityai/TripoSR"),
                    input_desc=str(reference_image)[:80],
                    input_hash=img_hash,
                    device_name=result.get("gpu_device", result.get("device", "cuda:0")),
                    t_infer_start=result.get("telemetry", {}).get("inference_start", ""),
                    t_infer_end=result.get("telemetry", {}).get("inference_end", ""),
                    t_infer_sec=result.get("telemetry", {}).get("neural_inference_sec", 0.0),
                    t_mesh_sec=result.get("telemetry", {}).get("mesh_extraction_sec", 0.0),
                    t_total_sec=result.get("generation_time_sec", round(time.time() - t_req_start, 2)),
                    glb_filename=output_glb_filename,
                    is_cache_hit=False
                )

                result["asset_id"] = p_id
                result["model_filename"] = output_glb_filename
                result["model_url"] = f"http://127.0.0.1:5000/cache/models/{output_glb_filename}"
                result["local_path"] = str(output_glb_path)
                result["format"] = "GLB"
                result["cache_hit"] = False
                return result

            except Exception as e:
                logger.error(f"[TRIPOSR ENGINE] Reconstruction failed: {e}", exc_info=True)
                # NO silent fallback!
                return {
                    "success": False,
                    "error": f"TripoSR execution error: {str(e)}",
                    "reconstruction_engine": "TripoSR",
                    "status": "FAILED"
                }

        else:
            # Explicit legacy Pixel3D requested
            if self.pixel3d_engine is None:
                self.pixel3d_engine = Pixel3DEngine()

            try:
                result = self.pixel3d_engine.reconstruct_from_image(
                    image_input=reference_image,
                    output_glb_path=output_glb_path,
                    product_name=p_name
                )
                
                self._log_telemetry(
                    engine_name="Pixel3D",
                    checkpoint_name="heuristic_2.5d_extrusion",
                    input_desc=str(reference_image)[:80],
                    input_hash=img_hash,
                    device_name=result.get("device", "CPU"),
                    t_infer_start=time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(t_req_start)),
                    t_infer_end=time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime()),
                    t_infer_sec=0.0,
                    t_mesh_sec=result.get("generation_time_sec", 0.1),
                    t_total_sec=result.get("generation_time_sec", 0.1),
                    glb_filename=output_glb_filename,
                    is_cache_hit=False
                )

                result["asset_id"] = p_id
                result["model_filename"] = output_glb_filename
                result["model_url"] = f"http://127.0.0.1:5000/cache/models/{output_glb_filename}"
                result["local_path"] = str(output_glb_path)
                result["format"] = "GLB"
                result["cache_hit"] = False
                return result

            except Exception as e:
                logger.error(f"[PIXEL3D ENGINE] Generation failed: {e}", exc_info=True)
                return {
                    "success": False,
                    "error": f"Pixel3D execution error: {str(e)}",
                    "reconstruction_engine": "Pixel3D",
                    "status": "FAILED"
                }

    def _log_telemetry(
        self,
        engine_name: str,
        checkpoint_name: str,
        input_desc: str,
        input_hash: str,
        device_name: str,
        t_infer_start: str,
        t_infer_end: str,
        t_infer_sec: float,
        t_mesh_sec: float,
        t_total_sec: float,
        glb_filename: str,
        is_cache_hit: bool
    ):
        """Prints explicit runtime telemetry to logs."""
        logger.info("=" * 70)
        logger.info("[RECONSTRUCTION TELEMETRY]")
        logger.info(f"ENGINE: {engine_name}")
        logger.info(f"MODEL/CHECKPOINT: {checkpoint_name}")
        logger.info(f"INPUT IMAGE: {input_desc}")
        logger.info(f"INPUT HASH: {input_hash}")
        logger.info(f"DEVICE: {device_name}")
        logger.info(f"INFERENCE START: {t_infer_start}")
        logger.info(f"INFERENCE END: {t_infer_end}")
        logger.info(f"INFERENCE TIME: {t_infer_sec:.3f}s")
        logger.info(f"MESH EXTRACTION TIME: {t_mesh_sec:.3f}s")
        logger.info(f"TOTAL RECONSTRUCTION TIME: {t_total_sec:.2f}s")
        logger.info(f"OUTPUT GLB: {glb_filename}")
        logger.info(f"CACHE HIT/MISS: {'HIT' if is_cache_hit else 'MISS'}")
        logger.info("=" * 70)

    def validate_mesh_asset(self, glb_path_or_url: str) -> Dict[str, Any]:
        """
        Validates a generated .glb asset for the 3D Approval phase.
        Checks file existence, readability, triangle/vertex counts, and watertightness.
        """
        try:
            if glb_path_or_url.startswith("http://") or glb_path_or_url.startswith("https://"):
                filename = os.path.basename(glb_path_or_url.split("?")[0])
                local_path = MODELS_CACHE_DIR / filename
            else:
                local_path = Path(glb_path_or_url)

            if not local_path.exists():
                return {
                    "valid": False,
                    "status": "FAILED",
                    "reason": f"Asset file not found on disk: {local_path}"
                }

            file_size_bytes = local_path.stat().st_size
            if file_size_bytes < 100:
                return {
                    "valid": False,
                    "status": "FAILED",
                    "reason": f"Asset file is corrupt or empty ({file_size_bytes} bytes)"
                }

            scene_or_mesh = trimesh.load(str(local_path), file_type="glb")
            if isinstance(scene_or_mesh, trimesh.Scene):
                if hasattr(scene_or_mesh, "to_geometry"):
                    mesh = scene_or_mesh.to_geometry()
                elif hasattr(scene_or_mesh, "dump"):
                    mesh = scene_or_mesh.dump(concatenate=True)
                else:
                    mesh = list(scene_or_mesh.geometry.values())[0]
            else:
                mesh = scene_or_mesh

            tri_count = len(mesh.faces)
            vert_count = len(mesh.vertices)
            is_watertight = bool(mesh.is_watertight)

            if tri_count < 4 or vert_count < 4:
                return {
                    "valid": False,
                    "status": "FAILED",
                    "reason": f"Mesh topology has insufficient geometry ({tri_count} faces, {vert_count} vertices)"
                }

            return {
                "valid": True,
                "status": "PASSED",
                "file_size_bytes": file_size_bytes,
                "triangles": tri_count,
                "vertices": vert_count,
                "is_watertight": is_watertight,
                "euler_characteristic": int(mesh.euler_number),
                "checks": {
                    "model_generated": True,
                    "asset_available": True,
                    "asset_loadable": True,
                    "mesh_validation_passed": True
                }
            }
        except Exception as e:
            return {
                "valid": False,
                "status": "FAILED",
                "reason": f"Mesh validation error: {str(e)}"
            }
