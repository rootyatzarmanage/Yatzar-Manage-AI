"""
End-to-End Live Browser Validation Suite for Yatzar
Tests all 3 products (ViewSonic LS800HD, Mahr MarSurf PS 10, Hansgrohe SilicaTec C51)
Includes:
- A/B Stale-State Invalidation Test on Product A
- Strict Pixal3D Engine Enforcement
- Zero TripoSR Leakage Verification on Reference Sheet
- Complete 6-File Regression Test Execution
- Frontend Production Build Verification
"""

import os
import sys
import time
import io
import json
import urllib.request
import subprocess
from pathlib import Path
from playwright.sync_api import sync_playwright

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

BASE_DIR = Path(__file__).resolve().parent
RESULTS_FILE = BASE_DIR / "backend" / "scratch" / "validation_results.json"
RESULTS_FILE.parent.mkdir(parents=True, exist_ok=True)

VALIDATION_DATA = {
    "product_a_viewsonic": {},
    "product_b_mahr": {},
    "product_c_hansgrohe": {},
    "ab_stale_state_test": {},
    "regression_tests": {},
    "frontend_build": {},
    "timings": {}
}


def query_backend_api(endpoint):
    url = f"http://127.0.0.1:5000{endpoint}"
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        return {"error": str(e), "success": False}


def poll_backend_research(product_id, max_wait_sec=90):
    t0 = time.time()
    while time.time() - t0 < max_wait_sec:
        time.sleep(1)
        data = query_backend_api(f"/api/research/status/{product_id}")
        job = data.get("job") or {}
        st = data.get("status") or job.get("status")
        if data.get("success") and st in ("COMPLETED", "FAILED"):
            results = job.get("results") or data.get("results") or {}
            summary = results.get("summary") or results.get("research_summary") or {}
            return st == "COMPLETED", job.get("job_id") or data.get("job_id"), results, summary
    return False, None, {}, {}


def poll_backend_reconstruction(product_id, max_wait_sec=60):
    t0 = time.time()
    while time.time() - t0 < max_wait_sec:
        time.sleep(0.5)
        data = query_backend_api(f"/api/reconstruct/status/{product_id}")
        if data.get("success") and data.get("status") in ("COMPLETED", "FAILED"):
            job = data.get("job") or {}
            result = job.get("result") or data.get("result") or data
            return data.get("status") == "COMPLETED", job.get("job_id") or data.get("job_id"), result
    return False, None, {}


