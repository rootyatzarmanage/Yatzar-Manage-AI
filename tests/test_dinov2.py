"""
Comprehensive unit tests for DINOv2 Feature Extraction, Cross-View Metric Comparison,
and 2D Scatter Coordinate Projection.
"""

import os
import sys
import unittest
import numpy as np
from PIL import Image, ImageDraw

# Add backend directory to path
backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend"))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from services.dinov2_service import DinoV2Engine, get_dinov2_engine


class TestDinoV2Engine(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        print("\n--- Initializing DINOv2 Engine for Unit Tests ---")
        cls.engine = get_dinov2_engine("dinov2_vits14")
        print(f"Engine Device: {cls.engine.device}")

    def create_synthetic_image(self, primary_color=(50, 120, 220), shape_type="rectangle"):
        """Creates a synthetic test image with crisp geometric features."""
        img = Image.new("RGB", (300, 300), color=(240, 240, 240))
        draw = ImageDraw.Draw(img)
        if shape_type == "rectangle":
            draw.rectangle([60, 60, 240, 240], fill=primary_color, outline=(20, 20, 20), width=4)
            draw.rectangle([100, 100, 200, 200], fill=(255, 255, 255))
        elif shape_type == "ellipse":
            draw.ellipse([50, 50, 250, 250], fill=primary_color, outline=(20, 20, 20), width=4)
            draw.ellipse([90, 90, 210, 210], fill=(255, 200, 50))
        elif shape_type == "noise":
            noise_arr = np.random.randint(0, 256, (300, 300, 3), dtype=np.uint8)
            return Image.fromarray(noise_arr)
        return img

    def test_01_feature_extraction_shapes_and_norms(self):
        """Test feature extraction output dimensions and L2 normalization."""
        test_img = self.create_synthetic_image()
        features = self.engine.extract_features(test_img, return_numpy=True)

        cls_token = features["cls_token"]
        patch_tokens = features["patch_tokens"]

        # Check shapes
        self.assertEqual(cls_token.shape, (384,))
        self.assertEqual(patch_tokens.shape, (256, 384))

        # Check L2 unit norms
        cls_norm = np.linalg.norm(cls_token)
        self.assertAlmostEqual(cls_norm, 1.0, places=4)

        patch_norms = np.linalg.norm(patch_tokens, axis=-1)
        self.assertTrue(np.allclose(patch_norms, 1.0, atol=1e-4))
        print("[OK] Feature extraction shapes (384,) and (256, 384) & L2 normalization verified.")

    def test_02_self_similarity(self):
        """Test that identical image similarity evaluates to 1.0."""
        test_img = self.create_synthetic_image()
        feat_a = self.engine.extract_features(test_img)
        feat_b = self.engine.extract_features(test_img)

        sim_result = self.engine.compute_similarity(feat_a, feat_b)

        self.assertAlmostEqual(sim_result["global_similarity"], 1.0, places=3)
        self.assertAlmostEqual(sim_result["patch_score"], 1.0, places=3)
        self.assertAlmostEqual(sim_result["composite_score"], 1.0, places=3)
        print(f"[OK] Self-similarity verified: {sim_result}")

    def test_03_similarity_ranking_and_patch_matching(self):
        """Test that related viewpoints have higher similarity than unrelated images."""
        seed_img = self.create_synthetic_image(primary_color=(30, 100, 240), shape_type="rectangle")
        similar_img = self.create_synthetic_image(primary_color=(40, 110, 230), shape_type="rectangle")
        distinct_img = self.create_synthetic_image(primary_color=(240, 30, 50), shape_type="ellipse")
        noise_img = self.create_synthetic_image(shape_type="noise")

        feat_seed = self.engine.extract_features(seed_img)
        feat_similar = self.engine.extract_features(similar_img)
        feat_distinct = self.engine.extract_features(distinct_img)
        feat_noise = self.engine.extract_features(noise_img)

        sim_similar = self.engine.compute_similarity(feat_seed, feat_similar)
        sim_distinct = self.engine.compute_similarity(feat_seed, feat_distinct)
        sim_noise = self.engine.compute_similarity(feat_seed, feat_noise)

        print(f"Seed vs Similar View:  Composite = {sim_similar['composite_score']}, Global = {sim_similar['global_similarity']}, Patch = {sim_similar['patch_score']}")
        print(f"Seed vs Distinct View: Composite = {sim_distinct['composite_score']}, Global = {sim_distinct['global_similarity']}, Patch = {sim_distinct['patch_score']}")
        print(f"Seed vs Pure Noise:    Composite = {sim_noise['composite_score']}, Global = {sim_noise['global_similarity']}, Patch = {sim_noise['patch_score']}")

        self.assertGreater(sim_similar["composite_score"], sim_distinct["composite_score"])
        self.assertGreater(sim_distinct["composite_score"], sim_noise["composite_score"])
        print("[OK] Metric ranking test passed.")

    def test_04_pca_2d_scatter_projection(self):
        """Test PCA 2D coordinates projection relative to seed at (0, 0)."""
        images = [
            self.create_synthetic_image((30, 100, 240), "rectangle"),  # Seed
            self.create_synthetic_image((40, 110, 230), "rectangle"),  # Candidate 1
            self.create_synthetic_image((20, 90, 250), "rectangle"),   # Candidate 2
            self.create_synthetic_image((240, 50, 30), "ellipse"),     # Candidate 3
            self.create_synthetic_image(shape_type="noise"),            # Candidate 4
        ]

        cls_vectors = [self.engine.extract_features(img, return_numpy=True)["cls_token"] for img in images]
        coords = DinoV2Engine.compute_2d_scatter_coordinates(cls_vectors)

        self.assertEqual(len(coords), len(images))
        # Seed must be anchored at (0.0, 0.0)
        self.assertEqual(coords[0]["x"], 0.0)
        self.assertEqual(coords[0]["y"], 0.0)

        for i, pt in enumerate(coords):
            self.assertIn("x", pt)
            self.assertIn("y", pt)
            self.assertIsInstance(pt["x"], float)
            self.assertIsInstance(pt["y"], float)
            print(f"Point {i}: ({pt['x']}, {pt['y']})")

        print("[OK] 2D PCA scatter coordinates projection relative to seed verified.")


if __name__ == "__main__":
    unittest.main()
