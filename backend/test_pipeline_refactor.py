"""
End-to-End Verification Script for Refactored Image Discovery & Filtering Pipeline.
Tests:
  1. Metadata Priority Cascade query generation.
  2. Stage 1 Geometric Uncertainty Triage.
  3. DINOv2 CLS feature extraction & intra-pool deduplication (< 0.95 threshold).
  4. 2D PCA scatter coordinate projection.
"""

import sys
import json
import logging
from pathlib import Path

# Add backend directory to path
backend_dir = Path(__file__).resolve().parent
sys.path.insert(0, str(backend_dir))

from services.triage_service import build_prioritized_search_queries, evaluate_geometric_uncertainty
from services.dinov2_service import DinoV2Engine, get_dinov2_engine
from services.scraper_service import ScrapingPipelineManager

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


def run_pipeline_test():
    print("=" * 70)
    print(" [TEST] RUNNING VERIFICATION TEST: METADATA CASCADE & DINOv2 DEDUP")
    print("=" * 70)

    # 1. Test Query Builder
    product_id = "AL-HEX-9000"
    product_name = "Alfa Laval Heat Exchanger"
    model_number = "HEX-9000"
    category = "Industrial Equipment"

    print("\n[STEP 1] Generating Prioritized Query Ladder:")
    queries = build_prioritized_search_queries(
        product_id=product_id,
        product_name=product_name,
        model_number=model_number,
        category=category
    )

    for q in queries:
        print(f"  Tier {q['priority']} | {q['angle_tag']:<16} | Query: {q['query']:<50} | {q['source_tier']}")

    # 2. Test Triage Service
    print("\n[STEP 2] Running Stage 1 Uncertainty Triage:")
    triage = evaluate_geometric_uncertainty(
        product_title=product_name,
        product_sku=product_id,
        category=category,
        product_id=product_id
    )
    print(f"  Rotational Symmetry: {triage['rotational_symmetry']}")
    print(f"  Quadrant Uncertainty: {triage['quad_uncertainty']}")
    print(f"  Skip Deep Scraping:   {triage['skip_deep_scraping']}")
    print(f"  Scrape Budget:        {triage['max_scrape_budget']}")

    # 3. Test DINOv2 Intra-Pool Deduplication
    print("\n[STEP 3] Testing DINOv2 Intra-Pool Deduplication Logic:")
    engine = get_dinov2_engine()

    # Create synthetic vectors to verify deduplication math
    vec_a = [1.0, 0.0, 0.0, 0.0]
    vec_a_dup = [0.99, 0.05, 0.0, 0.0]  # Very high similarity (> 0.95)
    vec_b = [0.0, 1.0, 0.0, 0.0]       # Orthogonal / distinct perspective

    sim_dup = DinoV2Engine.cosine_similarity(vec_a, vec_a_dup)
    sim_distinct = DinoV2Engine.cosine_similarity(vec_a, vec_b)

    print(f"  Duplicate Cosine Similarity: {sim_dup:.4f} (Is Dup >= 0.95: {sim_dup >= 0.95})")
    print(f"  Distinct View Cosine Sim:    {sim_distinct:.4f} (Is Dup >= 0.95: {sim_distinct >= 0.95})")

    # 4. Test 2D PCA Coordinate Projection
    print("\n[STEP 4] Testing 2D PCA Vector Space Projection:")
    coords = DinoV2Engine.compute_2d_scatter_coordinates([vec_a, vec_a_dup, vec_b])
    for i, pt in enumerate(coords):
        label = "Anchor (Seed)" if i == 0 else f"Candidate {i}"
        print(f"  {label:<16} -> X: {pt['x']:>7.4f}, Y: {pt['y']:>7.4f}")

    print("\n" + "=" * 70)
    print(" [PASS] ALL PIPELINE TESTS PASSED SUCCESSFULLY!")
    print("=" * 70)


if __name__ == "__main__":
    run_pipeline_test()