def validate_product_a_viewsonic(page):
    print("\n" + "="*70, flush=True)
    print("STEP 1: VALIDATING PRODUCT A — VIEWSONIC LS800HD (WITH A/B TEST)", flush=True)
    print("="*70, flush=True)

    t0_start = time.time()
    res_a = {}
    VALIDATION_DATA["product_a_viewsonic"] = res_a

    # Reset browser state
    page.goto("http://127.0.0.1:3000", wait_until="networkidle")
    page.evaluate("() => { localStorage.clear(); sessionStorage.clear(); }")
    page.reload(wait_until="networkidle")
    time.sleep(1.5)

    # 1. Fill Input Form
    page.fill("textarea", "ViewSonic LS800HD 5000 Lumens 1080p Laser Installation Projector")
    page.fill("input[placeholder*='e.g. SINK-01']", "VS-LS800HD")
    page.fill("input[placeholder*='e.g. Hansgrohe']", "ViewSonic LS800HD Laser Projector")
    page.fill("input[placeholder*='e.g. 43218000']", "LS800HD")
    try:
        page.select_option("select", label="Consumer Electronics")
    except Exception:
        pass

    print("[INPUT] Form populated for ViewSonic LS800HD", flush=True)
    t0_research = time.time()

    # Track requests to verify no auto-reconstruct
    auto_rec_calls = []
    def track_rec_calls(req):
        if "/api/reconstruct/queue" in req.url:
            auto_rec_calls.append(req.url)
    page.on("request", track_rec_calls)

    page.click("button:has-text('Start Autonomous Pipeline')")

    # Wait for research completion in browser UI and backend
    print("[RESEARCH] Waiting for Research terminal COMPLETED state...", flush=True)
    page.wait_for_selector("button:has-text('Proceed to Image Approval'):not([disabled])", timeout=90000)
    t_research_end = time.time()
    res_a["research_duration_s"] = round(t_research_end - t0_research, 2)

    research_ok, job_id, research_results, research_summary = poll_backend_research("VS-LS800HD")
    res_a["research_job_id"] = job_id
    res_a["research_summary"] = research_summary
    res_a["research_completed"] = research_ok
    print(f"[RESEARCH] Job {job_id} COMPLETED ({research_ok}) in {res_a['research_duration_s']}s", flush=True)
    print(f"  Curated count: {len(research_results.get('images', []))}", flush=True)
    print(f"  Rejected count: {len(research_results.get('rejected_images', []))}", flush=True)
    print(f"  Summary: {research_summary}", flush=True)

    # 2. Image Approval Stage
    print("[STAGE] Transitioning to Image Approval...", flush=True)
    page.click("button:has-text('Proceed to Image Approval')")
    time.sleep(2)
    page.screenshot(path="backend/scratch/TEMP_e2e_viewsonic_image_approval.png")

    # Verify no auto-reconstruction occurred
    print(f"[NO-AUTO-RECONSTRUCT] Auto-reconstruction calls during research: {len(auto_rec_calls)} (Pass if 0)", flush=True)
    res_a["no_auto_reconstruction"] = (len(auto_rec_calls) == 0)

    # Deliberately pick candidate index 1 as IMAGE_A
    use_ref_buttons = page.locator("button:has-text('Use as Reference')").all()
    if len(use_ref_buttons) > 1:
        use_ref_buttons[1].click()
        time.sleep(1)
        print("[IMAGE APPROVAL] Deliberately clicked 'Use as Reference' for Candidate [1]", flush=True)
    elif len(use_ref_buttons) > 0:
        use_ref_buttons[0].click()
        time.sleep(1)
        print("[IMAGE APPROVAL] Clicked 'Use as Reference' for Candidate [0]", flush=True)

    selected_image_a = page.evaluate("""() => {
        const ring = document.querySelector('div[class*="ring-brand-500"] img, div[class*="border-brand-500"] img');
        return ring ? { src: ring.src, alt: ring.alt } : null;
    }""")
    print("[IMAGE APPROVAL] Selected IMAGE_A info:", selected_image_a, flush=True)
    res_a["selected_image_a"] = selected_image_a

    # 3. 3D Generation Stage
    print("[PIXAL3D] Advancing to 3D Generation stage...", flush=True)
    page.click("button:has-text('Generate 3D Model with Pixal3D')")
    time.sleep(2)

    # Click Generate 3D with Pixal3D explicitly
    t0_gen_a = time.time()
    print("[PIXAL3D] Clicking Generate 3D with Pixal3D for MODEL_A...", flush=True)
    page.click("button:has-text('Generate 3D with Pixal3D')")

    # Wait for Three.js canvas to render
    page.wait_for_selector("canvas", timeout=40000)
    t_gen_a_end = time.time()
    rec_completed_a, rec_job_a, model_result_a = poll_backend_reconstruction("VS-LS800HD", max_wait_sec=20)
    res_a["rec_job_a"] = rec_job_a
    res_a["rec_completed_a"] = rec_completed_a
    res_a["rec_duration_a_s"] = round(t_gen_a_end - t0_gen_a, 2)
    res_a["model_result_a"] = model_result_a
    print(f"[PIXAL3D] MODEL_A Job {rec_job_a} COMPLETED ({rec_completed_a}) in {res_a['rec_duration_a_s']}s", flush=True)
    print(f"  Model URL: {model_result_a.get('model_url')}", flush=True)
    print(f"  Engine: {model_result_a.get('reconstruction_engine') or model_result_a.get('engine')}", flush=True)
    print(f"  Mesh Stats: {model_result_a.get('mesh_stats') or model_result_a.get('mesh_telemetry')}", flush=True)

    time.sleep(2)
    page.screenshot(path="backend/scratch/TEMP_e2e_viewsonic_3d_render_a.png")

    # 4. A/B Stale-State Invalidation Test
    print("\n--- RUNNING STALE STATE INVALIDATION TEST (IMAGE_A -> IMAGE_B) ---", flush=True)
    ab_data = {}
    VALIDATION_DATA["ab_stale_state_test"] = ab_data
    ab_data["image_a"] = selected_image_a
    ab_data["model_a"] = model_result_a

    print("[A/B TEST] Clicking Back to Image Approval...", flush=True)
    page.click("button:has-text('Back to Image Approval')")
    time.sleep(2)

    # Click an unselected candidate (Candidate B)
    use_ref_buttons = page.locator("button:has-text('Use as Reference')").all()
    if len(use_ref_buttons) > 0:
        use_ref_buttons[0].click()
        time.sleep(1)
        print("[A/B TEST] Selected alternate candidate [0] as IMAGE_B", flush=True)

    selected_image_b = page.evaluate("""() => {
        const ring = document.querySelector('div[class*="ring-brand-500"] img, div[class*="border-brand-500"] img');
        return ring ? { src: ring.src, alt: ring.alt } : null;
    }""")
    print("[A/B TEST] Selected IMAGE_B info:", selected_image_b, flush=True)
    ab_data["image_b"] = selected_image_b

    images_differ = bool(selected_image_a and selected_image_b and selected_image_a["src"] != selected_image_b["src"])
    print(f"[A/B TEST] Proof IMAGE_A != IMAGE_B: {images_differ}", flush=True)
    ab_data["images_differ"] = images_differ

    # Proceed to Generate 3D stage
    page.click("button:has-text('Generate 3D Model with Pixal3D')")
    time.sleep(2)

    # Check whether old MODEL_A is cleared / requires explicit generation
    ready_btn = page.locator("button:has-text('Generate 3D with Pixal3D')").count()
    print(f"[A/B TEST] Explicit 'Generate 3D with Pixal3D' button present (old model cleared): {ready_btn > 0}", flush=True)
    ab_data["explicit_generation_required"] = (ready_btn > 0)

    # Generate MODEL_B explicitly
    t0_gen_b = time.time()
    page.click("button:has-text('Generate 3D with Pixal3D')")
    page.wait_for_selector("canvas", timeout=40000)
    t_gen_b_end = time.time()

    rec_completed_b, rec_job_b, model_result_b = poll_backend_reconstruction("VS-LS800HD", max_wait_sec=20)
    ab_data["rec_job_b"] = rec_job_b
    ab_data["rec_completed_b"] = rec_completed_b
    ab_data["rec_duration_b_s"] = round(t_gen_b_end - t0_gen_b, 2)
    ab_data["model_result_b"] = model_result_b
    print(f"[A/B TEST] MODEL_B Job {rec_job_b} COMPLETED ({rec_completed_b}) in {ab_data['rec_duration_b_s']}s", flush=True)

    url_a = model_result_a.get("model_url") if isinstance(model_result_a, dict) else None
    url_b = model_result_b.get("model_url") if isinstance(model_result_b, dict) else None
    models_differ = bool(url_a and url_b and url_a != url_b)
    print(f"[A/B TEST] Proof MODEL_A ({url_a}) != MODEL_B ({url_b}): {models_differ}", flush=True)
    ab_data["models_differ"] = models_differ

    time.sleep(2)
    page.screenshot(path="backend/scratch/TEMP_e2e_viewsonic_3d_render_b.png")

    # 5. 3D Approval Validation
    print("\n[STAGE 4] Proceeding to 3D Approval Stage...", flush=True)
    page.click("button:has-text('Proceed to 3D Approval Validation')")
    time.sleep(3)
    page.screenshot(path="backend/scratch/TEMP_e2e_viewsonic_approval_stage.png")

    # 6. Reference Sheet (Stage 5)
    print("\n[STAGE 5] Proceeding to Reference Sheet Stage...", flush=True)
    page.click("button:has-text('Generate Product Reference Sheet')")
    time.sleep(4)

    # Wait for deterministic multi-views
    for _ in range(40):
        if page.locator("img[alt*='View 3D Render']").count() >= 4:
            break
        time.sleep(0.5)

    page.screenshot(path="backend/scratch/TEMP_e2e_viewsonic_reference_sheet.png")

    # Inspect Reference Sheet text & elements
    content = page.content()
    has_pixal3d_verified = "PIXAL3D VERIFIED" in content
    has_pixal3d_engine = "Pixal3D (TencentARC/CUDA)" in content
    has_triposr_leak = "TRIPOSR VERIFIED" in content or "TripoSR (CUDA)" in content

    print(f"[REFERENCE SHEET] Has 'PIXAL3D VERIFIED': {has_pixal3d_verified}", flush=True)
    print(f"[REFERENCE SHEET] Has 'Pixal3D (TencentARC/CUDA)': {has_pixal3d_engine}", flush=True)
    print(f"[REFERENCE SHEET] Has TripoSR leak: {has_triposr_leak} (Pass if False)", flush=True)

    res_a["has_pixal3d_verified"] = has_pixal3d_verified
    res_a["has_pixal3d_engine"] = has_pixal3d_engine
    res_a["has_triposr_leak"] = has_triposr_leak
    res_a["total_elapsed_s"] = round(time.time() - t0_start, 2)

    return res_a


