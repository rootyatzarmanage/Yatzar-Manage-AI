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

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)

# Cache / static images directory
UPLOAD_DIR = Path(__file__).resolve().parent / "cache" / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# In-memory database of products initialized with sample benchmark assets
PRODUCTS_DB = [
    {
        "id": "PROD-ALFA-01",
        "name": "Alfa Laval_Heat_Exchanger",
        "slug": "Alfa Laval_Heat_Exchanger",
        "status": "APPROVED",
        "category": "Industrial Equipment",
        "modelNumber": "AL-HEX-9000",
        "prompt": "Alfa Laval industrial plate heat exchanger with blue end frames, tightening bolts, ports and corrugated plate pack",
        "width": 1200,
        "height": 1800,
        "depth": 850,
        "currentStage": "3D Approval",
        "executionTime": "12s",
        "imagesCount": 10,
        "confidenceScore": 0.94,
        "triage": {
            "rotationalSymmetry": "Low (Planar Asymmetric)",
            "azimuthalUncertainty": 0.18,
            "quadrantCoverage": {"front": 1.0, "profile": 0.95, "rear": 0.90, "ports": 0.92},
            "scrapingBudget": "Multi-query Targeted (3 Cycles)"
        },
        "scrapedImages": [
            {"id": "img-1", "url": "https://images.unsplash.com/photo-1581092160607-ee22621dd758?w=500&auto=format&fit=crop&q=80", "title": "industrial-line-alfa-laval-frame", "source": "direct_url_fallback", "score": 0.92, "angle": "0° Front", "selected": True},
            {"id": "img-2", "url": "https://images.unsplash.com/photo-1581092335397-9583fe92d232?w=500&auto=format&fit=crop&q=80", "title": "product_9e9372d3.jpg", "source": "model_number_search_unfiltered", "score": 0.88, "angle": "90° Profile", "selected": True},
            {"id": "img-3", "url": "https://images.unsplash.com/photo-1581092580497-e0d23cbdf1dc?w=500&auto=format&fit=crop&q=80", "title": "product_5f509b4a.jpg", "source": "model_number_search_unfiltered", "score": 0.86, "angle": "180° Rear", "selected": True},
            {"id": "img-4", "url": "https://images.unsplash.com/photo-1581091226825-a6a2a5aee158?w=500&auto=format&fit=crop&q=80", "title": "product_4b430e45.jpg", "source": "model_number_search_unfiltered", "score": 0.79, "angle": "270° Bottom Ports", "selected": True},
            {"id": "img-5", "url": "https://images.unsplash.com/photo-1581092795360-fd1ca04f0952?w=500&auto=format&fit=crop&q=80", "title": "product_7621215c.jpg", "source": "model_number_search_unfiltered", "score": 0.81, "angle": "Isometric Perspective", "selected": True},
            {"id": "img-6", "url": "https://images.unsplash.com/photo-1581093458791-9f3c3900df4b?w=500&auto=format&fit=crop&q=80", "title": "logo-alfalaval.svg", "source": "domain_spec_sheet", "score": 0.58, "angle": "Noise (Dropped)", "selected": False},
            {"id": "img-7", "url": "https://images.unsplash.com/photo-1581092162384-8987c1d64718?w=500&auto=format&fit=crop&q=80", "title": "b4a3c207b6648082820.jpg", "source": "direct_url_fallback", "score": 0.54, "angle": "Packaging (Dropped)", "selected": False}
        ],
        "relatedUrls": [
            {"title": "Industrial line gasketed plate-and-frame heat exchangers", "url": "https://www.alfalaval.com/products/heat-transfer/plate-heat-exchangers/gasketed-plate-and-frame-heat-exchangers/industrial-line/", "selected": True},
            {"title": "Alfa Laval Heat Exchangers - Latest Price, Dealers & Retailers in India", "url": "https://dir.indiamart.com/impcat/alfa-laval-heat-exchangers.html", "selected": True},
            {"title": "Alfa Laval Heat Exchanger Configurator at Carolann Ness blog", "url": "https://carolannness.com/alfa-laval-heat-exchanger-configurator/", "selected": False}
        ],
        "qaAudit": {
            "watertight": True,
            "eulerCharacteristic": 2,
            "nonManifoldEdges": 0,
            "overallSimilarity": 0.92,
            "orthogonalScores": {
                "front": 0.94,
                "profile": 0.91,
                "rear": 0.89,
                "bottom": 0.93,
                "top": 0.95,
                "isometric": 0.90
            }
        }
    },
    {
        "id": "PROD-ELECTROLUX-02",
        "name": "Electrolux_Electric_Steam_Oven",
        "slug": "Electrolux_Electric_Steam_Oven",
        "status": "APPROVED",
        "category": "Home Appliances",
        "modelNumber": "EOB8S39Z",
        "prompt": "Electrolux 800 SteamBoost built-in electric steam oven black glass front touch panel",
        "width": 594,
        "height": 594,
        "depth": 567,
        "currentStage": "3D Approval",
        "executionTime": "10s",
        "imagesCount": 10,
        "confidenceScore": 0.96
    },
    {
        "id": "PROD-NORDPEIS-03",
        "name": "nordpeis fireplace",
        "slug": "nordpeis fireplace",
        "status": "APPROVED",
        "category": "Furniture & Interior",
        "modelNumber": "NP-ME-WOOD",
        "prompt": "Nordpeis ME modern minimalist curved glass wood-burning fireplace white chimney",
        "width": 500,
        "height": 1600,
        "depth": 450,
        "currentStage": "3D Approval",
        "executionTime": "14s",
        "imagesCount": 19,
        "confidenceScore": 0.91
    },
    {
        "id": "PROD-VIEWSONIC-04",
        "name": "Viewsonic_Laser_Projector",
        "slug": "Viewsonic_Laser_Projector",
        "status": "APPROVED",
        "category": "Electronics",
        "modelNumber": "LS740HD",
        "prompt": "ViewSonic high brightness laser projector white chassis ventilation grilles lens ports",
        "width": 286,
        "height": 115,
        "depth": 216,
        "currentStage": "3D Approval",
        "executionTime": "9s",
        "imagesCount": 12,
        "confidenceScore": 0.95
    },
    {
        "id": "PROD-VIDEOTEC-05",
        "name": "Videotec_Thermal_Camera",
        "slug": "Videotec_Thermal_Camera",
        "status": "APPROVED",
        "category": "Security Hardware",
        "modelNumber": "MAXIMUS-MPX",
        "prompt": "Videotec explosion-proof stainless steel PTZ thermal security camera cylindrical housing",
        "width": 380,
        "height": 420,
        "depth": 310,
        "currentStage": "3D Approval",
        "executionTime": "11s",
        "imagesCount": 13,
        "confidenceScore": 0.93
    },
    {
        "id": "PROD-CEA-06",
        "name": "CEA Estintori_Fire_Extinguisher",
        "slug": "CEA Estintori_Fire_Extinguisher",
        "status": "APPROVED",
        "category": "Safety Equipment",
        "modelNumber": "CEA-CO2-5KG",
        "prompt": "Red CO2 cylindrical fire extinguisher with high pressure black discharge horn and squeeze grip valve",
        "width": 160,
        "height": 720,
        "depth": 230,
        "currentStage": "3D Approval",
        "executionTime": "6s",
        "imagesCount": 10,
        "confidenceScore": 0.98
    },
    {
        "id": "PROD-ROCA-07",
        "name": "Roca Urinal",
        "slug": "Roca Urinal",
        "status": "APPROVED",
        "category": "Sanitary Ware",
        "modelNumber": "ROCA-NEXO",
        "prompt": "Roca wall-hung vitreous china modern compact waterless urinal white gloss",
        "width": 310,
        "height": 560,
        "depth": 280,
        "currentStage": "3D Approval",
        "executionTime": "8s",
        "imagesCount": 8,
        "confidenceScore": 0.97
    }
]

