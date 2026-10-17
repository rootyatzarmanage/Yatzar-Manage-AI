"""
Independent Background Research Jobs & Serialized Pixal3D Reconstruction Queue Manager.

Architecture:
1. ResearchJobManager:
   - Concurrency: MULTI-WORKER CONCURRENT (ThreadPoolExecutor max_workers=4)
   - Manages independent background research jobs per product.
   - Bounded stage timeouts, cancellation tokens, deterministic terminal states (QUEUED, RUNNING, COMPLETED, FAILED, CANCELLED).
   - In-memory state with disk cache persistence (backend/cache/jobs/).

2. ReconstructionQueueManager:
   - Concurrency: STRICTLY SERIALIZED (max_workers=1, MAX CONCURRENCY = 1)
   - Single GPU execution slot for TencentARC Pixal3D on NVIDIA RTX 4060 GPU.
   - Preserves exact approved image URL/path across queuing.
   - Safe cancellation of queued jobs.
"""

import os
import time
import json
import uuid
import logging
import threading
from pathlib import Path
from typing import Dict, Any, Optional, List
from concurrent.futures import ThreadPoolExecutor, Future
from enum import Enum

logger = logging.getLogger(__name__)

try:
    from services.scraper_service import ScrapingPipelineManager
    from services.reconstruction_service import ReconstructionService
except ImportError:
    from backend.services.scraper_service import ScrapingPipelineManager
    from backend.services.reconstruction_service import ReconstructionService

JOBS_CACHE_DIR = Path(__file__).resolve().parent.parent / "cache" / "jobs"
JOBS_CACHE_DIR.mkdir(parents=True, exist_ok=True)