def validate_product_b_mahr(page):
    print("\n" + "="*70, flush=True)
    print("STEP 2: VALIDATING PRODUCT B — MAHR MARSURF PS 10", flush=True)
    print("="*70, flush=True)

    t0_start = time.time()
    res_b = {}
    VALIDATION_DATA["product_b_mahr"] = res_b

    # Click New Product or reset
    page.click("button:has-text('New')")
    time.sleep(1.5)

    # Fill Input Form
    page.fill("textarea", "Mahr MarSurf PS 10 Mobile Surface Roughness Measuring Instrument 6910230")
    page.fill("input[placeholder*='e.g. SINK-01']", "MAHR-PS10")
    page.fill("input[placeholder*='e.g. Hansgrohe']", "Mahr MarSurf PS 10 Roughness Measuring Instrument")
    page.fill("input[placeholder*='e.g. 43218000']", "MarSurf PS 10")
    try:
        page.select_option("select", label="General")
    except Exception:
        pass

    print("[INPUT] Form populated for Mahr MarSurf PS 10", flush=True)
    t0_research = time.time()

    page.click("button:has-text('Start Autonomous Pipeline')")

    # Wait for completion
    print("[RESEARCH] Waiting for Research terminal COMPLETED state...", flush=True)
    page.wait_for_selector("button:has-text('Proceed to Image Approval'):not([disabled])", timeout=90000)
    res_b["research_duration_s"] = round(time.time() - t0_research, 2)

    research_ok, job_id, research_results, research_summary = poll_backend_research("MAHR-PS10")
    res_b["research_job_id"] = job_id
    res_b["research_summary"] = research_summary
    res_b["research_completed"] = research_ok
    print(f"[RESEARCH] Job {job_id} COMPLETED ({research_ok}) in {res_b['research_duration_s']}s", flush=True)
    print(f"  Curated count: {len(research_results.get('images', []))}", flush=True)
    print(f"  Summary: {research_summary}", flush=True)

    # Image Approval
    page.click("button:has-text('Proceed to Image Approval')")
    time.sleep(2)
    page.screenshot(path="backend/scratch/TEMP_e2e_mahr_image_approval.png")

    use_ref_buttons = page.locator("button:has-text('Use as Reference')").all()
    if len(use_ref_buttons) > 0:
        use_ref_buttons[0].click()
        time.sleep(1)

    selected_image = page.evaluate("""() => {
        const ring = document.querySelector('div[class*="ring-brand-500"] img, div[class*="border-brand-500"] img');
        return ring ? { src: ring.src, alt: ring.alt } : null;
    }""")
    print("[IMAGE APPROVAL] Selected image info:", selected_image, flush=True)
    res_b["selected_image"] = selected_image

    # Generate 3D with Pixal3D
    page.click("button:has-text('Generate 3D Model with Pixal3D')")
    time.sleep(2)

    t0_gen = time.time()
    page.click("button:has-text('Generate 3D with Pixal3D')")
    page.wait_for_selector("canvas", timeout=40000)
    t_gen_end = time.time()

    rec_completed, rec_job, model_result = poll_backend_reconstruction("MAHR-PS10", max_wait_sec=20)
    res_b["rec_job"] = rec_job
    res_b["rec_completed"] = rec_completed
    res_b["rec_duration_s"] = round(t_gen_end - t0_gen, 2)
    res_b["model_result"] = model_result
    print(f"[PIXAL3D] Job {rec_job} COMPLETED ({rec_completed}) in {res_b['rec_duration_s']}s", flush=True)
    print(f"  Model URL: {model_result.get('model_url')}", flush=True)
    print(f"  Engine: {model_result.get('reconstruction_engine') or model_result.get('engine')}", flush=True)

    time.sleep(2)
    page.screenshot(path="backend/scratch/TEMP_e2e_mahr_3d_render.png")

    # 3D Approval
    page.click("button:has-text('Proceed to 3D Approval Validation')")
    time.sleep(3)
    page.screenshot(path="backend/scratch/TEMP_e2e_mahr_approval_stage.png")

    # Reference Sheet
    page.click("button:has-text('Generate Product Reference Sheet')")
    time.sleep(4)

    for _ in range(40):
        if page.locator("img[alt*='View 3D Render']").count() >= 4:
            break
        time.sleep(0.5)

    page.screenshot(path="backend/scratch/TEMP_e2e_mahr_reference_sheet.png")

    content = page.content()
    res_b["has_pixal3d_verified"] = "PIXAL3D VERIFIED" in content
    res_b["has_pixal3d_engine"] = "Pixal3D (TencentARC/CUDA)" in content
    res_b["has_triposr_leak"] = "TRIPOSR VERIFIED" in content or "TripoSR (CUDA)" in content
    res_b["total_elapsed_s"] = round(time.time() - t0_start, 2)

    print(f"[REFERENCE SHEET] Has 'PIXAL3D VERIFIED': {res_b['has_pixal3d_verified']}", flush=True)
    print(f"[REFERENCE SHEET] Has 'Pixal3D (TencentARC/CUDA)': {res_b['has_pixal3d_engine']}", flush=True)
    print(f"[REFERENCE SHEET] Has TripoSR leak: {res_b['has_triposr_leak']}", flush=True)

    return res_b


