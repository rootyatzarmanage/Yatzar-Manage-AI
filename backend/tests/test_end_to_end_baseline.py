"""
End-to-End Autonomous Baseline Integration Test for Yatzar.
Verifies the complete 5-stage pipeline:
1. Input
2. Research (Product-ID-first retrieval + DINOv2 dedup + visual cross-verification)
3. Image Approval (Automatic best reference selection)
4. 3D Generate (Pixel 3D real .glb synthesis)
5. 3D Approval (Automated manifold mesh validation)
"""

import unittest
import os
import json
import base64
import numpy as np
from PIL import Image
import io

from app import app
from services.reconstruction_service import ReconstructionService

class TestAutonomousBaseline(unittest.TestCase):
    def setUp(self):
        self.app = app.test_client()
        self.app.testing = True

    def _create_sample_image_base64(self, color=(180, 190, 200), size=(256, 256)):
        img = Image.new('RGB', size, color=color)
        buf = io.BytesIO()
        img.save(buf, format='JPEG')
        b64 = base64.b64encode(buf.getvalue()).decode('utf-8')
        return f"data:image/jpeg;base64,{b64}"

    def test_01_research_and_verification_pipeline(self):
        """Test Research phase: product-ID query, DINOv2 deduplication, cross-verification, and best_reference."""
        seed_b64 = self._create_sample_image_base64(color=(40, 60, 90))
        payload = {
            "product_title": "Hansgrohe C51 Kitchen Sink",
            "product_sku": "43218000",
            "seed_image": seed_b64
        }
        res = self.app.post("/api/v1/scrape", data=json.dumps(payload), content_type="application/json")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data.get("success"))
        self.assertIn("images", data)
        self.assertIn("summary", data)
        
        # Verify clean research summary format
        summary = data["summary"]
        self.assertIn("total_retrieved", summary)
        self.assertIn("duplicates_removed", summary)
        self.assertIn("rejected_as_irrelevant", summary)
        self.assertIn("verified_count", summary)
        self.assertIn("selected_reference", summary)
        
        # Check best reference is provided
        if data.get("best_reference"):
            self.assertIn("url", data["best_reference"])
            self.assertEqual(data["best_reference"].get("status"), "VERIFIED")

    def test_02_reconstruct_endpoint_generates_real_glb(self):
        """Test 3D Generate phase: Pixel 3D synthesis generates real .glb file."""
        seed_b64 = self._create_sample_image_base64(color=(30, 90, 160))
        payload = {
            "reference_image": seed_b64,
            "product_title": "Alfa Laval Heat Exchanger",
            "product_sku": "AL-HEX-9000",
            "product_id": "PROD-TEST-01"
        }
        res = self.app.post("/api/v1/reconstruct", data=json.dumps(payload), content_type="application/json")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data.get("success"))
        self.assertIn("model_url", data)
        self.assertIn("model_path", data)
        self.assertTrue(os.path.exists(data["model_path"]))
        self.assertTrue(data["model_path"].endswith(".glb"))
        
        # Verify mesh stats
        stats = data.get("mesh_stats", {})
        self.assertGreater(stats.get("vertex_count", 0), 0)
        self.assertGreater(stats.get("face_count", 0), 0)
        self.assertTrue(stats.get("watertight"))
        self.assertEqual(stats.get("euler_characteristic"), 2)

    def test_03_validate_3d_endpoint(self):
        """Test 3D Approval phase: validate-3d checks real GLB mesh integrity."""
        # First generate a test asset
        service = ReconstructionService.get_instance()
        res_gen = service.generate_3d_asset(
            reference_image=self._create_sample_image_base64(),
            product_metadata={"name": "Validation Test Product", "id": "VAL-01"}
        )
        self.assertTrue(res_gen["success"])
        model_url = res_gen["model_url"]
        local_path = res_gen["local_path"]
        self.assertTrue(os.path.exists(local_path))
        
        # Validate endpoint
        payload = {
            "model_url": model_url,
            "local_path": local_path
        }
        res = self.app.post("/api/v1/validate-3d", data=json.dumps(payload), content_type="application/json")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data.get("success"))
        self.assertEqual(data.get("status"), "PASSED")
        self.assertTrue(data["validation"]["checks"]["asset_available"])
        self.assertTrue(data["validation"]["checks"]["mesh_validation_passed"])

    def test_04_glb_asset_static_serving(self):
        """Test static route serves .glb binary with proper model/gltf-binary mimetype."""
        service = ReconstructionService.get_instance()
        res_gen = service.generate_3d_asset(
            reference_image=self._create_sample_image_base64(),
            product_metadata={"name": "Serving Test", "id": "SRV-01"}
        )
        self.assertTrue(res_gen["success"])
        model_url = res_gen["model_url"]
        
        # Extract relative path from model_url (e.g. /cache/models/...)
        rel_url = "/" + model_url.split("5000/")[1] if "5000/" in model_url else model_url
        
        # Request static endpoint
        res = self.app.get(rel_url)
        self.assertEqual(res.status_code, 200)
        self.assertGreater(len(res.data), 100)
        # Verify GLB magic bytes: 'glTF' = 0x676c5446
        self.assertEqual(res.data[:4], b'glTF')

if __name__ == '__main__':
    unittest.main()
