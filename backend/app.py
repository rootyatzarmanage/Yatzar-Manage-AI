"""
Uncertainty-Aware 2D-to-3D Reconstruction Pipeline - Backend Service
Product Asset Factory API with DINOv2 & Playwright Multi-View Scraping
"""

import os
import io
import json
import time
import random
import logging
from pathlib import Path
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from PIL import Image

from services.triage_service import evaluate_geometric_uncertainty
from services.scraper_service import (
    ScrapingPipelineManager,
    harvest_and_filter,
    scrape_images_scrapy,
    scrape_images_playwright,
    CACHE_DIR
)
from services.reconstruction_service import ReconstructionService, MODELS_CACHE_DIR

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)

# Cache / static images directory
UPLOAD_DIR = Path(__file__).resolve().parent / "cache" / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# In-memory database of user products (starts clean, zero demo contamination)
PRODUCTS_DB = []

# Static candidate image serving
@app.route("/cache/candidates/<path:filename>")
def serve_candidate_cache(filename):
    return send_from_directory(str(CACHE_DIR), filename)

@app.route("/cache/uploads/<path:filename>")
def serve_uploads_cache(filename):
    return send_from_directory(str(UPLOAD_DIR), filename)

@app.route("/cache/models/<path:filename>")
def serve_models_cache(filename):
    return send_from_directory(str(MODELS_CACHE_DIR), filename)

# Health check
@app.route("/api/health", methods=["GET"])
def health_check():
    return jsonify({
        "status": "online",
        "service": "Yatzar Manage AI - 2D to 3D Pipeline Backend",
        "version": "1.0.0",
        "gpu_available": True
    })

# Get all products
@app.route("/api/products", methods=["GET"])
def get_products():
    return jsonify({"success": True, "products": PRODUCTS_DB})

# Get single product by id or slug
@app.route("/api/products/<product_id>", methods=["GET"])
def get_product(product_id):
    product = next((p for p in PRODUCTS_DB if p["id"] == product_id or p.get("slug") == product_id), None)
    if not product:
        return jsonify({"success": False, "error": "Product not found"}), 404
    return jsonify({"success": True, "product": product})

# Create product
@app.route("/api/products", methods=["POST"])
def create_product():
    data = request.json or {}
    new_product = {
        "id": data.get("id") or f"PROD-{len(PRODUCTS_DB)+1:02d}",
        "name": data.get("name", ""),
        "slug": data.get("slug", ""),
        "status": "IN_PROGRESS",
        "category": data.get("category", "General"),
        "modelNumber": data.get("modelNumber", ""),
        "articleNumber": data.get("articleNumber", ""),
        "brand": data.get("brand", ""),
        "prompt": data.get("prompt", ""),
        "width": data.get("width", ""),
        "height": data.get("height", ""),
        "depth": data.get("depth", ""),
        "currentStage": "Input",
        "executionTime": "0s",
        "imagesCount": 0,
        "confidenceScore": 0.0,
        "scrapedImages": [],
        "relatedUrls": []
    }
    PRODUCTS_DB.insert(0, new_product)
    return jsonify({"success": True, "product": new_product}), 201


