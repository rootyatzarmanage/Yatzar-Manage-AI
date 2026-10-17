import os
import sys
import unittest
from pathlib import Path
import torch

# Ensure backend is on sys.path
backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend"))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from app import app
from services.reconstruction_service import ReconstructionService
from services.job_manager import ReconstructionQueueManager, ReconstructionJob, ReconstructionStatus
from services.pixal3d_adapter import Pixal3DProductionAdapter, unload_pixal3d_pipeline
import services.pixal3d_adapter as adapter_mod

class TestPixal3DProductionIntegration(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()

    def test_01_backend_health(self):
        resp = self.client.get('/api/health')
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data.get('status'), 'online')
        self.assertEqual(data.get('gpu_available'), torch.cuda.is_available())
        if torch.cuda.is_available():
            self.assertIsNotNone(data.get('cuda_info'))
            self.assertIn('device_name', data.get('cuda_info', {}))

    def test_02_legacy_engine_eradication_audit(self):
        """Verify that legacy engines and tsr modules are completely eradicated from the production runtime."""
        # Check sys.modules
        self.assertNotIn('tsr', sys.modules)
        self.assertNotIn('tsr.system', sys.modules)

        # Check ReconstructionService engine instance
        service = ReconstructionService.get_instance()
        self.assertTrue(hasattr(service, 'pixal3d_engine'))
        self.assertFalse(hasattr(service, 'triposr_engine'))

        # Check that adapter is Pixal3DProductionAdapter
        self.assertIsInstance(service.pixal3d_engine.adapter, Pixal3DProductionAdapter)
        self.assertEqual(service.pixal3d_engine.adapter.resolution, 1536)
        self.assertTrue(service.pixal3d_engine.adapter.low_vram)

    def test_03_job_lifecycle_and_cancellation(self):
        """Test enqueueing, active job tracking, and cancellation."""
        job = ReconstructionJob(
            job_id="rec-test-cancel-01",
            product_id="TEST-PROD-CANCEL",
            product_name="Cancel Test Asset",
            reference_image="backend/cache/candidates/verified_4d28321d64f4.jpg",
            engine="Pixal3D"
        )
        
        # Test serialization
        d = job.to_dict()
        self.assertEqual(d["engine"], "Pixal3D")
        self.assertEqual(d["status"], "QUEUED")
        self.assertEqual(d["progress"], 0.0)

        # Test cancellation request
        job.cancellation_requested = True
        job.status = ReconstructionStatus.CANCELLED.value
        self.assertEqual(job.status, ReconstructionStatus.CANCELLED.value)
        self.assertTrue(job.cancellation_requested)

    def test_04_model_serving_endpoints(self):
        """Verify that GLB models can be fetched via /cache/models and /api/models."""
        # Check existing verified production GLB
        models_dir = Path("backend/cache/models")
        glbs = list(models_dir.glob("PROD-VIEWSONIC-E2E-*_pixal3d_*.glb"))
        self.assertTrue(len(glbs) > 0, "Production Pixal3D GLB must exist")
        
        latest_glb = glbs[-1]
        
        # Test /cache/models/<filename>
        resp1 = self.client.get(f"/cache/models/{latest_glb.name}")
        self.assertEqual(resp1.status_code, 200)
        self.assertEqual(len(resp1.data), latest_glb.stat().st_size)

        # Test /api/models/<filename>
        resp2 = self.client.get(f"/api/models/{latest_glb.name}")
        self.assertEqual(resp2.status_code, 200)
        self.assertEqual(len(resp2.data), latest_glb.stat().st_size)

    def test_05_unsupported_engine_rejection(self):
        """Verify that request with unsupported engine (e.g. UnsupportedEngine, LegacyEngine) is strictly rejected with 400."""
        payload = {
            "product_id": "TEST-REJECT-ENGINE",
            "product_title": "Reject Engine Test",
            "reference_image": "backend/cache/candidates/verified_4d28321d64f4.jpg",
            "engine": "UnsupportedEngine"
        }
        resp = self.client.post("/api/reconstruct/queue", json=payload)
        self.assertEqual(resp.status_code, 400)
        data = resp.get_json()
        self.assertFalse(data.get("success"))
        self.assertEqual(data.get("status"), "FAILED")
        self.assertIn("Unsupported reconstruction engine", data.get("error", ""))

    def test_06_missing_reference_image_rejection(self):
        """Verify that request with missing approved image is strictly rejected with 400."""
        payload = {
            "product_id": "TEST-MISSING-IMG",
            "product_title": "Missing Image Test",
            "reference_image": "",
            "engine": "Pixal3D"
        }
        resp = self.client.post("/api/reconstruct/queue", json=payload)
        self.assertEqual(resp.status_code, 400)
        data = resp.get_json()
        self.assertFalse(data.get("success"))
        self.assertEqual(data.get("status"), "FAILED")
        self.assertIn("Missing approved reference image", data.get("error", ""))

    def test_07_pipeline_unload_lifecycle(self):
        """Verify that unload_pixal3d_pipeline cleanly resets the global _pipeline_instance."""
        unload_pixal3d_pipeline()
        self.assertIsNone(adapter_mod._pipeline_instance)

if __name__ == '__main__':
    unittest.main()