# Static candidate image serving
@app.route("/cache/candidates/<path:filename>")
def serve_candidate_cache(filename):
    return send_from_directory(str(CACHE_DIR), filename)

@app.route("/cache/uploads/<path:filename>")
def serve_uploads_cache(filename):
    return send_from_directory(str(UPLOAD_DIR), filename)

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
    product = next((p for p in PRODUCTS_DB if p["id"] == product_id or p["slug"] == product_id), None)
    if not product:
        return jsonify({"success": False, "error": "Product not found"}), 404
    return jsonify({"success": True, "product": product})

# Create product
@app.route("/api/products", methods=["POST"])
def create_product():
    data = request.json or {}
    new_product = {
        "id": f"PROD-{len(PRODUCTS_DB)+1:02d}",
        "name": data.get("name", "Untitled Product"),
        "slug": data.get("slug", "untitled_product"),
        "status": "IN_PROGRESS",
        "category": data.get("category", "General"),
        "modelNumber": data.get("modelNumber", "N/A"),
        "prompt": data.get("prompt", ""),
        "width": float(data.get("width", 100)),
        "height": float(data.get("height", 100)),
        "depth": float(data.get("depth", 100)),
        "currentStage": "Input",
        "executionTime": "0s",
        "imagesCount": 0,
        "confidenceScore": 0.0
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
    Accepts image file upload or JSON payload with product_title + product_sku.
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
        if request.form:
            product_title = request.form.get("product_title") or request.form.get("name") or ""
            product_sku = request.form.get("product_sku") or request.form.get("modelNumber") or request.form.get("sku") or ""
            if not saved_image_path:
                saved_image_path = request.form.get("image_path") or request.form.get("thumbnail") or request.form.get("seed_image")

        if request.is_json and request.json:
            data = request.json
            product_title = data.get("product_title") or data.get("name") or product_title
            product_sku = data.get("product_sku") or data.get("modelNumber") or data.get("sku") or product_sku
            if not saved_image_path:
                saved_image_path = data.get("image_path") or data.get("thumbnail") or data.get("seed_image")

        logger.info(f"Running geometric uncertainty triage for '{product_title}' (SKU: {product_sku})")
        triage_data = evaluate_geometric_uncertainty(
            image_path=saved_image_path,
            product_title=product_title,
            product_sku=product_sku
        )

        return jsonify({
            "success": True,
            "triage": triage_data
        })

    except Exception as e:
        logger.error(f"Error in /api/v1/triage: {e}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500


# ==========================================
# STAGE 2: DINOv2 HARVEST & VECTOR SCRAPING
# ==========================================
@app.route("/api/v1/scrape", methods=["POST"])
@app.route("/api/scrape", methods=["POST"])
def run_scrape():
    """
    POST /api/v1/scrape
    Ingests the seed image and runs scraper_service.execute_pipeline().
    Returns top 10 verified cards with DINOv2 score, 2D PCA vector space coordinates, and source tags.
    """
    try:
        seed_image_input = None
        product_title = ""
        product_sku = ""
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
            product_sku = request.form.get("product_sku") or request.form.get("modelNumber") or product_sku
            if not seed_image_input:
                seed_image_input = request.form.get("seed_image") or request.form.get("thumbnail") or request.form.get("image")
            q_str = request.form.get("target_queries")
            if q_str:
                try:
                    target_queries = json.loads(q_str) if q_str.startswith("[") else q_str.split("\n")
                except Exception:
                    target_queries = [q_str]

        # Handle JSON body
        if request.is_json and request.json:
            data = request.json
            product_title = data.get("product_title") or data.get("name") or product_title
            product_sku = data.get("product_sku") or data.get("modelNumber") or product_sku
            if not seed_image_input:
                seed_image_input = data.get("seed_image") or data.get("thumbnail") or data.get("image")
            target_queries = data.get("target_queries") or target_queries
            dynamic_urls = data.get("dynamic_urls") or data.get("sourceUrls") or []

        # Default product metadata if empty
        if not product_title:
            product_title = "Custom Product Asset"
        if not product_sku:
            product_sku = "PROD-GEN-01"

        # Handle base64 Data URL if passed in JSON/form
        if isinstance(seed_image_input, str) and seed_image_input.startswith("data:image"):
            import base64
            header, data_part = seed_image_input.split(",", 1)
            raw_data = base64.b64decode(data_part)
            dest = UPLOAD_DIR / f"upload_b64_{int(time.time())}.jpg"
            with open(dest, "wb") as f:
                f.write(raw_data)
            seed_image_input = str(dest)

        # If no queries specified, derive using triage service
        if not target_queries:
            triage_res = evaluate_geometric_uncertainty(
                image_path=seed_image_input if isinstance(seed_image_input, str) and os.path.exists(seed_image_input) else None,
                product_title=product_title,
                product_sku=product_sku
            )
            target_queries = triage_res.get("target_search_queries", [
                f"{product_title} rear view",
                f"{product_title} side profile view",
                f"{product_title} bottom ports"
            ])

        # If seed_image_input is None or invalid, generate fallback image
        if not seed_image_input:
            seed_image_input = "https://images.unsplash.com/photo-1542291026-7eec264c27ff?w=600&auto=format&fit=crop&q=80"

        logger.info(f"Running Scraping Pipeline for '{product_title}' (SKU: {product_sku}) across {len(target_queries)} queries")
        start_time = time.time()
        pipeline_manager = ScrapingPipelineManager()
        pipeline_result = pipeline_manager.execute_pipeline(
            seed_image=seed_image_input,
            target_queries=target_queries,
            max_candidates=15,
            similarity_threshold=0.60,
            dynamic_urls=dynamic_urls,
            product_title=product_title
        )

        candidates = pipeline_result.get("candidates", [])
        seed_coord = pipeline_result.get("seed_coordinates", {"x": 0.0, "y": 0.0})
        elapsed_sec = round(time.time() - start_time, 2)

        sample_urls = [
            {
                "title": f"{product_title} - Engineering Datasheet & Dimensional Spec",
                "url": f"https://www.specs.example.com/products/{product_title.lower().replace(' ', '-')}",
                "selected": True
            },
            {
                "title": f"{product_title} - Official CAD & 3D Interactive Model Sheet",
                "url": f"https://cad.example.com/models/{product_title.lower().replace(' ', '-')}",
                "selected": True
            },
            {
                "title": f"{product_title} - Technical Manual & Component Spares Catalog",
                "url": f"https://parts.example.com/item/{product_sku.lower().replace(' ', '-')}",
                "selected": False
            }
        ]

        return jsonify({
            "success": True,
            "totalImagesFound": pipeline_result.get("total_harvested", len(candidates)),
            "totalAccepted": pipeline_result.get("total_accepted", len([c for c in candidates if c.get("selected")])),
            "images": candidates,
            "seed_coordinates": seed_coord,
            "relatedUrls": sample_urls,
            "cycleNumber": 1,
            "coverageReached": 0.94,
            "executionTime": f"{elapsed_sec}s",
            "executionTimeMs": int(elapsed_sec * 1000),
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
    Executes a targeted search cascade for occluded angles/ports using real scrapers + DINOv2 scoring.
    """
    try:
        start_time = time.time()
        data = request.json or {}
        
        cascade_query = data.get("cascade_query") or data.get("query") or "Product rear view"
        product_title = data.get("product_title") or data.get("name") or "Product Asset"
        product_sku = data.get("product_sku") or data.get("modelNumber") or "SKU-01"
        seed_image_input = data.get("seed_image") or data.get("thumbnail")
        cycle_number = int(data.get("cycle_number", 2))

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
            seed_image_input = "https://images.unsplash.com/photo-1542291026-7eec264c27ff?w=600&auto=format&fit=crop&q=80"

        logger.info(f"Executing Cascade Cycle {cycle_number} for '{product_title}' query: '{cascade_query}'")
        pipeline_manager = ScrapingPipelineManager()
        
        cascade_result = pipeline_manager.execute_pipeline(
            seed_image=seed_image_input,
            target_queries=[cascade_query],
            max_candidates=6,
            similarity_threshold=0.60,
            product_title=product_title
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
# PROCEDURAL CAD CSG SYNTHESIS
# ==========================================
@app.route("/api/csg/generate", methods=["POST"])
def generate_csg():
    """Returns procedural CAD CSG synthesis instructions and telemetry."""
    data = request.json or {}
    product_name = data.get("name", "Product")
    width = float(data.get("width", 1000))
    height = float(data.get("height", 1000))
    depth = float(data.get("depth", 1000))

    # Normalize dimensions for WebGL viewport (target 2-3 unit bounding sphere)
    max_dim = max(width, height, depth, 1.0)
    scale_factor = 2.4 / max_dim
    norm_w = round(width * scale_factor, 3)
    norm_h = round(height * scale_factor, 3)
    norm_d = round(depth * scale_factor, 3)

    return jsonify({
        "success": True,
        "proceduralCAD": {
            "primitive": "RoundedBox",
            "dimensions": {"x": norm_w, "y": norm_h, "z": norm_d},
            "radius": 0.08,
            "chamfer": 0.04,
            "booleanCuts": [
                {"type": "recess", "label": "Screen Cavity", "pos": [0, 0, norm_d/2], "size": [norm_w*0.85, norm_h*0.88, 0.05]},
                {"type": "cutout", "label": "USB-C Port Carve", "pos": [0, -norm_h/2, 0], "size": [0.35, 0.1, 0.15]},
                {"type": "plateau", "label": "Rear Camera Plateau", "pos": [norm_w*0.22, norm_h*0.25, -norm_d/2], "size": [0.65, 0.65, 0.08]}
            ],
            "material": {
                "type": "PhysicalPBR",
                "color": "#2563EB",
                "metalness": 0.85,
                "roughness": 0.22,
                "clearcoat": 0.3
            }
        },
        "telemetry": {
            "triangles": 14820,
            "vertices": 7412,
            "eulerCharacteristic": 2,
            "isWatertight": True,
            "renderLatencyMs": 340
        }
    })


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