class JobStatus(str, Enum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class ReconstructionStatus(str, Enum):
    QUEUED = "QUEUED"
    RECONSTRUCTING = "RECONSTRUCTING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class ResearchJob:
    def __init__(
        self,
        job_id: str,
        product_id: str,
        product_payload: Dict[str, Any]
    ):
        self.job_id = job_id
        self.product_id = product_id
        self.product_payload = product_payload
        self.status = JobStatus.QUEUED.value
        self.created_at = time.time()
        self.started_at: Optional[float] = None
        self.completed_at: Optional[float] = None
        self.progress = 0.0
        self.current_phase = "Queued"
        self.elapsed_time_sec = 0.0
        self.candidate_count = 0
        self.results: Optional[Dict[str, Any]] = None
        self.error: Optional[str] = None
        self.retry_count = 0
        self.cancellation_requested = False
        self.cancel_reason: Optional[str] = None
        self.stage_telemetry: Dict[str, Any] = {}

    def to_dict(self) -> Dict[str, Any]:
        elapsed = self.elapsed_time_sec
        if self.status == JobStatus.RUNNING.value and self.started_at:
            elapsed = round(time.time() - self.started_at, 2)
        elif self.completed_at and self.started_at:
            elapsed = round(self.completed_at - self.started_at, 2)

        return {
            "job_id": self.job_id,
            "product_id": self.product_id,
            "product_name": self.product_payload.get("name") or self.product_payload.get("product_title") or "",
            "product_sku": self.product_payload.get("modelNumber") or self.product_payload.get("product_sku") or "",
            "status": self.status,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "progress": round(self.progress, 2),
            "current_phase": self.current_phase,
            "elapsed_time_sec": elapsed,
            "executionTime": f"{elapsed}s",
            "candidate_count": self.candidate_count,
            "error": self.error,
            "retry_count": self.retry_count,
            "cancellation_requested": self.cancellation_requested,
            "cancel_reason": self.cancel_reason,
            "stage_telemetry": self.stage_telemetry,
            "has_results": bool(self.results)
        }


class ReconstructionJob:
    def __init__(
        self,
        job_id: str,
        product_id: str,
        product_name: str,
        reference_image: str,
        engine: str = "Pixal3D",
        product_metadata: Optional[Dict[str, Any]] = None
    ):
        self.job_id = job_id
        self.product_id = product_id
        self.product_name = product_name
        self.reference_image = reference_image
        self.engine = "Pixal3D"
        self.product_metadata = product_metadata or {}
        self.status = ReconstructionStatus.QUEUED.value
        self.current_phase = "Queued"
        self.progress = 0.0
        self.created_at = time.time()
        self.started_at: Optional[float] = None
        self.completed_at: Optional[float] = None
        self.generation_time_sec: Optional[float] = None
        self.result: Optional[Dict[str, Any]] = None
        self.error: Optional[str] = None
        self.cancellation_requested = False

    def to_dict(self, queue_position: int = 0) -> Dict[str, Any]:
        elapsed = 0.0
        if self.status == ReconstructionStatus.RECONSTRUCTING.value and self.started_at:
            elapsed = round(time.time() - self.started_at, 2)
        elif self.completed_at and self.started_at:
            elapsed = round(self.completed_at - self.started_at, 2)

        return {
            "job_id": self.job_id,
            "product_id": self.product_id,
            "product_name": self.product_name,
            "reference_image": self.reference_image,
            "engine": self.engine,
            "status": self.status,
            "current_phase": self.current_phase,
            "progress": self.progress,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "elapsed_time_sec": elapsed,
            "generation_time_sec": self.generation_time_sec or elapsed,
            "queue_position": queue_position,
            "error": self.error,
            "cancellation_requested": self.cancellation_requested,
            "has_result": bool(self.result),
            "result": self.result if self.status == ReconstructionStatus.COMPLETED.value else None
        }


# ============================================================================
# RESEARCH JOB MANAGER (CONCURRENT / BACKGROUND)
# ============================================================================
class ResearchJobManager:
    _instance: Optional["ResearchJobManager"] = None
    _lock = threading.Lock()

    def __init__(self, max_workers: int = 4):
        self._max_workers = max_workers
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="research_worker")
        self._jobs: Dict[str, ResearchJob] = {}  # job_id -> ResearchJob
        self._product_to_latest_job: Dict[str, str] = {}  # product_id -> job_id
        self._futures: Dict[str, Future] = {}
        self._jobs_lock = threading.RLock()
        self._load_persisted_jobs()

    @classmethod
    def get_instance(cls) -> "ResearchJobManager":
        with cls._lock:
            if cls._instance is None:
                cls._instance = ResearchJobManager()
            return cls._instance

    def _get_cache_path(self, product_id: str) -> Path:
        safe_id = "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in product_id)
        return JOBS_CACHE_DIR / f"research_{safe_id}.json"

    def _persist_job(self, job: ResearchJob):
        """Persists completed job results to disk cache for restart/refresh recovery."""
        try:
            if job.status in [JobStatus.COMPLETED.value, JobStatus.FAILED.value]:
                cache_file = self._get_cache_path(job.product_id)
                data = {
                    "job_id": job.job_id,
                    "product_id": job.product_id,
                    "status": job.status,
                    "created_at": job.created_at,
                    "started_at": job.started_at,
                    "completed_at": job.completed_at,
                    "elapsed_time_sec": job.elapsed_time_sec,
                    "candidate_count": job.candidate_count,
                    "results": job.results,
                    "error": job.error,
                    "retry_count": job.retry_count,
                    "product_payload": job.product_payload
                }
                with open(cache_file, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2)
        except Exception as e:
            logger.warning(f"[JOB MANAGER] Could not persist research job {job.job_id}: {e}")

    def _load_persisted_jobs(self):
        """Loads completed research jobs from disk cache into memory."""
        try:
            for cache_file in JOBS_CACHE_DIR.glob("research_*.json"):
                with open(cache_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    job = ResearchJob(
                        job_id=data.get("job_id", f"job-{uuid.uuid4().hex[:8]}"),
                        product_id=data.get("product_id", "PROD-UNKNOWN"),
                        product_payload=data.get("product_payload", {})
                    )
                    job.status = data.get("status", JobStatus.COMPLETED.value)
                    job.created_at = data.get("created_at", time.time())
                    job.started_at = data.get("started_at")
                    job.completed_at = data.get("completed_at")
                    job.elapsed_time_sec = data.get("elapsed_time_sec", 0.0)
                    job.candidate_count = data.get("candidate_count", 0)
                    job.results = data.get("results")
                    job.error = data.get("error")
                    job.progress = 1.0 if job.status == JobStatus.COMPLETED.value else 0.0
                    job.current_phase = "Complete" if job.status == JobStatus.COMPLETED.value else "Failed"

                    self._jobs[job.job_id] = job
                    self._product_to_latest_job[job.product_id] = job.job_id
        except Exception as e:
            logger.warning(f"[JOB MANAGER] Error loading persisted research jobs: {e}")

    def start_research_job(self, product_payload: Dict[str, Any], force_restart: bool = False) -> ResearchJob:
        """
        Starts an independent background research job for a product.
        If a job is already RUNNING or QUEUED for this product, reattaches to it (NO duplicate jobs).
        """
        product_id = product_payload.get("id") or product_payload.get("product_id") or f"PROD-{uuid.uuid4().hex[:6]}"
        
        with self._jobs_lock:
            existing_job_id = self._product_to_latest_job.get(product_id)
            if existing_job_id and existing_job_id in self._jobs:
                existing_job = self._jobs[existing_job_id]
                # Reattach if active
                if existing_job.status in [JobStatus.QUEUED.value, JobStatus.RUNNING.value] and not force_restart:
                    logger.info(f"[JOB MANAGER] Reattaching to existing {existing_job.status} job {existing_job.job_id} for product {product_id}")
                    return existing_job

            # Create new job
            job_id = f"res-job-{uuid.uuid4().hex[:8]}"
            job = ResearchJob(
                job_id=job_id,
                product_id=product_id,
                product_payload=product_payload
            )
            self._jobs[job_id] = job
            self._product_to_latest_job[product_id] = job_id

            # Invalidate stale persisted cache file for this product
            try:
                cache_file = self._get_cache_path(product_id)
                if cache_file.exists():
                    cache_file.unlink()
            except Exception as e:
                logger.debug(f"[JOB MANAGER] Cache unlink notice: {e}")

            logger.info(f"[JOB MANAGER] Created new ResearchJob {job_id} for product {product_id} (Status: QUEUED)")

            future = self._executor.submit(self._run_research_worker, job)
            self._futures[job_id] = future

            return job

    def retry_research_job(self, product_id_or_job_id: str) -> ResearchJob:
        """Explicitly retries a FAILED or CANCELLED research job."""
        with self._jobs_lock:
            job = self.get_job_by_id_or_product(product_id_or_job_id)
            if not job:
                raise ValueError(f"No research job found for {product_id_or_job_id}")

            payload = job.product_payload
            retry_count = job.retry_count + 1

        new_job = self.start_research_job(payload, force_restart=True)
        new_job.retry_count = retry_count
        return new_job

    def cancel_research_job(self, product_id_or_job_id: str, reason: str = "User cancelled") -> bool:
        """Explicitly cancels an active research job."""
        with self._jobs_lock:
            job = self.get_job_by_id_or_product(product_id_or_job_id)
            if not job:
                return False

            if job.status in [JobStatus.COMPLETED.value, JobStatus.FAILED.value, JobStatus.CANCELLED.value]:
                return True

            job.cancellation_requested = True
            job.cancel_reason = reason

            if job.status == JobStatus.QUEUED.value:
                job.status = JobStatus.CANCELLED.value
                job.completed_at = time.time()
                job.current_phase = "Cancelled"
                self._persist_job(job)
                logger.info(f"[JOB MANAGER] Cancelled queued research job {job.job_id}")
                return True

            logger.info(f"[JOB MANAGER] Requested cancellation for running research job {job.job_id}")
            return True

    def get_job_by_id_or_product(self, identifier: str) -> Optional[ResearchJob]:
        """Looks up job by job_id or product_id."""
        with self._jobs_lock:
            if identifier in self._jobs:
                return self._jobs[identifier]
            job_id = self._product_to_latest_job.get(identifier)
            if job_id and job_id in self._jobs:
                return self._jobs[job_id]
            return None

    def get_job_status(self, identifier: str) -> Optional[Dict[str, Any]]:
        job = self.get_job_by_id_or_product(identifier)
        if not job:
            return None
        return job.to_dict()

    def get_job_results(self, identifier: str) -> Optional[Dict[str, Any]]:
        job = self.get_job_by_id_or_product(identifier)
        if not job or job.status != JobStatus.COMPLETED.value or not job.results:
            return None
        return job.results

    def list_active_jobs(self) -> List[Dict[str, Any]]:
        with self._jobs_lock:
            active = []
            for j in self._jobs.values():
                if j.status in [JobStatus.QUEUED.value, JobStatus.RUNNING.value]:
                    active.append(j.to_dict())
            return sorted(active, key=lambda x: x["created_at"], reverse=True)

    def list_all_jobs(self) -> List[Dict[str, Any]]:
        with self._jobs_lock:
            return [j.to_dict() for j in self._jobs.values()]

    def _run_research_worker(self, job: ResearchJob):
        """Worker thread executing the research cascade with strict bounded timeouts & cancellation tokens."""
        job.started_at = time.time()
        job.status = JobStatus.RUNNING.value
        job.progress = 0.10
        job.current_phase = "Identity Normalization & Query Planning"

        logger.info(f"[JOB WORKER {job.job_id}] Started background research for '{job.product_id}'")

        try:
            # Check cancellation token
            if job.cancellation_requested:
                job.status = JobStatus.CANCELLED.value
                job.completed_at = time.time()
                job.current_phase = "Cancelled"
                self._persist_job(job)
                return

            payload = job.product_payload
            seed_image = payload.get("seed_image") or payload.get("thumbnail") or payload.get("image")
            product_title = payload.get("name") or payload.get("product_title") or ""
            model_number = payload.get("modelNumber") or payload.get("model_number") or ""
            article_number = payload.get("articleNumber") or payload.get("article_number") or ""
            part_number = payload.get("partNumber") or payload.get("part_number") or ""
            product_sku = payload.get("product_sku") or payload.get("sku") or model_number or article_number or part_number
            brand = payload.get("brand") or payload.get("manufacturer") or ""
            category = payload.get("category") or ""
            user_prompt = payload.get("prompt") or payload.get("user_prompt") or payload.get("description") or ""
            dynamic_urls = payload.get("sourceUrls") or payload.get("dynamic_urls") or []

            def cancellation_check():
                return job.cancellation_requested

            def progress_callback(phase: str, pct: float):
                job.current_phase = phase
                job.progress = min(0.95, max(0.10, pct))
                job.elapsed_time_sec = round(time.time() - job.started_at, 2)

            pipeline_manager = ScrapingPipelineManager()
            
            # Execute bounded research pipeline
            pipeline_result = pipeline_manager.execute_pipeline(
                seed_image=seed_image,
                max_candidates=15,
                similarity_threshold=0.60,
                dynamic_urls=dynamic_urls,
                product_title=product_title,
                product_sku=product_sku,
                product_id=job.product_id,
                model_number=model_number,
                article_number=article_number,
                part_number=part_number,
                brand=brand,
                category=category,
                user_prompt=user_prompt,
                cancellation_check=cancellation_check,
                progress_callback=progress_callback
            )

            # Final check before committing completed results
            if job.cancellation_requested or pipeline_result.get("cancelled"):
                job.status = JobStatus.CANCELLED.value
                job.completed_at = time.time()
                job.current_phase = "Cancelled"
                job.elapsed_time_sec = round(job.completed_at - job.started_at, 2)
                self._persist_job(job)
                logger.info(f"[JOB WORKER {job.job_id}] Research job cancelled during execution")
                return

            candidates = pipeline_result.get("candidates", [])
            elapsed_sec = round(time.time() - job.started_at, 2)
            
            job.results = {
                "success": True,
                "job_id": job.job_id,
                "product_id": job.product_id,
                "totalImagesFound": pipeline_result.get("total_harvested", len(candidates)),
                "totalAccepted": pipeline_result.get("total_accepted", len(candidates)),
                "images": candidates,
                "curated_images": candidates,
                "rejected_images": pipeline_result.get("rejected_candidates", []),
                "seed_coordinates": pipeline_result.get("seed_coordinates", {"x": 0.0, "y": 0.0}),
                "relatedUrls": [{"title": f"Source: {u}", "url": u} for u in dynamic_urls],
                "research_duration_sec": elapsed_sec,
                "executionTime": f"{elapsed_sec}s",
                "telemetry": pipeline_result.get("telemetry_timing", {}),
                "plannedQueries": pipeline_result.get("planned_queries", []),
                "summary": pipeline_result.get("research_summary", {}),
                "research_summary": pipeline_result.get("research_summary", {}),
                "best_reference": pipeline_result.get("best_reference"),
                "gpuDevice": "NVIDIA GeForce RTX 4060 Laptop GPU"
            }

            job.candidate_count = len(candidates)
            job.status = JobStatus.COMPLETED.value
            job.completed_at = time.time()
            job.progress = 1.0
            job.current_phase = "Complete"
            job.elapsed_time_sec = elapsed_sec
            self._persist_job(job)

            logger.info(f"[JOB WORKER {job.job_id}] Research COMPLETED in {elapsed_sec}s with {len(candidates)} candidates")

        except Exception as e:
            logger.error(f"[JOB WORKER {job.job_id}] Research FAILED with error: {e}", exc_info=True)
            job.status = JobStatus.FAILED.value
            job.completed_at = time.time()
            job.elapsed_time_sec = round(job.completed_at - (job.started_at or job.created_at), 2)
            job.error = str(e)
            job.current_phase = "Failed"
            self._persist_job(job)


# ============================================================================
# RECONSTRUCTION QUEUE MANAGER (STRICTLY SERIALIZED / MAX CONCURRENCY = 1)
# ============================================================================
class ReconstructionQueueManager:
    _instance: Optional["ReconstructionQueueManager"] = None
    _lock = threading.Lock()

    def __init__(self):
        # Strict MAX CONCURRENCY = 1 on RTX 4060 GPU
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="reconstruct_gpu_worker")
        self._queue: List[ReconstructionJob] = []  # Ordered queue
        self._jobs: Dict[str, ReconstructionJob] = {}  # job_id -> ReconstructionJob
        self._product_to_job: Dict[str, str] = {}  # product_id -> job_id
        self._queue_lock = threading.RLock()
        self._gpu_inference_lock = threading.Lock()
        self._active_job: Optional[ReconstructionJob] = None

    @classmethod
    def get_instance(cls) -> "ReconstructionQueueManager":
        with cls._lock:
            if cls._instance is None:
                cls._instance = ReconstructionQueueManager()
            return cls._instance

    def enqueue_reconstruction(
        self,
        product_id: str,
        reference_image: str,
        product_name: str,
        engine: str = "Pixal3D",
        product_metadata: Optional[Dict[str, Any]] = None
    ) -> ReconstructionJob:
        """
        Enqueues a 3D reconstruction request.
        Preserves the EXACT approved reference image across queuing.
        """
        if not reference_image or not str(reference_image).strip():
            logger.error(f"[RECONSTRUCT QUEUE] Rejected: Missing approved reference image for '{product_name}' ({product_id})")
            raise ValueError("Missing approved reference image for 3D reconstruction")

        if engine.strip().lower() not in ("pixal3d", "tencentarc/pixal3d"):
            logger.error(f"[RECONSTRUCT QUEUE] Rejected: Unsupported reconstruction engine '{engine}'")
            raise ValueError(f"Unsupported reconstruction engine: '{engine}'. Sole production engine is TencentARC/Pixal3D.")

        with self._queue_lock:
            # Check if an existing active reconstruction is queued/running for this product
            existing_job_id = self._product_to_job.get(product_id)
            if existing_job_id and existing_job_id in self._jobs:
                existing_job = self._jobs[existing_job_id]
                if existing_job.status in [ReconstructionStatus.QUEUED.value, ReconstructionStatus.RECONSTRUCTING.value]:
                    logger.info(f"[RECONSTRUCT QUEUE] Product {product_id} already has active job {existing_job.job_id} ({existing_job.status})")
                    return existing_job

            job_id = f"rec-job-{uuid.uuid4().hex[:8]}"
            job = ReconstructionJob(
                job_id=job_id,
                product_id=product_id,
                product_name=product_name,
                reference_image=reference_image,
                engine=engine,
                product_metadata=product_metadata
            )
            self._jobs[job_id] = job
            self._product_to_job[product_id] = job_id
            self._queue.append(job)

            logger.info(f"[RECONSTRUCT QUEUE] Enqueued {job_id} for '{product_name}' (Queue Depth: {len(self._queue)})")

            self._executor.submit(self._process_queue_item, job)
            return job

    def cancel_reconstruction(self, product_id_or_job_id: str) -> bool:
        """Safely cancels a queued reconstruction job."""
        with self._queue_lock:
            job = self.get_job_by_id_or_product(product_id_or_job_id)
            if not job:
                return False

            if job.status == ReconstructionStatus.QUEUED.value:
                job.status = ReconstructionStatus.CANCELLED.value
                job.cancellation_requested = True
                job.completed_at = time.time()
                if job in self._queue:
                    self._queue.remove(job)
                logger.info(f"[RECONSTRUCT QUEUE] Cancelled queued job {job.job_id}")
                return True

            elif job.status == ReconstructionStatus.RECONSTRUCTING.value:
                job.cancellation_requested = True
                logger.info(f"[RECONSTRUCT QUEUE] Flagged running inference job {job.job_id} for cancellation")
                return True

            return False

    def retry_reconstruction(self, product_id_or_job_id: str) -> ReconstructionJob:
        """
        Retries a 3D reconstruction request.
        Guarantees that a brand new job is enqueued and fresh neural inference executes.
        No previous reconstruction result can satisfy this request.
        """
        with self._queue_lock:
            old_job = self.get_job_by_id_or_product(product_id_or_job_id)
            if not old_job:
                raise ValueError(f"No existing reconstruction job found for '{product_id_or_job_id}'")

            # If old job is queued, remove it
            if old_job.status == ReconstructionStatus.QUEUED.value:
                old_job.status = ReconstructionStatus.CANCELLED.value
                old_job.cancellation_requested = True
                if old_job in self._queue:
                    self._queue.remove(old_job)

            # Generate fresh job with new UUID
            job_id = f"rec-job-{uuid.uuid4().hex[:8]}"
            new_job = ReconstructionJob(
                job_id=job_id,
                product_id=old_job.product_id,
                product_name=old_job.product_name,
                reference_image=old_job.reference_image,
                engine=old_job.engine,
                product_metadata=old_job.product_metadata
            )
            self._jobs[job_id] = new_job
            self._product_to_job[old_job.product_id] = job_id
            self._queue.append(new_job)

            logger.info(f"[RECONSTRUCT QUEUE] Enqueued RETRY {job_id} for '{old_job.product_name}' (Queue Depth: {len(self._queue)})")
            self._executor.submit(self._process_queue_item, new_job)
            return new_job

    def get_job_by_id_or_product(self, identifier: str) -> Optional[ReconstructionJob]:
        with self._queue_lock:
            if identifier in self._jobs:
                return self._jobs[identifier]
            job_id = self._product_to_job.get(identifier)
            if job_id and job_id in self._jobs:
                return self._jobs[job_id]
            return None

    def get_queue_status(self) -> Dict[str, Any]:
        with self._queue_lock:
            queued_jobs = [j.to_dict(queue_position=idx + 1) for idx, j in enumerate(self._queue) if j.status == ReconstructionStatus.QUEUED.value]
            active_job_dict = self._active_job.to_dict(queue_position=0) if self._active_job else None
            return {
                "active_job": active_job_dict,
                "is_gpu_busy": bool(self._active_job),
                "queued_count": len(queued_jobs),
                "queue": queued_jobs,
                "max_concurrency": 1
            }

    def get_job_status(self, identifier: str) -> Optional[Dict[str, Any]]:
        with self._queue_lock:
            job = self.get_job_by_id_or_product(identifier)
            if not job:
                return None

            pos = 0
            if job.status == ReconstructionStatus.QUEUED.value and job in self._queue:
                pos = self._queue.index(job) + 1

            return job.to_dict(queue_position=pos)

    def _process_queue_item(self, job: ReconstructionJob):
        """Single-threaded GPU queue processor."""
        # Acquire strict serialized GPU lock
        with self._gpu_inference_lock:
            with self._queue_lock:
                if job.cancellation_requested or job.status == ReconstructionStatus.CANCELLED.value:
                    if job in self._queue:
                        self._queue.remove(job)
                    return

                self._active_job = job
                job.status = ReconstructionStatus.RECONSTRUCTING.value
                job.started_at = time.time()
                if job in self._queue:
                    self._queue.remove(job)

            logger.info(f"[GPU SLOT ACQUIRED] Running Pixal3D reconstruction for '{job.product_name}' ({job.job_id})")

            try:
                service = ReconstructionService.get_instance()
                meta = {
                    "name": job.product_name,
                    "id": job.product_id,
                    **(job.product_metadata or {})
                }

                def progress_callback(phase: str, pct: float):
                    job.current_phase = phase
                    job.progress = pct
                    logger.info(f"[PIXAL3D PROGRESS {job.job_id}] {phase} ({int(pct*100)}%)")

                result = service.generate_3d_asset(
                    reference_image=job.reference_image,
                    product_metadata=meta,
                    engine=job.engine,
                    progress_callback=progress_callback
                )

                if result.get("success"):
                    job.current_phase = "Validating 3D Mesh Topology"
                    job.progress = 0.99
                    val_result = service.validate_mesh_asset(result["local_path"])
                    actual_gen_sec = result.get("generation_time_sec")
                    if actual_gen_sec is None and job.started_at:
                        actual_gen_sec = round(time.time() - job.started_at, 2)
                    actual_gen_ms = result.get("generation_time_ms")
                    if actual_gen_ms is None and actual_gen_sec is not None:
                        actual_gen_ms = int(actual_gen_sec * 1000)

                    job.result = {
                        "success": True,
                        "asset_id": result.get("asset_id", job.job_id),
                        "input_image": getattr(job, "reference_image", ""),
                        "model_url": result.get("model_url", ""),
                        "model_path": result.get("local_path", ""),
                        "local_path": result.get("local_path", ""),
                        "model_filename": result.get("model_filename", os.path.basename(result.get("local_path", "model.glb"))),
                        "format": result.get("format", "glb"),
                        "reconstruction_engine": result.get("reconstruction_engine", job.engine),
                        "generation_time_sec": actual_gen_sec,
                        "generation_time_ms": actual_gen_ms,
                        "call_count": result.get("call_count", 1),
                        "request_token": result.get("request_token", job.job_id),
                        "telemetry": result.get("telemetry", {}),
                        "mesh_telemetry": result.get("mesh_telemetry", result.get("mesh_stats", {})),
                        "mesh_stats": {
                            "vertex_count": result.get("mesh_telemetry", {}).get("vertices", result.get("mesh_stats", {}).get("vertices", 0)),
                            "face_count": result.get("mesh_telemetry", {}).get("triangles", result.get("mesh_stats", {}).get("faces", 0)),
                            "watertight": result.get("mesh_telemetry", {}).get("is_watertight", True),
                            "euler_characteristic": result.get("mesh_telemetry", {}).get("euler_characteristic", 2)
                        },
                        "validation": val_result,
                        "status": "MODEL_READY" if val_result.get("valid", True) else "VALIDATION_WARNING"
                    }
                    job.status = ReconstructionStatus.COMPLETED.value
                    job.completed_at = time.time()
                    job.current_phase = "Complete"
                    job.progress = 1.0
                    job.generation_time_sec = result.get("generation_time_sec", round(job.completed_at - job.started_at, 2))
                    logger.info(f"[GPU RECONSTRUCTION COMPLETE] Job {job.job_id} generated in {job.generation_time_sec}s")
                else:
                    job.status = ReconstructionStatus.FAILED.value
                    job.completed_at = time.time()
                    job.current_phase = "Failed"
                    job.error = result.get("error", "Reconstruction failed")
                    logger.error(f"[GPU RECONSTRUCTION FAILED] Job {job.job_id}: {job.error}")

            except Exception as e:
                logger.error(f"[GPU RECONSTRUCTION EXCEPTION] Job {job.job_id}: {e}", exc_info=True)
                job.status = ReconstructionStatus.FAILED.value
                job.completed_at = time.time()
                job.current_phase = "Failed"
                job.error = str(e)
            finally:
                with self._queue_lock:
                    self._active_job = None
                try:
                    import gc
                    import torch
                    gc.collect()
                    if torch.cuda.is_available():
                        torch.cuda.empty_cache()
                except Exception:
                    pass
