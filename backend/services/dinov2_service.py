"""
DINOv2 Feature Extraction, Cross-View Metric Comparison, and PCA Projection Engine.
Provides patch-level structural similarity, CLS global semantic similarity,
and 2D t-SNE/PCA coordinates projection relative to seed references.
"""

import io
import math
import logging
import requests
from typing import Union, List, Dict, Tuple, Any, Optional
import numpy as np
from PIL import Image

import torch
import torch.nn.functional as F
import torchvision.transforms as transforms
from torchvision.transforms import InterpolationMode
from sklearn.decomposition import PCA

logger = logging.getLogger(__name__)


class DinoV2Engine:
    """
    High-performance feature extraction and metric comparison engine powered by Meta's DINOv2.
    """

    def __init__(
        self,
        model_name: str = "dinov2_vits14",
        device: Optional[str] = None
    ):
        """
        Initializes the DINOv2 model and caches it on GPU or CPU.
        """
        if device is None:
            self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        else:
            self.device = torch.device(device)

        logger.info(f"Initializing DINOv2 ({model_name}) on device: {self.device}")
        
        # Load pre-trained DINOv2 model from torch.hub (uses local torch cache)
        self.model = torch.hub.load("facebookresearch/dinov2", model_name)
        self.model.to(self.device)
        self.model.eval()

        # Standard ImageNet normalization and 224x224 bicubic interpolation
        self.transform = transforms.Compose([
            transforms.Resize((224, 224), interpolation=InterpolationMode.BICUBIC, antialias=True),
            transforms.ToTensor(),
            transforms.Normalize(
                mean=[0.485, 0.456, 0.406],
                std=[0.229, 0.224, 0.225]
            )
        ])

    def _load_image(self, image_input: Union[str, bytes, Image.Image, np.ndarray, torch.Tensor]) -> Image.Image:
        """
        Loads and converts various image input formats into an RGB PIL Image.
        """
        if isinstance(image_input, Image.Image):
            return image_input.convert("RGB")

        if isinstance(image_input, bytes):
            return Image.open(io.BytesIO(image_input)).convert("RGB")

        if isinstance(image_input, np.ndarray):
            if image_input.dtype != np.uint8:
                if image_input.max() <= 1.0:
                    image_input = (image_input * 255).astype(np.uint8)
                else:
                    image_input = image_input.astype(np.uint8)
            return Image.fromarray(image_input).convert("RGB")

        if isinstance(image_input, str):
            # Check if Data URL (base64)
            if image_input.startswith("data:"):
                import base64
                header, data_part = image_input.split(",", 1)
                img_bytes = base64.b64decode(data_part)
                return Image.open(io.BytesIO(img_bytes)).convert("RGB")
            # Check if URL
            if image_input.startswith("http://") or image_input.startswith("https://"):
                headers = {"User-Agent": "YatzarManageAI/1.0 (DINOv2 Pipeline)"}
                resp = requests.get(image_input, headers=headers, timeout=12)
                resp.raise_for_status()
                return Image.open(io.BytesIO(resp.content)).convert("RGB")
            # Local filesystem path
            return Image.open(image_input).convert("RGB")

        raise ValueError(f"Unsupported image input type: {type(image_input)}")

    def preprocess(self, image_input: Union[str, bytes, Image.Image, np.ndarray, torch.Tensor]) -> torch.Tensor:
        """
        Preprocesses an image to a (1, 3, 224, 224) normalized tensor on the engine device.
        """
        if isinstance(image_input, torch.Tensor):
            tensor = image_input
            if tensor.dim() == 3:
                tensor = tensor.unsqueeze(0)
            if tensor.shape[-2:] != (224, 224):
                tensor = F.interpolate(tensor, size=(224, 224), mode="bicubic", align_corners=False)
            return tensor.to(self.device).float()

        pil_img = self._load_image(image_input)
        tensor = self.transform(pil_img)  # Shape: (3, 224, 224)
        tensor = tensor.unsqueeze(0).to(self.device)  # Shape: (1, 3, 224, 224)
        return tensor

    def extract_features(
        self,
        image_input: Union[str, bytes, Image.Image, np.ndarray, torch.Tensor],
        return_numpy: bool = False
    ) -> Dict[str, Any]:
        """
        Extracts both global normalized [CLS] token and dense spatial patch tokens.

        Returns:
            Dict containing:
                - 'cls_token': L2-normalized 1D vector (384-dim)
                - 'patch_tokens': L2-normalized 2D matrix (256, 384) (16x16 grid for 224x224 input)
        """
        tensor = self.preprocess(image_input)

        with torch.no_grad():
            features_dict = self.model.forward_features(tensor)
            
            # x_norm_clstoken shape: (1, 384)
            cls_token = features_dict["x_norm_clstoken"][0]
            # Ensure unit norm
            cls_token = F.normalize(cls_token, p=2, dim=-1)

            # x_norm_patchtokens shape: (1, 256, 384)
            patch_tokens = features_dict["x_norm_patchtokens"][0]
            # Ensure unit norm per patch
            patch_tokens = F.normalize(patch_tokens, p=2, dim=-1)

        if return_numpy:
            return {
                "cls_token": cls_token.cpu().numpy(),
                "patch_tokens": patch_tokens.cpu().numpy()
            }

        return {
            "cls_token": cls_token,
            "patch_tokens": patch_tokens
        }

    def compute_similarity(
        self,
        seed_features: Union[Dict[str, Any], Tuple[Any, Any]],
        candidate_features: Union[Dict[str, Any], Tuple[Any, Any]],
        top_k_percent: float = 0.20
    ) -> Dict[str, float]:
        """
        Calculates composite similarity between seed and candidate features:
        1. Global Cosine Similarity via dot product on normalized [CLS] tokens.
        2. Patch-level structural similarity using top-k (20%) max cosine patch matches
           to capture shared chassis materials, contours, and sub-components across viewpoints.
        3. composite_score = (0.4 * global_sim) + (0.6 * patch_score).

        Returns:
            Dict with 'composite_score', 'global_similarity', 'patch_score'.
        """
        # Unpack seed features
        if isinstance(seed_features, dict):
            seed_cls = seed_features["cls_token"]
            seed_patches = seed_features["patch_tokens"]
        else:
            seed_cls, seed_patches = seed_features

        # Unpack candidate features
        if isinstance(candidate_features, dict):
            cand_cls = candidate_features["cls_token"]
            cand_patches = candidate_features["patch_tokens"]
        else:
            cand_cls, cand_patches = candidate_features

        # Convert to torch tensor on device if numpy array
        if isinstance(seed_cls, np.ndarray):
            seed_cls = torch.from_numpy(seed_cls)
        if isinstance(cand_cls, np.ndarray):
            cand_cls = torch.from_numpy(cand_cls)
        if isinstance(seed_patches, np.ndarray):
            seed_patches = torch.from_numpy(seed_patches)
        if isinstance(cand_patches, np.ndarray):
            cand_patches = torch.from_numpy(cand_patches)

        seed_cls = seed_cls.to(self.device).view(-1)
        cand_cls = cand_cls.to(self.device).view(-1)
        seed_patches = seed_patches.to(self.device)
        cand_patches = cand_patches.to(self.device)

        # 1. Global Cosine Similarity
        seed_cls_norm = F.normalize(seed_cls, p=2, dim=-1)
        cand_cls_norm = F.normalize(cand_cls, p=2, dim=-1)
        global_sim = float(torch.dot(seed_cls_norm, cand_cls_norm).clamp(-1.0, 1.0).item())

        # 2. Dense Patch-Level Structural Similarity
        seed_patches_norm = F.normalize(seed_patches, p=2, dim=-1)  # (N_seed, 384)
        cand_patches_norm = F.normalize(cand_patches, p=2, dim=-1)  # (N_cand, 384)

        # Cross-patch cosine similarity matrix: (N_seed, N_cand)
        sim_matrix = torch.matmul(seed_patches_norm, cand_patches_norm.transpose(0, 1))

        # Best candidate patch match for each seed patch
        max_per_seed, _ = torch.max(sim_matrix, dim=1)  # (N_seed,)
        k_seed = max(1, int(math.ceil(len(max_per_seed) * top_k_percent)))
        topk_seed, _ = torch.topk(max_per_seed, k=k_seed)
        seed_patch_mean = topk_seed.mean().item()

        # Best seed patch match for each candidate patch (symmetric check)
        max_per_cand, _ = torch.max(sim_matrix, dim=0)  # (N_cand,)
        k_cand = max(1, int(math.ceil(len(max_per_cand) * top_k_percent)))
        topk_cand, _ = torch.topk(max_per_cand, k=k_cand)
        cand_patch_mean = topk_cand.mean().item()

        # Bidirectional top-k structural patch score
        patch_score = float(0.5 * (seed_patch_mean + cand_patch_mean))

        # 3. Composite Score: 40% global semantic + 60% dense structural patch
        composite_score = float((0.4 * global_sim) + (0.6 * patch_score))

        return {
            "composite_score": round(max(0.0, min(1.0, composite_score)), 4),
            "global_similarity": round(max(-1.0, min(1.0, global_sim)), 4),
            "patch_score": round(max(0.0, min(1.0, patch_score)), 4)
        }

    @staticmethod
    def compute_2d_scatter_coordinates(
        vector_list: List[Union[np.ndarray, torch.Tensor, List[float]]]
    ) -> List[Dict[str, float]]:
        """
        Projects high-dimensional CLS vectors (384-dim) into 2D scatter coordinates
        using Principal Component Analysis (PCA).
        The seed vector at index 0 is anchored to (0.0, 0.0), and all other candidate
        points are positioned relative to the seed.

        Returns:
            List of dicts: [{'x': float, 'y': float}, ...]
        """
        if not vector_list:
            return []

        # Convert all vectors to 2D numpy float32 matrix
        np_vectors = []
        for v in vector_list:
            if isinstance(v, torch.Tensor):
                np_vectors.append(v.detach().cpu().float().numpy().reshape(-1))
            elif isinstance(v, np.ndarray):
                np_vectors.append(v.astype(np.float32).reshape(-1))
            elif isinstance(v, list):
                np_vectors.append(np.array(v, dtype=np.float32).reshape(-1))
            else:
                raise ValueError(f"Unsupported vector format in vector_list: {type(v)}")

        matrix = np.vstack(np_vectors)  # Shape: (N, D)
        n_samples, n_features = matrix.shape

        if n_samples == 1:
            return [{"x": 0.0, "y": 0.0}]

        if n_samples == 2:
            # For 2 points, project along line connecting them
            diff = matrix[1] - matrix[0]
            dist = float(np.linalg.norm(diff))
            return [
                {"x": 0.0, "y": 0.0},
                {"x": round(dist, 4), "y": 0.0}
            ]

        # Use PCA for n_samples >= 3
        pca = PCA(n_components=2, random_state=42)
        projected = pca.fit_transform(matrix)  # Shape: (N, 2)

        # Shift coordinate system so the seed at index 0 is exactly (0.0, 0.0)
        seed_coord = projected[0]
        centered_coords = projected - seed_coord

        result = []
        for pt in centered_coords:
            result.append({
                "x": round(float(pt[0]), 4),
                "y": round(float(pt[1]), 4)
            })

        return result


# Singleton instance cache for backend services
_GLOBAL_ENGINE: Optional[DinoV2Engine] = None


def get_dinov2_engine(model_name: str = "dinov2_vits14") -> DinoV2Engine:
    """
    Returns the cached singleton DinoV2Engine instance.
    """
    global _GLOBAL_ENGINE
    if _GLOBAL_ENGINE is None:
        _GLOBAL_ENGINE = DinoV2Engine(model_name=model_name)
    return _GLOBAL_ENGINE