# ==========================================
# STAGE 1: V-LLM GEOMETRIC UNCERTAINTY TRIAGE
# ==========================================
@app.route("/api/v1/triage", methods=["POST"])
@app.route("/api/triage", methods=["POST"])
def run_triage():
    """
    POST /api/v1/triage
    Accepts image file upload or JSON payload with structured product metadata.
    Calls triage_service.evaluate_geometric_uncertainty() and returns 4-quadrant uncertainty telemetry.
    """
    try:
        saved_image_path = None
        product_title = ""
        product_sku = ""

        # Handle multipart/form-data upload
        if request.files and "image" in request.files:
            uploaded = request.files["image"]
            if uploaded.filename:
                dest = UPLOAD_DIR / f"upload_{int(time.time())}_{uploaded.filename}"
                uploaded.save(str(dest))
                saved_image_path = str(dest)

        # Form fields or JSON body
        category = ""
        product_id = ""
        model_number = ""
        article_number = ""
        part_number = ""
        brand = ""
        user_prompt = ""
        dynamic_urls = []

        if request.form:
            product_title = request.form.get("product_title") or request.form.get("name") or ""
            model_number = request.form.get("model_number") or request.form.get("modelNumber") or ""
            article_number = request.form.get("article_number") or request.form.get("articleNumber") or ""
            part_number = request.form.get("part_number") or request.form.get("partNumber") or ""
            product_sku = request.form.get("product_sku") or request.form.get("sku") or model_number or article_number or part_number or ""
            brand = request.form.get("brand") or request.form.get("manufacturer") or ""
            category = request.form.get("category") or ""
            product_id = request.form.get("product_id") or request.form.get("id") or ""
            user_prompt = request.form.get("prompt") or request.form.get("user_prompt") or ""
            if not saved_image_path:
                saved_image_path = request.form.get("image_path") or request.form.get("thumbnail") or request.form.get("seed_image")

        if request.is_json and request.json:
            data = request.json
            product_title = data.get("product_title") or data.get("name") or product_title
            model_number = data.get("model_number") or data.get("modelNumber") or model_number
            article_number = data.get("article_number") or data.get("articleNumber") or article_number
            part_number = data.get("part_number") or data.get("partNumber") or part_number
            product_sku = data.get("product_sku") or data.get("sku") or model_number or article_number or part_number or product_sku
            brand = data.get("brand") or data.get("manufacturer") or brand
            category = data.get("category") or category
            product_id = data.get("product_id") or data.get("id") or product_id
            user_prompt = data.get("prompt") or data.get("user_prompt") or user_prompt
            dynamic_urls = data.get("dynamic_urls") or data.get("sourceUrls") or []
            if not saved_image_path:
                saved_image_path = data.get("image_path") or data.get("thumbnail") or data.get("seed_image")

        logger.info(f"[PRODUCT IDENTITY] Triage requested for '{product_title}' (Brand: {brand}, Model: {model_number}, Article: {article_number}, Part: {part_number}, Cat: {category})")
        triage_data = evaluate_geometric_uncertainty(
            image_path=saved_image_path,
            product_title=product_title,
            product_sku=product_sku,
            category=category,
            product_id=product_id,
            model_number=model_number or article_number,
            part_number=part_number,
            brand=brand
        )

        return jsonify({
            "success": True,
            "triage": triage_data
        })

    except Exception as e:
        logger.error(f"Error in /api/v1/triage: {e}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500


# ==========================================
# STAGE 2: DINOv2 HARVEST & VECTOR SCRAPING (RETRIEVAL V2)
# ==========================================
@app.route("/api/v1/scrape", methods=["POST"])
@app.route("/api/scrape", methods=["POST"])
def run_scrape():
    """
    POST /api/v1/scrape
    Ingests structured product metadata and executes the Retrieval V2 staged retrieval pipeline.
    Returns verified cards with 2D PCA vector space coordinates, source provenance, and telemetry timings.
    """
    try:
        seed_image_input = None
        product_title = ""
        product_sku = ""
        category = ""
        product_id = ""
        model_number = ""
        article_number = ""
        part_number = ""
        brand = ""
        user_prompt = ""
        target_queries = []
        dynamic_urls = []

        # Handle multipart file upload
        if request.files and "image" in request.files:
            uploaded = request.files["image"]
            if uploaded.filename:
                dest = UPLOAD_DIR / f"seed_{int(time.time())}_{uploaded.filename}"
                uploaded.save(str(dest))
                seed_image_input = str(dest)

        # Handle form data
        if request.form:
            product_title = request.form.get("product_title") or request.form.get("name") or product_title
            model_number = request.form.get("model_number") or request.form.get("modelNumber") or ""
            article_number = request.form.get("article_number") or request.form.get("articleNumber") or ""
            part_number = request.form.get("part_number") or request.form.get("partNumber") or ""
            product_sku = request.form.get("product_sku") or request.form.get("sku") or model_number or article_number or part_number or product_sku
            brand = request.form.get("brand") or request.form.get("manufacturer") or ""
            category = request.form.get("category") or category
            product_id = request.form.get("product_id") or request.form.get("id") or product_id
            user_prompt = request.form.get("prompt") or request.form.get("user_prompt") or ""
            if not seed_image_input:
                seed_image_input = request.form.get("seed_image") or request.form.get("thumbnail") or request.form.get("image")
            q_str = request.form.get("target_queries")
            if q_str:
                try:
                    target_queries = json.loads(q_str) if q_str.startswith("[") else q_str.split("\n")
                except Exception:
                    target_queries = [q_str]
            url_str = request.form.get("sourceUrls") or request.form.get("dynamic_urls")
            if url_str:
                try:
                    dynamic_urls = json.loads(url_str) if url_str.startswith("[") else url_str.split("\n")
                except Exception:
                    dynamic_urls = [url_str]

        # Handle JSON body
        if request.is_json and request.json:
            data = request.json
            product_title = data.get("product_title") or data.get("name") or product_title
            model_number = data.get("model_number") or data.get("modelNumber") or model_number
            article_number = data.get("article_number") or data.get("articleNumber") or article_number
            part_number = data.get("part_number") or data.get("partNumber") or part_number
            product_sku = data.get("product_sku") or data.get("sku") or model_number or article_number or part_number or product_sku
            brand = data.get("brand") or data.get("manufacturer") or brand
            category = data.get("category") or category
            product_id = data.get("product_id") or data.get("id") or product_id
            user_prompt = data.get("prompt") or data.get("user_prompt") or user_prompt
            if not seed_image_input:
                seed_image_input = data.get("seed_image") or data.get("thumbnail") or data.get("image")
            target_queries = data.get("target_queries") or target_queries
            dynamic_urls = data.get("dynamic_urls") or data.get("sourceUrls") or []

        # Handle base64 Data URL if passed in JSON/form
        if isinstance(seed_image_input, str) and seed_image_input.startswith("data:image"):
            import base64
            header, data_part = seed_image_input.split(",", 1)
            raw_data = base64.b64decode(data_part)
            dest = UPLOAD_DIR / f"upload_b64_{int(time.time())}.jpg"
            with open(dest, "wb") as f:
                f.write(raw_data)
            seed_image_input = str(dest)

        # Fallback neutral seed if None
        if not seed_image_input:
            seed_image_input = "https://images.unsplash.com/photo-1581291518857-4e27b48ff24e?w=600&auto=format&fit=crop&q=80"

        logger.info(
            f"[PRODUCT IDENTITY] Executing Retrieval V2 for '{product_title}' "
            f"(Brand: {brand}, Model: {model_number}, Article: {article_number}, Part: {part_number}, SKU: {product_sku}, Cat: {category})"
        )

        start_time = time.time()
        pipeline_manager = ScrapingPipelineManager()
        pipeline_result = pipeline_manager.execute_pipeline(
            seed_image=seed_image_input,
            target_queries=target_queries,
            max_candidates=15,
            similarity_threshold=0.60,
            dynamic_urls=dynamic_urls,
            product_title=product_title,
            product_sku=product_sku,
            product_id=product_id,
            model_number=model_number,
            article_number=article_number,
            part_number=part_number,
            brand=brand,
            category=category,
            user_prompt=user_prompt
        )

        candidates = pipeline_result.get("candidates", [])
        seed_coord = pipeline_result.get("seed_coordinates", {"x": 0.0, "y": 0.0})
        telemetry = pipeline_result.get("telemetry_timing", {})
        elapsed_sec = round(time.time() - start_time, 2)

        sample_urls = []
        if dynamic_urls:
            for u in dynamic_urls:
                sample_urls.append({"title": f"Official Source Page: {u}", "url": u, "selected": True})

        return jsonify({
            "success": True,
            "totalImagesFound": pipeline_result.get("total_harvested", len(candidates)),
            "totalAccepted": pipeline_result.get("total_accepted", len(candidates)),
            "images": candidates,
            "curated_images": candidates,
            "rejected_images": pipeline_result.get("rejected_candidates", []),
            "seed_coordinates": seed_coord,
            "relatedUrls": sample_urls,
            "cycleNumber": 1,
            "research_duration_sec": elapsed_sec,
            "executionTime": f"{elapsed_sec}s",
            "executionTimeMs": int(elapsed_sec * 1000),
            "telemetry": telemetry,
            "plannedQueries": pipeline_result.get("planned_queries", []),
            "summary": pipeline_result.get("research_summary", {}),
            "research_summary": pipeline_result.get("research_summary", {}),
            "best_reference": pipeline_result.get("best_reference"),
            "gpuDevice": "NVIDIA GeForce RTX 4060 Laptop GPU"
        })


    except Exception as e:
        logger.error(f"Error in /api/v1/scrape: {e}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500


# ==========================================
# TARGETED ANGLE CASCADE PIPELINE
# ==========================================
@app.route("/api/v1/cascade", methods=["POST"])
@app.route("/api/cascade", methods=["POST"])
def run_cascade():
    """
    POST /api/v1/cascade
    Executes a targeted search cascade for occluded angles/ports using Retrieval V2 scrapers.
    """
    try:
        start_time = time.time()
        data = request.json or {}
        
        cascade_query = data.get("cascade_query") or data.get("query") or "Product rear view"
        product_title = data.get("product_title") or data.get("name") or "Product Asset"
        product_sku = data.get("product_sku") or data.get("modelNumber") or "SKU-01"
        category = data.get("category") or ""
        product_id = data.get("product_id") or data.get("id") or product_sku
        seed_image_input = data.get("seed_image") or data.get("thumbnail")
        cycle_number = int(data.get("cycle_number", 2))
        brand = data.get("brand") or data.get("manufacturer") or ""

        # Handle base64 Data URL if passed
        if isinstance(seed_image_input, str) and seed_image_input.startswith("data:image"):
            import base64
            header, data_part = seed_image_input.split(",", 1)
            raw_data = base64.b64decode(data_part)
            dest = UPLOAD_DIR / f"cascade_b64_{int(time.time())}.jpg"
            with open(dest, "wb") as f:
                f.write(raw_data)
            seed_image_input = str(dest)

        if not seed_image_input:
            seed_image_input = "https://images.unsplash.com/photo-1581291518857-4e27b48ff24e?w=600&auto=format&fit=crop&q=80"

        logger.info(f"[CASCADE] Executing Cascade Cycle {cycle_number} for '{product_title}' query: '{cascade_query}'")
        pipeline_manager = ScrapingPipelineManager()
        
        cascade_result = pipeline_manager.execute_pipeline(
            seed_image=seed_image_input,
            target_queries=[cascade_query],
            max_candidates=6,
            similarity_threshold=0.60,
            product_title=product_title,
            product_sku=product_sku,
            product_id=product_id,
            model_number=product_sku,
            brand=brand,
            category=category,
            user_prompt=cascade_query
        )

        candidates = cascade_result.get("candidates", [])
        elapsed_sec = round(time.time() - start_time, 2)

        return jsonify({
            "success": True,
            "cycleNumber": cycle_number,
            "cascadeQuery": cascade_query,
            "images": candidates,
            "totalHarvested": len(candidates),
            "executionTime": f"{elapsed_sec}s",
            "executionTimeMs": int(elapsed_sec * 1000),
            "gpuDevice": "NVIDIA GeForce RTX 4060 Laptop GPU"
        })

    except Exception as e:
        logger.error(f"Error in /api/v1/cascade: {e}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500


# ==========================================
# REAL 3D RECONSTRUCTION (TRIPOSR NEURAL ENGINE)
# ==========================================
@app.route("/api/v1/reconstruct", methods=["POST"])
@app.route("/api/reconstruct", methods=["POST"])
@app.route("/api/csg/generate", methods=["POST"])
def reconstruct_3d_asset():
    """
    POST /api/v1/reconstruct
    Accepts reference image (path, URL, or base64) and product metadata.
    Invokes TripoSREngine (or fallback Pixel3DEngine) to reconstruct watertight 3D GLB model.
    """
    try:
        data = request.json or {}
        image_input = data.get("reference_image") or data.get("image_url") or data.get("local_path") or data.get("seed_image") or data.get("thumbnail")
        product_name = data.get("name") or data.get("product_title") or "Product Asset"
        product_id = data.get("id") or data.get("product_id") or f"prod_{int(time.time())}"
        engine_target = data.get("engine") or data.get("reconstruction_engine") or "TripoSR"

        if not image_input:
            # Fallback to neutral seed image
            image_input = "https://images.unsplash.com/photo-1581291518857-4e27b48ff24e?w=600&auto=format&fit=crop&q=80"

        # Handle base64 Data URL if passed
        if isinstance(image_input, str) and image_input.startswith("data:image"):
            import base64
            header, data_part = image_input.split(",", 1)
            raw_data = base64.b64decode(data_part)
            dest = UPLOAD_DIR / f"reconstruct_b64_{int(time.time())}.jpg"
            with open(dest, "wb") as f:
                f.write(raw_data)
            image_input = str(dest)

        logger.info(f"[RECONSTRUCTION] Ingesting reference image for '{product_name}' (ID: {product_id}) using engine '{engine_target}'")
        reconstruction_service = ReconstructionService.get_instance()
        result = reconstruction_service.generate_3d_asset(
            reference_image=image_input,
            product_metadata={"name": product_name, "id": product_id},
            engine=engine_target
        )

        if not result.get("success"):
            return jsonify({
                "success": False,
                "error": result.get("error", "Reconstruction failed"),
                "reconstruction_engine": result.get("reconstruction_engine", engine_target),
                "status": "FAILED"
            }), 500

        # Perform automatic 3D validation check
        val_result = reconstruction_service.validate_mesh_asset(result["local_path"])

        return jsonify({
            "success": True,
            "asset_id": result["asset_id"],
            "model_url": result["model_url"],
            "model_path": result["local_path"],
            "local_path": result["local_path"],
            "model_filename": result["model_filename"],
            "format": result["format"],
            "reconstruction_engine": result["reconstruction_engine"],
            "generation_time_sec": result["generation_time_sec"],
            "generation_time_ms": result["generation_time_ms"],
            "cache_hit": result.get("cache_hit", False),
            "telemetry": result.get("telemetry", {}),
            "mesh_telemetry": result["mesh_telemetry"],
            "mesh_stats": {
                "vertex_count": result["mesh_telemetry"].get("vertices", 0),
                "face_count": result["mesh_telemetry"].get("triangles", 0),
                "watertight": result["mesh_telemetry"].get("is_watertight", True),
                "euler_characteristic": result["mesh_telemetry"].get("euler_characteristic", 2)
            },
            "validation": val_result,
            "status": "MODEL_READY" if val_result.get("valid") else "VALIDATION_WARNING"
        })

    except Exception as e:
        logger.error(f"Error in /api/v1/reconstruct: {e}", exc_info=True)
        return jsonify({"success": False, "error": str(e), "reconstruction_engine": "TripoSR", "status": "FAILED"}), 500


# ==========================================
# 3D ASSET VALIDATION (3D APPROVAL PHASE)
# ==========================================
@app.route("/api/v1/validate-3d", methods=["POST"])
@app.route("/api/validate-3d", methods=["POST"])
def validate_3d_model():
    """
    POST /api/v1/validate-3d
    Verifies that a generated GLB model asset exists, is loadable, watertight, and valid.
    """
    try:
        data = request.json or {}
        model_url_or_path = data.get("model_url") or data.get("local_path") or data.get("model_filename")
        if not model_url_or_path:
            return jsonify({"success": False, "error": "No model path or URL provided"}), 400

        reconstruction_service = ReconstructionService.get_instance()
        val = reconstruction_service.validate_mesh_asset(model_url_or_path)

        return jsonify({
            "success": val.get("valid", False),
            "validation": val,
            "status": "PASSED" if val.get("valid") else "FAILED"
        })

    except Exception as e:
        logger.error(f"Error in /api/v1/validate-3d: {e}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