def validate_product_c_hansgrohe(page):
    print("\n" + "="*70, flush=True)
    print("STEP 3: VALIDATING PRODUCT C — HANSGROHE SILICATEC C51 KITCHEN SINK 43218000", flush=True)
    print("="*70, flush=True)

    t0_start = time.time()
    res_c = {}
    VALIDATION_DATA["product_c_hansgrohe"] = res_c

    # Reset
    page.click("button:has-text('New')")
    time.sleep(1.5)

    # Fill Input Form
    page.fill("textarea", "Hansgrohe SilicaTec C51 Undermount Single Bowl Kitchen Sink 43218000")
    page.fill("input[placeholder*='e.g. SINK-01']", "HG-43218000")
    page.fill("input[placeholder*='e.g. Hansgrohe']", "Hansgrohe SilicaTec C51 Kitchen Sink 43218000")
    page.fill("input[placeholder*='e.g. 43218000']", "43218000")
    try:
        page.select_option("select", label="Sanitaryware")
    except Exception:
        pass

    print("[INPUT] Form populated for Hansgrohe SilicaTec C51", flush=True)
    t0_research = time.time()

    page.click("button:has-text('Start Autonomous Pipeline')")

    # Wait for completion
    print("[RESEARCH] Waiting for Research terminal COMPLETED state...", flush=True)
    page.wait_for_selector("button:has-text('Proceed to Image Approval'):not([disabled])", timeout=90000)
    res_c["research_duration_s"] = round(time.time() - t0_research, 2)

    research_ok, job_id, research_results, research_summary = poll_backend_research("HG-43218000")
    res_c["research_job_id"] = job_id
    res_c["research_summary"] = research_summary
    res_c["research_completed"] = research_ok
    print(f"[RESEARCH] Job {job_id} COMPLETED ({research_ok}) in {res_c['research_duration_s']}s", flush=True)
    print(f"  Curated count: {len(research_results.get('images', []))}", flush=True)
    print(f"  Summary: {research_summary}", flush=True)

    # Image Approval
    page.click("button:has-text('Proceed to Image Approval')")
    time.sleep(2)
    page.screenshot(path="backend/scratch/TEMP_e2e_hansgrohe_image_approval.png")

    use_ref_buttons = page.locator("button:has-text('Use as Reference')").all()
    if len(use_ref_buttons) > 0:
        use_ref_buttons[0].click()
        time.sleep(1)

    selected_image = page.evaluate("""() => {
        const ring = document.querySelector('div[class*="ring-brand-500"] img, div[class*="border-brand-500"] img');
        return ring ? { src: ring.src, alt: ring.alt } : null;
    }""")
    print("[IMAGE APPROVAL] Selected image info:", selected_image, flush=True)
    res_c["selected_image"] = selected_image

    # Generate 3D with Pixal3D
    page.click("button:has-text('Generate 3D Model with Pixal3D')")
    time.sleep(2)

    t0_gen = time.time()
    page.click("button:has-text('Generate 3D with Pixal3D')")
    page.wait_for_selector("canvas", timeout=40000)
    t_gen_end = time.time()

    rec_completed, rec_job, model_result = poll_backend_reconstruction("HG-43218000", max_wait_sec=20)
    res_c["rec_job"] = rec_job
    res_c["rec_completed"] = rec_completed
    res_c["rec_duration_s"] = round(t_gen_end - t0_gen, 2)
    res_c["model_result"] = model_result
    print(f"[PIXAL3D] Job {rec_job} COMPLETED ({rec_completed}) in {res_c['rec_duration_s']}s", flush=True)
    print(f"  Model URL: {model_result.get('model_url')}", flush=True)
    print(f"  Engine: {model_result.get('reconstruction_engine') or model_result.get('engine')}", flush=True)

    time.sleep(2)
    page.screenshot(path="backend/scratch/TEMP_e2e_hansgrohe_3d_render.png")

    # 3D Approval
    page.click("button:has-text('Proceed to 3D Approval Validation')")
    time.sleep(3)
    page.screenshot(path="backend/scratch/TEMP_e2e_hansgrohe_approval_stage.png")

    # Reference Sheet
    page.click("button:has-text('Generate Product Reference Sheet')")
    time.sleep(4)

    for _ in range(40):
        if page.locator("img[alt*='View 3D Render']").count() >= 4:
            break
        time.sleep(0.5)

    page.screenshot(path="backend/scratch/TEMP_e2e_hansgrohe_reference_sheet.png")

    content = page.content()
    res_c["has_pixal3d_verified"] = "PIXAL3D VERIFIED" in content
    res_c["has_pixal3d_engine"] = "Pixal3D (TencentARC/CUDA)" in content
    res_c["has_triposr_leak"] = "TRIPOSR VERIFIED" in content or "TripoSR (CUDA)" in content
    res_c["total_elapsed_s"] = round(time.time() - t0_start, 2)

    print(f"[REFERENCE SHEET] Has 'PIXAL3D VERIFIED': {res_c['has_pixal3d_verified']}", flush=True)
    print(f"[REFERENCE SHEET] Has 'Pixal3D (TencentARC/CUDA)': {res_c['has_pixal3d_engine']}", flush=True)
    print(f"[REFERENCE SHEET] Has TripoSR leak: {res_c['has_triposr_leak']}", flush=True)

    return res_c


