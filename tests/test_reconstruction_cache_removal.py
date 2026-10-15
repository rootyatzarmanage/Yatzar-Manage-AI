"""
Automated Verification Suite for Complete Removal of Reconstruction Cache
Specifically verifies requirements:
- TEST 1: Same image reconstructed twice -> Two independent reconstruction executions.
- TEST 2: Same product reconstructed twice -> Second request does NOT reuse the first result.
- TEST 3: Different images reconstructed sequentially -> Second result belongs to second request.
- TEST 4: Retry a completed/failed reconstruction -> Retry executes a fresh reconstruction.
- TEST 5: No reconstruction-cache lookup exists in the execution path.
- TEST 6: Frontend contains no reconstruction-cache UI/state.
"""

import os
import sys
import unittest
import tempfile
import time
from pathlib import Path
from PIL import Image
import numpy as np

backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend"))
if backend_dir in sys.path:
    sys.path.remove(backend_dir)
sys.path.insert(0, backend_dir)

from services.reconstruction_service import ReconstructionService, MODELS_OUTPUT_DIR
from services.job_manager import ReconstructionQueueManager, ReconstructionStatus
from app import app


class TestReconstructionCacheRemoval(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.client = app.test_client()
        cls.service = ReconstructionService.get_instance()

        cls.tmp_dir = tempfile.TemporaryDirectory()
        cls.tmp_path = Path(cls.tmp_dir.name)

        # Image A (Red)
        cls.img_a_path = cls.tmp_path / "img_a.png"
        img_a = Image.new("RGB", (256, 256), color=(255, 0, 0))
        img_a.save(cls.img_a_path)

        # Image B (Blue)
        cls.img_b_path = cls.tmp_path / "img_b.png"
        img_b = Image.new("RGB", (256, 256), color=(0, 0, 255))
        img_b.save(cls.img_b_path)

    @classmethod
    def tearDownClass(cls):
        cls.tmp_dir.cleanup()

    def test_01_same_image_reconstructed_twice(self):
        """
        TEST 1: Same image reconstructed twice.
        Expected: Two independent reconstruction executions.
        """
        initial_count = getattr(self.service, "call_count", 0)

        payload1 = {
            "reference_image": str(self.img_a_path),
            "product_title": "Identical Test Product",
            "product_sku": "SKU-SAME-IMG",
            "product_id": "PROD-SAME-1",
            "engine": "Pixal3D"
        }
        resp1 = self.client.post("/api/v1/reconstruct?sync=true", json=payload1)
        self.assertEqual(resp1.status_code, 200)
        data1 = resp1.get_json()
        self.assertTrue(data1.get("success"))
        file1 = data1.get("model_filename")
        token1 = data1.get("request_token")
        call_count1 = data1.get("call_count")

        time.sleep(0.02)

        # Reconstruct exactly the same image again
        payload2 = {
            "reference_image": str(self.img_a_path),
            "product_title": "Identical Test Product",
            "product_sku": "SKU-SAME-IMG",
            "product_id": "PROD-SAME-2",
            "engine": "Pixal3D"
        }
        resp2 = self.client.post("/api/v1/reconstruct?sync=true", json=payload2)
        self.assertEqual(resp2.status_code, 200)
        data2 = resp2.get_json()
        self.assertTrue(data2.get("success"))
        file2 = data2.get("model_filename")
        token2 = data2.get("request_token")
        call_count2 = data2.get("call_count")

        # Independent executions:
        self.assertNotEqual(file1, file2, "Each request must generate a distinct unique model file")
        self.assertNotEqual(token1, token2, "Each request must have a distinct request token")
        self.assertEqual(call_count2, call_count1 + 1, "Call count must strictly increment for second inference")
        self.assertNotIn("cache_hit", data1, "Response must not contain cache_hit")
        self.assertNotIn("cache_hit", data2, "Response must not contain cache_hit")
        print(f"[OK] TEST 1: Same image reconstructed twice executed independent inferences: calls {call_count1} -> {call_count2}")

    def test_02_same_product_reconstructed_twice(self):
        """
        TEST 2: Same product reconstructed twice.
        Expected: Second request does NOT reuse the first result.
        """
        product_id = "PROD-REUSE-CHECK"
        payload = {
            "reference_image": str(self.img_a_path),
            "product_title": "Product Reuse Check",
            "product_sku": "SKU-REUSE",
            "product_id": product_id,
            "engine": "Pixal3D"
        }

        # Run 1
        resp1 = self.client.post("/api/v1/reconstruct?sync=true", json=payload)
        data1 = resp1.get_json()
        self.assertEqual(resp1.status_code, 200)
        file1 = data1.get("model_filename")
        call_count1 = data1.get("call_count")

        time.sleep(0.02)

        # Run 2 on same product
        resp2 = self.client.post("/api/v1/reconstruct?sync=true", json=payload)
        data2 = resp2.get_json()
        self.assertEqual(resp2.status_code, 200)
        file2 = data2.get("model_filename")
        call_count2 = data2.get("call_count")

        self.assertNotEqual(file1, file2, "Second request for same product must NOT reuse first result")
        self.assertGreater(call_count2, call_count1, "Inference must be executed anew for same product")
        print(f"[OK] TEST 2: Same product requested twice did NOT reuse result: {file1} != {file2}")

    def test_03_different_images_reconstructed_sequentially(self):
        """
        TEST 3: Different images reconstructed sequentially.
        Expected: Second result belongs to the second request and is not the first model.
        """
        payload_a = {
            "reference_image": str(self.img_a_path),
            "product_title": "Product A",
            "product_sku": "SKU-SEQ-A",
            "product_id": "PROD-SEQ-A",
            "engine": "Pixal3D"
        }
        resp_a = self.client.post("/api/v1/reconstruct?sync=true", json=payload_a)
        data_a = resp_a.get_json()
        self.assertEqual(resp_a.status_code, 200)
        file_a = data_a.get("model_filename")
        token_a = data_a.get("request_token")

        payload_b = {
            "reference_image": str(self.img_b_path),
            "product_title": "Product B",
            "product_sku": "SKU-SEQ-B",
            "product_id": "PROD-SEQ-B",
            "engine": "Pixal3D"
        }
        resp_b = self.client.post("/api/v1/reconstruct?sync=true", json=payload_b)
        data_b = resp_b.get_json()
        self.assertEqual(resp_b.status_code, 200)
        file_b = data_b.get("model_filename")
        token_b = data_b.get("request_token")

        self.assertNotEqual(file_a, file_b)
        self.assertNotEqual(token_a, token_b)
        self.assertIn("PROD-SEQ-A", file_a)
        self.assertIn("PROD-SEQ-B", file_b)
        print(f"[OK] TEST 3: Sequential different images produced distinct models: {file_a} vs {file_b}")

    def test_04_retry_reconstruction(self):
        """
        TEST 4: Retry a completed/failed reconstruction.
        Expected: Retry executes a fresh reconstruction with a new job ID and new model output.
        """
        # Step 1: Initial enqueue
        payload = {
            "reference_image": str(self.img_a_path),
            "product_title": "Retry Test Product",
            "product_sku": "SKU-RETRY-01",
            "product_id": "PROD-RETRY-01",
            "engine": "Pixal3D"
        }
        resp1 = self.client.post("/api/v1/reconstruct/queue", json=payload)
        self.assertEqual(resp1.status_code, 202)
        initial_job_id = resp1.get_json()["job_id"]

        # Wait for completion
        t_start = time.time()
        while time.time() - t_start < 10.0:
            st = self.client.get(f"/api/v1/reconstruct/status/{initial_job_id}").get_json()
            if st.get("status") in [ReconstructionStatus.COMPLETED.value, ReconstructionStatus.FAILED.value]:
                break
            time.sleep(0.1)

        st1 = self.client.get(f"/api/v1/reconstruct/status/{initial_job_id}").get_json()
        self.assertEqual(st1.get("status"), ReconstructionStatus.COMPLETED.value)
        orig_file = st1.get("model_filename")
        orig_call_count = st1.get("call_count")

        # Step 2: Request RETRY via endpoint
        retry_resp = self.client.post(f"/api/v1/reconstruct/retry/{initial_job_id}")
        self.assertEqual(retry_resp.status_code, 202)
        retry_job_id = retry_resp.get_json()["job_id"]
        self.assertNotEqual(initial_job_id, retry_job_id, "Retry must assign a fresh job ID")

        # Wait for retry completion
        t_start = time.time()
        while time.time() - t_start < 10.0:
            st = self.client.get(f"/api/v1/reconstruct/status/{retry_job_id}").get_json()
            if st.get("status") in [ReconstructionStatus.COMPLETED.value, ReconstructionStatus.FAILED.value]:
                break
            time.sleep(0.1)

        st2 = self.client.get(f"/api/v1/reconstruct/status/{retry_job_id}").get_json()
        self.assertEqual(st2.get("status"), ReconstructionStatus.COMPLETED.value)
        retry_file = st2.get("model_filename")
        retry_call_count = st2.get("call_count")

        self.assertNotEqual(orig_file, retry_file, "Retry must produce a fresh model output file")
        self.assertGreater(retry_call_count, orig_call_count, "Retry must execute fresh inference")
        print(f"[OK] TEST 4: Retry executed fresh reconstruction: job {initial_job_id} -> {retry_job_id}")

    def test_05_no_cache_lookup_in_execution_path(self):
        """
        TEST 5: No reconstruction-cache lookup exists in the execution path.
        Verifies that ReconstructionService code and job execution path has no cache lookup,
        no image hash -> model mapping, and no short-circuit.
        """
        import inspect
        src_service = inspect.getsource(ReconstructionService.generate_3d_asset)
        src_pixal = inspect.getsource(self.service.pixal3d_engine.reconstruct_from_image)
        src_queue = inspect.getsource(ReconstructionQueueManager._process_queue_item)

        # Check for cache hit branches or cache lookup statements
        forbidden_phrases = [
            "cache_hit = True",
            "if cached_model",
            "if model_cache.has",
            "return cached",
            "is_cache_hit = True",
            "cache.get(",
        ]
        for phrase in forbidden_phrases:
            self.assertNotIn(phrase, src_service, f"Forbidden cache phrase '{phrase}' in ReconstructionService")
            self.assertNotIn(phrase, src_pixal, f"Forbidden cache phrase '{phrase}' in Pixal3DEngine")
            self.assertNotIn(phrase, src_queue, f"Forbidden cache phrase '{phrase}' in QueueManager")

        print("[OK] TEST 5: Verified zero cache-lookup or short-circuit branches in execution path.")

    def test_06_frontend_contains_no_cache_ui(self):
        """
        TEST 6: Frontend contains no reconstruction-cache UI/state.
        Scans frontend JSX components for cache hit/miss or reconstruction cache status strings.
        """
        frontend_dir = Path(__file__).resolve().parent.parent / "frontend" / "src"
        forbidden_ui_strings = [
            "reconstruction cache",
            "cache hit",
            "cache miss",
            "cached model",
            "model reused from cache",
            "cache age",
            "cached result",
        ]

        found_violations = []
        for jsx_file in frontend_dir.rglob("*.jsx"):
            content = jsx_file.read_text(encoding="utf-8").lower()
            for s in forbidden_ui_strings:
                if s in content:
                    found_violations.append(f"{jsx_file.name}: contains '{s}'")

        self.assertEqual(found_violations, [], f"Frontend contains forbidden cache UI strings: {found_violations}")
        print("[OK] TEST 6: Verified frontend components contain zero reconstruction-cache UI/state.")


if __name__ == "__main__":
    unittest.main()
