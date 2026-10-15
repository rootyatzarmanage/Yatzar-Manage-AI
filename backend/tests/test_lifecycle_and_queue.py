import os
os.environ["OPENBLAS_NUM_THREADS"] = "1"
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"
os.environ["NUMEXPR_NUM_THREADS"] = "1"

import sys
import time
import unittest
import threading
from unittest.mock import MagicMock, patch

# Ensure backend path is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

try:
    import services.job_manager as job_mgr_mod
    from services.job_manager import (
        ResearchJobManager,
        ReconstructionQueueManager,
        ResearchJob,
        ReconstructionJob,
        JobStatus,
        ReconstructionStatus
    )
except ImportError:
    import backend.services.job_manager as job_mgr_mod
    from backend.services.job_manager import (
        ResearchJobManager,
        ReconstructionQueueManager,
        ResearchJob,
        ReconstructionJob,
        JobStatus,
        ReconstructionStatus
    )

ScrapingPipelineManager = job_mgr_mod.ScrapingPipelineManager
ReconstructionService = job_mgr_mod.ReconstructionService

class TestResearchJobLifecycleAndQueue(unittest.TestCase):
    def setUp(self):
        # Create isolated managers for unit/integration tests
        self._orig_scraper_init = ScrapingPipelineManager.__init__
        ScrapingPipelineManager.__init__ = lambda self, *args, **kwargs: None
        self.research_mgr = ResearchJobManager(max_workers=3)
        self.research_mgr._jobs.clear()
        self.research_mgr._product_to_latest_job.clear()
        self.reconstruct_mgr = ReconstructionQueueManager()
        self.reconstruct_mgr._jobs.clear()
        self.reconstruct_mgr._product_to_job.clear()
        self.reconstruct_mgr._queue.clear()

    def tearDown(self):
        ScrapingPipelineManager.__init__ = self._orig_scraper_init
        # Cleanly shutdown executors
        self.research_mgr._executor.shutdown(wait=False)
        self.reconstruct_mgr._executor.shutdown(wait=False)

    # -------------------------------------------------------------
    # 1. Start Research Explicitly
    # -------------------------------------------------------------
    def test_01_start_research_explicitly(self):
        payload = {"id": "TEST-PROD-01", "name": "Ergonomic Office Chair", "brand": "Herman Miller"}

        mock_return = {
            "candidates": [{"url": "http://img1.png", "is_selected_reference": True}],
            "best_reference": {"url": "http://img1.png"},
            "total_harvested": 1,
            "total_accepted": 1,
            "seed_coordinates": {"x": 0.0, "y": 0.0},
            "research_summary": {"total_candidates": 1}
        }

        with patch.object(ScrapingPipelineManager, "execute_pipeline", return_value=mock_return):
            job = self.research_mgr.start_research_job(payload)
            self.assertIsNotNone(job)
            self.assertEqual(job.product_id, "TEST-PROD-01")
            self.assertIn(job.status, [JobStatus.QUEUED.value, JobStatus.RUNNING.value, JobStatus.COMPLETED.value])

            for _ in range(60):
                if job.status == JobStatus.COMPLETED.value:
                    break
                time.sleep(0.02)

            self.assertEqual(job.status, JobStatus.COMPLETED.value)
            self.assertIsNotNone(job.results)
            self.assertEqual(len(job.results.get("images", [])), 1)

    # -------------------------------------------------------------
    # 2. Existing RUNNING Job is Reused (No Duplicate Start)
    # -------------------------------------------------------------
    def test_02_running_job_is_reused_no_duplicate(self):
        payload = {"id": "TEST-PROD-02", "name": "Modern Lamp"}

        def slow_pipeline(*args, **kwargs):
            time.sleep(0.2)
            return {"candidates": [], "total_harvested": 0, "total_accepted": 0}

        with patch.object(ScrapingPipelineManager, "execute_pipeline", side_effect=slow_pipeline):
            job1 = self.research_mgr.start_research_job(payload)
            self.assertIn(job1.status, [JobStatus.QUEUED.value, JobStatus.RUNNING.value])

            # Second start request for the same product while first is running
            job2 = self.research_mgr.start_research_job(payload)
            self.assertEqual(job1.job_id, job2.job_id, "Must return existing job instance")

    # -------------------------------------------------------------
    # 3. Existing COMPLETED Job is Retained and Retrievable
    # -------------------------------------------------------------
    def test_03_completed_job_is_reused(self):
        payload = {"id": "TEST-PROD-03", "name": "Standing Desk"}
        mock_ret = {
            "candidates": [{"url": "http://desk.png"}],
            "best_reference": {"url": "http://desk.png"},
            "total_harvested": 1,
            "total_accepted": 1
        }

        with patch.object(ScrapingPipelineManager, "execute_pipeline", return_value=mock_ret):
            job1 = self.research_mgr.start_research_job(payload)
            for _ in range(60):
                if job1.status == JobStatus.COMPLETED.value:
                    break
                time.sleep(0.02)
            self.assertEqual(job1.status, JobStatus.COMPLETED.value)

            # Re-querying by product ID should return existing completed job and results without scraping again
            job2 = self.research_mgr.get_job_by_id_or_product("TEST-PROD-03")
            self.assertIsNotNone(job2)
            self.assertEqual(job1.job_id, job2.job_id)
            self.assertEqual(job2.status, JobStatus.COMPLETED.value)
            self.assertEqual(len(job2.results.get("images", [])), 1)

    # -------------------------------------------------------------
    # 4. Existing FAILED Job Does Not Auto-Retry
    # -------------------------------------------------------------
    def test_04_failed_job_does_not_auto_retry(self):
        payload = {"id": "TEST-PROD-04", "name": "Faulty Product"}

        def raise_timeout(*args, **kwargs):
            raise RuntimeError("Network Timeout")

        with patch.object(ScrapingPipelineManager, "execute_pipeline", side_effect=raise_timeout):
            job1 = self.research_mgr.start_research_job(payload)
            for _ in range(60):
                if job1.status == JobStatus.FAILED.value:
                    break
                time.sleep(0.02)
            self.assertEqual(job1.status, JobStatus.FAILED.value)

            # Normal get returns existing failed job
            job2 = self.research_mgr.get_job_by_id_or_product("TEST-PROD-04")
            self.assertEqual(job2.status, JobStatus.FAILED.value)

    # -------------------------------------------------------------
    # 5. Explicit Retry Works
    # -------------------------------------------------------------
    def test_05_explicit_retry_works(self):
        payload = {"id": "TEST-PROD-05", "name": "Retry Product"}
        attempt = 0

        def retry_pipeline(*args, **kwargs):
            nonlocal attempt
            attempt += 1
            if attempt == 1:
                raise RuntimeError("Attempt 1 network failure")
            return {"candidates": [{"url": "http://success.png"}], "total_harvested": 1, "total_accepted": 1}

        with patch.object(ScrapingPipelineManager, "execute_pipeline", side_effect=retry_pipeline):
            job1 = self.research_mgr.start_research_job(payload)
            for _ in range(60):
                if job1.status == JobStatus.FAILED.value:
                    break
                time.sleep(0.02)
            self.assertEqual(job1.status, JobStatus.FAILED.value)

            # Trigger explicit retry INSIDE the patch context
            retried_job = self.research_mgr.retry_research_job("TEST-PROD-05")
            self.assertIsNotNone(retried_job)
            self.assertEqual(retried_job.retry_count, 1)

            for _ in range(60):
                if retried_job.status == JobStatus.COMPLETED.value:
                    break
                time.sleep(0.02)

            self.assertEqual(retried_job.status, JobStatus.COMPLETED.value)
            self.assertEqual(attempt, 2)

    # -------------------------------------------------------------
    # 6. Explicit Cancel Works
    # -------------------------------------------------------------
    def test_06_explicit_cancel_works(self):
        payload = {"id": "TEST-PROD-06", "name": "Cancel Product"}

        def slow_cancel_pipeline(*args, **kwargs):
            cancel_fn = kwargs.get("cancellation_check")
            for _ in range(40):
                if cancel_fn and cancel_fn():
                    return {"cancelled": True, "candidates": []}
                time.sleep(0.02)
            return {"candidates": []}

        with patch.object(ScrapingPipelineManager, "execute_pipeline", side_effect=slow_cancel_pipeline):
            job = self.research_mgr.start_research_job(payload)
            time.sleep(0.03)

            cancelled = self.research_mgr.cancel_research_job("TEST-PROD-06")
            self.assertTrue(cancelled)

            for _ in range(60):
                if job.status == JobStatus.CANCELLED.value:
                    break
                time.sleep(0.02)

            self.assertEqual(job.status, JobStatus.CANCELLED.value)
            self.assertTrue(job.cancellation_requested)

    # -------------------------------------------------------------
    # 7. Concurrent Research for Multiple Products
    # -------------------------------------------------------------
    def test_07_concurrent_research_multiple_products(self):
        active_counts = []
        lock = threading.Lock()
        active_now = 0

        def concurrent_pipeline(*args, **kwargs):
            nonlocal active_now
            with lock:
                active_now += 1
                active_counts.append(active_now)
            time.sleep(0.1)
            with lock:
                active_now -= 1
            return {
                "candidates": [{"url": "http://img.png"}],
                "total_harvested": 1,
                "total_accepted": 1
            }

        with patch.object(ScrapingPipelineManager, "execute_pipeline", side_effect=concurrent_pipeline):
            job_a = self.research_mgr.start_research_job({"id": "PROD-CONCUR-A", "brand": "BrandA"})
            job_b = self.research_mgr.start_research_job({"id": "PROD-CONCUR-B", "brand": "BrandB"})
            job_c = self.research_mgr.start_research_job({"id": "PROD-CONCUR-C", "brand": "BrandC"})

            for _ in range(60):
                if (job_a.status == JobStatus.COMPLETED.value and 
                    job_b.status == JobStatus.COMPLETED.value and 
                    job_c.status == JobStatus.COMPLETED.value):
                    break
                time.sleep(0.02)

            self.assertEqual(job_a.status, JobStatus.COMPLETED.value)
            self.assertEqual(job_b.status, JobStatus.COMPLETED.value)
            self.assertEqual(job_c.status, JobStatus.COMPLETED.value)
            self.assertGreater(max(active_counts), 1, "Research jobs ran concurrently")

    # -------------------------------------------------------------
    # 8. Product A State Cannot Overwrite Product B State
    # -------------------------------------------------------------
    def test_08_product_isolation(self):
        def pipeline_a(p_name):
            return {"candidates": [{"url": "http://a.png"}], "research_summary": {"note": "Summary A"}}

        def pipeline_b(p_name):
            return {"candidates": [{"url": "http://b.png"}], "research_summary": {"note": "Summary B"}}

        def side_effect(*args, **kwargs):
            p_name = kwargs.get("product_title") or kwargs.get("product_name") or kwargs.get("product_id") or ""
            if "ProdA" in str(p_name):
                return pipeline_a(p_name)
            return pipeline_b(p_name)

        with patch.object(ScrapingPipelineManager, "execute_pipeline", side_effect=side_effect):
            job_a = self.research_mgr.start_research_job({"id": "PROD-ISO-A", "name": "ProdA Chair"})
            job_b = self.research_mgr.start_research_job({"id": "PROD-ISO-B", "name": "ProdB Faucet"})

            for _ in range(60):
                if job_a.status == JobStatus.COMPLETED.value and job_b.status == JobStatus.COMPLETED.value:
                    break
                time.sleep(0.02)

            self.assertEqual(job_a.results["summary"]["note"], "Summary A")
            self.assertEqual(job_b.results["summary"]["note"], "Summary B")
            self.assertNotEqual(job_a.results["images"][0]["url"], job_b.results["images"][0]["url"])

    # -------------------------------------------------------------
    # 9. Reconstruction Queue: MAX CONCURRENCY = 1 (SERIALIZED)
    # -------------------------------------------------------------
    def test_09_reconstruction_queue_serialized_one_at_a_time(self):
        active_gpu_ops = []
        lock = threading.Lock()
        current_active = 0

        def mock_pixal3d(*args, **kwargs):
            nonlocal current_active
            with lock:
                current_active += 1
                active_gpu_ops.append(current_active)
            time.sleep(0.08)
            with lock:
                current_active -= 1
            return {
                "success": True,
                "asset_id": "asset-rec",
                "model_url": "/cache/models/sample.glb",
                "local_path": "cache/models/sample.glb",
                "model_filename": "sample.glb",
                "generation_time_ms": 2050,
                "generation_time_sec": 2.05,
                "reconstruction_engine": "Pixal3D",
                "mesh_stats": {"faces": 45000, "vertices": 23000}
            }

        mock_service = MagicMock()
        mock_service.generate_3d_asset.side_effect = mock_pixal3d
        mock_service.validate_mesh_asset.return_value = {"valid": True, "faces": 45000}

        with patch.object(ReconstructionService, "get_instance", return_value=mock_service):
            rec_job_1 = self.reconstruct_mgr.enqueue_reconstruction(
                product_id="REC-PROD-01",
                reference_image="http://img1.png",
                product_name="Product One",
                engine="Pixal3D"
            )
            rec_job_2 = self.reconstruct_mgr.enqueue_reconstruction(
                product_id="REC-PROD-02",
                reference_image="http://img2.png",
                product_name="Product Two",
                engine="Pixal3D"
            )

            for _ in range(60):
                if (rec_job_1.status == ReconstructionStatus.COMPLETED.value and 
                    rec_job_2.status == ReconstructionStatus.COMPLETED.value):
                    break
                time.sleep(0.02)

            self.assertEqual(rec_job_1.status, ReconstructionStatus.COMPLETED.value)
            self.assertEqual(rec_job_2.status, ReconstructionStatus.COMPLETED.value)
            self.assertEqual(max(active_gpu_ops), 1, "Pixal3D GPU reconstruction MUST BE SERIALIZED (MAX = 1)")

    # -------------------------------------------------------------
    # 10. Exact Approved Image is Handed to Pixal3D
    # -------------------------------------------------------------
    def test_10_exact_approved_image_handoff(self):
        captured_image_ref = None

        def mock_reconstruct(*args, **kwargs):
            nonlocal captured_image_ref
            ref = kwargs.get("reference_image") or (args[1] if len(args) > 1 else args[0] if len(args) > 0 else None)
            captured_image_ref = ref
            return {
                "success": True,
                "asset_id": "asset-exact",
                "model_url": "/cache/models/exact.glb",
                "local_path": "cache/models/exact.glb",
                "model_filename": "exact.glb",
                "generation_time_sec": 2.05,
                "generation_time_ms": 2050,
                "reconstruction_engine": "Pixal3D",
                "mesh_stats": {"faces": 45000, "vertices": 23000}
            }

        mock_service = MagicMock()
        mock_service.generate_3d_asset.side_effect = mock_reconstruct
        mock_service.validate_mesh_asset.return_value = {"valid": True}

        selected_image_url = "http://cdn.yatzar.ai/unique_selected_angle_side_view.jpg"

        with patch.object(ReconstructionService, "get_instance", return_value=mock_service):
            rec_job = self.reconstruct_mgr.enqueue_reconstruction(
                product_id="EXACT-PROD-01",
                reference_image=selected_image_url,
                product_name="Exact Chair",
                engine="Pixal3D"
            )

            for _ in range(60):
                if rec_job.status == ReconstructionStatus.COMPLETED.value:
                    break
                time.sleep(0.02)

            self.assertEqual(rec_job.reference_image, selected_image_url)
            self.assertEqual(captured_image_ref, selected_image_url)
            self.assertEqual(rec_job.status, ReconstructionStatus.COMPLETED.value)

    # -------------------------------------------------------------
    # 11. Safe Cancellation of Queued Reconstruction Job
    # -------------------------------------------------------------
    def test_11_cancel_queued_reconstruction(self):
        def slow_reconstruct(*args, **kwargs):
            time.sleep(0.2)
            return {
                "success": True,
                "asset_id": "asset-slow",
                "model_url": "/model.glb",
                "local_path": "cache/models/sample.glb",
                "model_filename": "sample.glb",
                "generation_time_sec": 2.05,
                "generation_time_ms": 2050,
                "reconstruction_engine": "Pixal3D",
                "mesh_stats": {"faces": 45000, "vertices": 23000}
            }

        mock_service = MagicMock()
        mock_service.generate_3d_asset.side_effect = slow_reconstruct
        mock_service.validate_mesh_asset.return_value = {"valid": True}

        with patch.object(ReconstructionService, "get_instance", return_value=mock_service):
            # First job takes the single GPU slot
            job1 = self.reconstruct_mgr.enqueue_reconstruction("BLOCKING-01", "http://img1.png", "Blocking Product")
            # Second job is queued
            job2 = self.reconstruct_mgr.enqueue_reconstruction("QUEUED-02", "http://img2.png", "Queued Product")

            self.assertEqual(job2.status, ReconstructionStatus.QUEUED.value)

            # Cancel the queued job before GPU slot becomes free
            cancelled = self.reconstruct_mgr.cancel_reconstruction("QUEUED-02")
            self.assertTrue(cancelled)
            self.assertEqual(job2.status, ReconstructionStatus.CANCELLED.value)

    # -------------------------------------------------------------
    # 12. Completion Persists and Restores after Reload
    # -------------------------------------------------------------
    def test_12_completion_persists_after_reload(self):
        payload = {"id": "TEST-PROD-12", "name": "Persistent Product"}
        mock_ret = {
            "candidates": [{"url": "http://persist.png"}],
            "best_reference": {"url": "http://persist.png"},
            "total_harvested": 1,
            "total_accepted": 1
        }

        with patch.object(ScrapingPipelineManager, "execute_pipeline", return_value=mock_ret):
            job = self.research_mgr.start_research_job(payload)
            for _ in range(60):
                if job.status == JobStatus.COMPLETED.value:
                    break
                time.sleep(0.02)
            self.assertEqual(job.status, JobStatus.COMPLETED.value)

        # Create a fresh manager instance to simulate backend process reboot / reload
        fresh_mgr = ResearchJobManager(max_workers=2)
        restored_job = fresh_mgr.get_job_by_id_or_product("TEST-PROD-12")
        self.assertIsNotNone(restored_job, "Job must restore from disk cache")
        self.assertEqual(restored_job.status, JobStatus.COMPLETED.value)
        self.assertIsNotNone(restored_job.results)
        fresh_mgr._executor.shutdown(wait=False)

    # -------------------------------------------------------------
    # 13. Regression Test: Reconstruction Status Canonical Contract
    # -------------------------------------------------------------
    def test_13_reconstruction_status_canonical_contract(self):
        """
        REGRESSION PROOF for Bug 1:
        Given top-level job status = COMPLETED and result.status = MODEL_READY,
        the API response MUST preserve response.status == 'COMPLETED'
        while response.result.status == 'MODEL_READY' and frontend-consumed
        model information is retained.
        """
        from app import app
        client = app.test_client()

        with patch("app.reconstruct_queue_manager") as mock_mgr:
            mock_mgr.get_job_status.return_value = {
                "job_id": "JOB-CANONICAL-01",
                "product_id": "PROD-CANONICAL-01",
                "status": "COMPLETED",
                "queue_position": 0,
                "result": {
                    "status": "MODEL_READY",
                    "model_url": "http://127.0.0.1:5000/cache/models/canonical.glb",
                    "model_path": "cache/models/canonical.glb",
                    "generation_time_sec": 3.82,
                    "mesh_stats": {
                        "vertex_count": 42108,
                        "face_count": 84212,
                        "watertight": True
                    }
                }
            }

            resp = client.get("/api/reconstruct/status/PROD-CANONICAL-01")
            self.assertEqual(resp.status_code, 200)
            data = resp.get_json()

            # CANONICAL STATUS: response.status MUST remain COMPLETED (not MODEL_READY)
            self.assertEqual(data["status"], "COMPLETED")
            # Result metadata status preserved inside result:
            self.assertIn("result", data)
            self.assertEqual(data["result"]["status"], "MODEL_READY")
            # Frontend-consumed model info directly accessible
            self.assertEqual(data["model_url"], "http://127.0.0.1:5000/cache/models/canonical.glb")
            self.assertEqual(data["mesh_stats"]["vertex_count"], 42108)
            self.assertEqual(data["job"]["status"], "COMPLETED")

    # -------------------------------------------------------------
    # 14. Regression Test: All Lifecycle Statuses Preserved Against Result Overwrites
    # -------------------------------------------------------------
    def test_14_lifecycle_statuses_not_overwritten_by_metadata(self):
        """
        Verify that QUEUED, RECONSTRUCTING, RUNNING, COMPLETED, FAILED, CANCELLED
        are NEVER overwritten if result metadata is present.
        """
        from app import app
        client = app.test_client()

        statuses_to_test = ["QUEUED", "RECONSTRUCTING", "RUNNING", "COMPLETED", "FAILED", "CANCELLED"]

        for expected_status in statuses_to_test:
            with patch("app.reconstruct_queue_manager") as mock_mgr:
                mock_mgr.get_job_status.return_value = {
                    "job_id": f"JOB-{expected_status}",
                    "product_id": f"PROD-{expected_status}",
                    "status": expected_status,
                    "queue_position": 1 if expected_status == "QUEUED" else 0,
                    "result": {
                        "status": "MODEL_READY",
                        "model_url": "http://127.0.0.1:5000/cache/models/test.glb"
                    }
                }

                resp = client.get(f"/api/reconstruct/status/PROD-{expected_status}")
                self.assertEqual(resp.status_code, 200)
                data = resp.get_json()

                # MUST expose expected lifecycle status at top-level
                self.assertEqual(data["status"], expected_status, f"Status {expected_status} was corrupted")

if __name__ == "__main__":
    unittest.main()