def run_regression_suite():
    print("\n" + "="*70, flush=True)
    print("STEP 4: RUNNING COMPLETE REGRESSION SUITE (6 TEST FILES)", flush=True)
    print("="*70, flush=True)

    test_files = [
        "tests/test_identifier_policy.py",
        "backend/tests/test_scraper_harvesting.py",
        "backend/tests/test_research_correctness.py",
        "backend/tests/test_lifecycle_and_queue.py",
        "tests/test_reconstruction_and_reference_selection.py",
        "backend/tests/test_end_to_end_baseline.py",
    ]

    python_exe = str(BASE_DIR / "backend" / "venv" / "Scripts" / "python.exe")
    reg_results = {}
    VALIDATION_DATA["regression_tests"] = reg_results

    for tf in test_files:
        t0 = time.time()
        cmd = [python_exe, "-m", "unittest", tf.replace("/", ".").replace(".py", "")]
        proc = subprocess.run(
            cmd,
            cwd=str(BASE_DIR),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True
        )
        elapsed = round(time.time() - t0, 3)
        passed = (proc.returncode == 0)
        status_label = "PASS" if passed else "FAIL"
        print(f"[{status_label}] {tf} ({elapsed}s)", flush=True)
        reg_results[tf] = {
            "passed": passed,
            "duration_s": elapsed,
            "returncode": proc.returncode,
            "output_tail": proc.stdout[-500:] if proc.stdout else ""
        }

    # Frontend Build
    print("\n[FRONTEND BUILD] Running npm run build in frontend/...", flush=True)
    t0_build = time.time()
    npm_cmd = "npm.cmd" if sys.platform == "win32" else "npm"
    proc_build = subprocess.run(
        [npm_cmd, "run", "build"],
        cwd=str(BASE_DIR / "frontend"),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True
    )
    b_elapsed = round(time.time() - t0_build, 3)
    b_passed = (proc_build.returncode == 0)
    print(f"[{'PASS' if b_passed else 'FAIL'}] Frontend Production Build ({b_elapsed}s)", flush=True)
    VALIDATION_DATA["frontend_build"] = {
        "passed": b_passed,
        "duration_s": b_elapsed,
        "output_tail": proc_build.stdout[-500:] if proc_build.stdout else ""
    }


def main():
    print("#"*70, flush=True)
    print("STARTING YATZAR FULL CLEAN-STATE 3-PRODUCT E2E VALIDATION RUN", flush=True)
    print("#"*70, flush=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 900})

        try:
            validate_product_a_viewsonic(page)
            validate_product_b_mahr(page)
            validate_product_c_hansgrohe(page)
        except Exception as e:
            print(f"ERROR during browser validation: {e}", flush=True)
            import traceback
            traceback.print_exc()
        finally:
            browser.close()

    run_regression_suite()

    with open(RESULTS_FILE, "w", encoding="utf-8") as f:
        json.dump(VALIDATION_DATA, f, indent=2)

    print("\n" + "="*70, flush=True)
    print(f"VALIDATION FINISHED! Results written to {RESULTS_FILE}", flush=True)
    print("="*70, flush=True)


if __name__ == "__main__":
    main()
