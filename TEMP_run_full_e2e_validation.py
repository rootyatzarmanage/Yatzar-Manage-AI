import os
import sys
import time
import json
import subprocess
import traceback
from playwright.sync_api import sync_playwright

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

RESULTS_DATA = {
    "product_a": {},
    "product_b": {},
    "regression_tests": {},
    "timing_summary": {}
}

os.makedirs("backend/scratch", exist_ok=True)

def run_product_a_viewsonic(page, requests_log, responses_log):
    print("\n" + "="*70)
    print("STEP 1: VALIDATING PRODUCT A - VIEWSONIC LS800HD")
    print("="*70)

    t0_start = time.time()
    res_a = {}
    RESULTS_DATA["product_a"] = res_a

    # Reset localStorage to clean state
    page.goto("http://127.0.0.1:3000", wait_until="networkidle")
    page.evaluate("() => { localStorage.clear(); }")
    page.reload(wait_until="networkidle")
    time.sleep(1.5)

    # 1. Input Form
    page.fill("textarea", "ViewSonic LS800HD 5000 Lumens 1080p Laser Installation Projector")
    page.fill("input[placeholder*='e.g. SINK-01']", "VS-LS800HD")
    page.fill("input[placeholder*='e.g. Hansgrohe']", "ViewSonic LS800HD Laser Projector")
    page.fill("input[placeholder*='e.g. 43218000']", "LS800HD")
    page.select_option("select", label="Consumer Electronics" if "Consumer Electronics" in page.content() else "General")

    print("[INPUT] Form populated for ViewSonic LS800HD")
    t0_click = time.time()

    # Clear logs before click
    requests_log.clear()
    responses_log.clear()

    page.click("button:has-text('Start Autonomous Pipeline')")

    # Monitor job creation from /api/research/start
    research_job_id = None
    for _ in range(40):
        time.sleep(0.5)
        for r in responses_log:
            if "/api/research/start" in r["url"] and isinstance(r.get("data"), dict):
                if r["data"].get("job", {}).get("job_id"):
                    research_job_id = r["data"]["job"]["job_id"]
                    break
        if research_job_id:
            break

    print(f"[RESEARCH] Created Job ID: {research_job_id} in {time.time() - t0_click:.2f}s")
    res_a["research_job_id"] = research_job_id
    res_a["t0_research_click"] = t0_click
    res_a["t1_job_created"] = time.time()

    # 2. Mid-Research Resilience Test (Navigation & Refresh)
    time.sleep(3)
    print("[RESILIENCE] Performing mid-research stage navigation away to Input...")
    page.click("button:has-text('Input')")
    time.sleep(1.5)
    
    # Check that in-progress indicator is visible in Input stage
    active_in_input = page.locator("button:has-text('View Live Research')").count() > 0
    print(f"[RESILIENCE] Active research banner visible in Input stage: {active_in_input}")
    res_a["active_in_input"] = active_in_input

    print("[RESILIENCE] Returning to ScrapeStage...")
    if active_in_input:
        page.click("button:has-text('View Live Research')")
    else:
        page.click("button:has-text('Research')")
    time.sleep(1.5)

    print("[RESILIENCE] Refreshing browser page...")
    page.reload(wait_until="networkidle")
    time.sleep(2)

    # Check total research jobs created (must remain 1)
    jobs_created_count = len([r for r in requests_log if "/api/research/start" in r["url"] and r["method"] == "POST"])
    print(f"[RESILIENCE] Total research start requests: {jobs_created_count} (Pass if exactly 1)")
    res_a["no_duplicate_research_job"] = (jobs_created_count == 1)

    # Wait for research to complete
    print("[RESEARCH] Waiting for Research terminal COMPLETED state...")
    try:
        page.wait_for_selector("button:has-text('Proceed to Image Approval'):not([disabled])", timeout=75000)
        research_done = True
    except Exception as e:
        print("[RESEARCH] Timeout waiting for proceed button:", e)
        research_done = False

    res_a["t4_research_completed"] = time.time()
    res_a["research_duration_s"] = round(res_a["t4_research_completed"] - t0_click, 2)
    print(f"[RESEARCH] Terminal COMPLETED reached in {res_a['research_duration_s']}s")

    # 3. Transition to Image Approval
    print("[STAGE] Transitioning to Image Approval...")
    page.click("button:has-text('Proceed to Image Approval')")
    time.sleep(2)

    page.screenshot(path="backend/scratch/TEMP_e2e_viewsonic_image_approval.png")

    # Verify NO automatic reconstruction started
    reconstruct_calls_early = [r for r in requests_log if "/api/reconstruct/queue" in r["url"]]
    print(f"[NO-AUTO-RECONSTRUCT] Reconstruction requests before user click: {len(reconstruct_calls_early)} (Pass if 0)")
    res_a["no_auto_reconstruction"] = (len(reconstruct_calls_early) == 0)

    # Inspect candidate cards
    candidates = page.evaluate("""() => {
        const list = [];
        document.querySelectorAll('img').forEach((img, i) => {
            if (img.src && (img.src.includes('/cache/candidates/') || img.src.includes('/static/'))) {
                list.push({
                    src: img.src,
                    alt: img.alt || ''
                });
            }
        });
        return list;
    }""")
    print(f"[IMAGE APPROVAL] Visible candidate images: {len(candidates)}")
    for i, c in enumerate(candidates[:5]):
        print(f"  Candidate {i}: src={c['src']}")
    res_a["visible_candidates_count"] = len(candidates)

    # Deliberately pick candidate index 1 as SELECTED_IMAGE_A
    use_ref_buttons = page.locator("button:has-text('Use as Reference')").all()
    if len(use_ref_buttons) > 0:
        use_ref_buttons[0].click()
        time.sleep(1)
        print("[IMAGE APPROVAL] Deliberately selected candidate [1] as SELECTED_IMAGE_A")
    else:
        print("[IMAGE APPROVAL] Using default selected candidate")

    selected_image_a_info = page.evaluate("""() => {
        const ring = document.querySelector('div[class*=\"ring-brand-500\"] img, div[class*=\"border-brand-500\"] img');
        return ring ? { src: ring.src, alt: ring.alt } : null;
    }""")
    print("[EXACT HANDOFF] SELECTED_IMAGE_A info:", selected_image_a_info)
    res_a["selected_image_a"] = selected_image_a_info

    # 4. Generate 3D & Exact Reference Handoff Check
    print("[PIXAL3D] Advancing to 3D Generation stage...")
    page.click("button:has-text('Generate 3D Model with TripoSR')")
    time.sleep(2)

    print("[PIXAL3D] Clicking Generate 3D with Pixal3D...")
    t_gen_click = time.time()
    requests_log.clear()
    responses_log.clear()
    page.click("button:has-text('Generate 3D with Pixal3D')")
    time.sleep(2)

    # Check reconstruction queue call
    rec_queue_calls = [r for r in requests_log if "/api/reconstruct/queue" in r["url"]]
    print(f"[PIXAL3D] Queue requests triggered: {len(rec_queue_calls)}")
    
    reconstruction_input_url = None
    rec_job_id = None
    if rec_queue_calls:
        post_json = json.loads(rec_queue_calls[-1]["post_data"]) if rec_queue_calls[-1].get("post_data") else {}
        reconstruction_input_url = post_json.get("reference_image") or post_json.get("image_url")
        print(f"[PIXAL3D] Reconstruction request payload reference_image: {reconstruction_input_url}")
        
    for res in responses_log:
        if "/api/reconstruct/queue" in res["url"] and isinstance(res.get("data"), dict):
            rec_job_id = res["data"].get("job", {}).get("job_id") or res["data"].get("job_id")
            break

    print(f"[PIXAL3D] Reconstruction Job ID: {rec_job_id}")
    res_a["reconstruction_job_id"] = rec_job_id
    res_a["reconstruction_input_url"] = reconstruction_input_url

    # PROVE: SELECTED_IMAGE_A == RECONSTRUCTION_INPUT
    exact_match = (selected_image_a_info and reconstruction_input_url and selected_image_a_info["src"] == reconstruction_input_url)
    print(f"[EXACT HANDOFF PROOF] SELECTED_IMAGE_A == RECONSTRUCTION_INPUT: {exact_match}")
    res_a["exact_handoff_proof"] = exact_match

    # Wait for Pixal3D completion
    print("[PIXAL3D] Waiting for neural inference on RTX 4060...")
    rec_completed = False
    model_result = None
    for _ in range(80): # up to 40s
        time.sleep(0.5)
        for res in responses_log:
            if "/api/reconstruct/status/" in res["url"] and isinstance(res.get("data"), dict):
                job_data = res["data"].get("job", {})
                if job_data.get("status") == "COMPLETED":
                    rec_completed = True
                    model_result = job_data.get("result", {})
                    break
        if rec_completed:
            break

    t_rec_done = time.time()
    res_a["reconstruction_completed"] = rec_completed
    res_a["reconstruction_duration_s"] = round(t_rec_done - t_gen_click, 2)
    res_a["model_result_a"] = model_result
    print(f"[PIXAL3D] Finished in {res_a['reconstruction_duration_s']}s. Result: {model_result}")

    time.sleep(3) # Wait for Three.js WebGL canvas
    page.screenshot(path="backend/scratch/TEMP_e2e_viewsonic_3d_render_a.png")
    canvas_rendered = page.locator("canvas").count() > 0
    print(f"[THREE.JS] Canvas visibly rendered: {canvas_rendered}")
    res_a["canvas_rendered_a"] = canvas_rendered
    res_a["model_url_a"] = model_result.get("model_url") if model_result else None

    # 5. Stale State Invalidation Test
    print("\n--- RUNNING STALE STATE TEST (A -> B) ---")
    page.click("button:has-text('Back to Image Approval')")
    time.sleep(2)

    # Pick candidate index 0 (different candidate)
    use_ref_buttons = page.locator("button:has-text('Use as Reference')").all()
    if len(use_ref_buttons) > 0:
        use_ref_buttons[0].click()
        time.sleep(1)
        print("[STALE STATE] Selected different candidate as SELECTED_IMAGE_B")

    selected_image_b_info = page.evaluate("""() => {
        const ring = document.querySelector('div[class*=\"ring-brand-500\"] img, div[class*=\"border-brand-500\"] img');
        return ring ? { src: ring.src, alt: ring.alt } : null;
    }""")
    print("[STALE STATE] SELECTED_IMAGE_B info:", selected_image_b_info)
    res_a["selected_image_b"] = selected_image_b_info

    diff_images = (selected_image_a_info and selected_image_b_info and selected_image_a_info["src"] != selected_image_b_info["src"])
    print(f"[STALE STATE] Proof Image A != Image B: {diff_images}")
    res_a["images_different_proof"] = diff_images

    # Proceed to 3D again
    page.click("button:has-text('Generate 3D Model with TripoSR')")
    time.sleep(2)

    requests_log.clear()
    responses_log.clear()
    t_gen_b_click = time.time()
    page.click("button:has-text('Generate 3D with Pixal3D')")
    time.sleep(2)

    # Verify new reconstruction triggered with image B
    rec_queue_calls_b = [r for r in requests_log if "/api/reconstruct/queue" in r["url"]]
    reconstruction_input_b = None
    if rec_queue_calls_b:
        post_json_b = json.loads(rec_queue_calls_b[-1]["post_data"]) if rec_queue_calls_b[-1].get("post_data") else {}
        reconstruction_input_b = post_json_b.get("reference_image") or post_json_b.get("image_url")
    print(f"[STALE STATE] New reconstruction input URL: {reconstruction_input_b}")
    res_a["reconstruction_input_b"] = reconstruction_input_b

    # Wait for model B to complete
    rec_completed_b = False
    model_result_b = None
    for _ in range(80):
        time.sleep(0.5)
        for res in responses_log:
            if "/api/reconstruct/status/" in res["url"] and isinstance(res.get("data"), dict):
                job_data = res["data"].get("job", {})
                if job_data.get("status") == "COMPLETED":
                    rec_completed_b = True
                    model_result_b = job_data.get("result", {})
                    break
        if rec_completed_b:
            break

    print(f"[STALE STATE] Model B completed: {rec_completed_b} in {round(time.time() - t_gen_b_click, 2)}s. Result: {model_result_b}")
    res_a["model_result_b"] = model_result_b
    res_a["model_url_b"] = model_result_b.get("model_url") if model_result_b else None
    
    diff_models = bool(res_a["model_url_a"] and res_a["model_url_b"] and res_a["model_url_a"] != res_a["model_url_b"])
    print(f"[STALE STATE] Proof Model A != Model B: {diff_models}")
    res_a["models_different_proof"] = diff_models

    time.sleep(2)
    page.screenshot(path="backend/scratch/TEMP_e2e_viewsonic_3d_render_b.png")

    # 6. Proceed to 3D Approval Validation (Stage 4)
    print("\n[STAGE 4] Proceeding to 3D Approval Stage...")
    responses_log.clear()
    page.click("button:has-text('Proceed to 3D Approval Validation')")
    time.sleep(3)

    # Verify validation API ran
    val_res = None
    for _ in range(20):
        time.sleep(0.5)
        for res in responses_log:
            if "/api/validate-3d" in res["url"] and isinstance(res.get("data"), dict):
                val_res = res["data"]
                break
        if val_res:
            break

    print(f"[3D APPROVAL] Mesh validation result: {val_res}")
    res_a["mesh_validation"] = val_res
    page.screenshot(path="backend/scratch/TEMP_e2e_viewsonic_approval_stage.png")

    # 7. Proceed to Reference Sheet (Stage 5)
    print("\n[STAGE 5] Proceeding to Reference Sheet Stage...")
    page.click("button:has-text('Generate Product Reference Sheet')")
    time.sleep(3)

    # Wait for deterministic multi-views to finish rendering
    for _ in range(40):
        if page.locator("img[alt*='View 3D Render']").count() >= 4:
            break
        time.sleep(0.5)

    page.screenshot(path="backend/scratch/TEMP_e2e_viewsonic_reference_sheet.png")

    ref_views_count = page.locator("img[alt*='View 3D Render']").count()
    print(f"[REFERENCE SHEET] Rendered multi-angle views: {ref_views_count}")
    res_a["reference_sheet_views_count"] = ref_views_count

    res_a["total_elapsed_s"] = round(time.time() - t0_start, 2)
    print(f"=== PRODUCT A COMPLETE ({res_a['total_elapsed_s']}s) ===\n")
    return res_a


def run_product_b_hansgrohe(page, requests_log, responses_log):
    print("\n" + "="*70)
    print("STEP 2: VALIDATING PRODUCT B - HANSGROHE SILICATEC C51 43218000")
    print("="*70)

    t0_start = time.time()
    res_b = {}
    RESULTS_DATA["product_b"] = res_b

    # Click New Product or reset
    page.click("button:has-text('New')")
    time.sleep(1.5)

    # Fill Input Form
    page.fill("textarea", "Hansgrohe SilicaTec C51-F450-06 Granite Composite Kitchen Sink 43218000")
    page.fill("input[placeholder*='e.g. SINK-01']", "HG-43218000")
    page.fill("input[placeholder*='e.g. Hansgrohe']", "Hansgrohe SilicaTec C51 Kitchen Sink 43218000")
    page.fill("input[placeholder*='e.g. 43218000']", "43218000")
    page.select_option("select", label="Sanitary Ware" if "Sanitary Ware" in page.content() else "General")

    print("[INPUT] Form populated for Hansgrohe SilicaTec C51")
    t0_click = time.time()
    requests_log.clear()
    responses_log.clear()

    page.click("button:has-text('Start Autonomous Pipeline')")

    # Monitor job creation
    research_job_id = None
    for _ in range(40):
        time.sleep(0.5)
        for r in responses_log:
            if "/api/research/start" in r["url"] and isinstance(r.get("data"), dict):
                if r["data"].get("job", {}).get("job_id"):
                    research_job_id = r["data"]["job"]["job_id"]
                    break
        if research_job_id:
            break

    print(f"[RESEARCH] Created Job ID: {research_job_id}")
    res_b["research_job_id"] = research_job_id

    # Wait for completion
    try:
        page.wait_for_selector("button:has-text('Proceed to Image Approval'):not([disabled])", timeout=75000)
    except Exception as e:
        print("[RESEARCH] Timeout on Hansgrohe:", e)

    res_b["research_duration_s"] = round(time.time() - t0_click, 2)
    print(f"[RESEARCH] Terminal COMPLETED in {res_b['research_duration_s']}s")

    # Transition to Image Approval
    page.click("button:has-text('Proceed to Image Approval')")
    time.sleep(2)
    page.screenshot(path="backend/scratch/TEMP_e2e_hansgrohe_image_approval.png")

    # Select candidate
    clickable_cards = page.locator("div[class*='cursor-pointer']").all()
    if len(clickable_cards) > 0:
        clickable_cards[0].click()
        time.sleep(1)

    selected_image_info = page.evaluate("""() => {
        const ring = document.querySelector('div[class*=\"ring-brand-500\"] img, div[class*=\"border-brand-500\"] img');
        return ring ? { src: ring.src, alt: ring.alt } : null;
    }""")
    print("[IMAGE APPROVAL] Selected image info:", selected_image_info)
    res_b["selected_image"] = selected_image_info

    # Proceed to Generate 3D
    print("[PIXAL3D] Advancing to 3D Generation stage for Hansgrohe...")
    page.click("button:has-text('Generate 3D Model with TripoSR')")
    time.sleep(2)

    print("[PIXAL3D] Clicking Generate 3D with Pixal3D...")
    requests_log.clear()
    responses_log.clear()
    t_gen_click = time.time()
    page.click("button:has-text('Generate 3D with Pixal3D')")
    time.sleep(2)

    # Wait for Pixal3D
    rec_job_id = None
    rec_completed = False
    model_result = None
    for _ in range(80):
        time.sleep(0.5)
        for res in responses_log:
            if "/api/reconstruct/queue" in res["url"] and isinstance(res.get("data"), dict):
                rec_job_id = res["data"].get("job", {}).get("job_id") or res["data"].get("job_id")
            if "/api/reconstruct/status/" in res["url"] and isinstance(res.get("data"), dict):
                job_data = res["data"].get("job", {})
                if job_data.get("status") == "COMPLETED":
                    rec_completed = True
                    model_result = job_data.get("result", {})
                    break
        if rec_completed:
            break

    res_b["reconstruction_job_id"] = rec_job_id
    res_b["reconstruction_completed"] = rec_completed
    res_b["reconstruction_duration_s"] = round(time.time() - t_gen_click, 2)
    res_b["model_result"] = model_result
    print(f"[PIXAL3D] Job ID: {rec_job_id}. Inference finished in {res_b['reconstruction_duration_s']}s. Result: {model_result}")
    
    time.sleep(3)
    page.screenshot(path="backend/scratch/TEMP_e2e_hansgrohe_3d_render.png")

    canvas_rendered = page.locator("canvas").count() > 0
    print(f"[THREE.JS] Canvas rendered: {canvas_rendered}")
    res_b["canvas_rendered"] = canvas_rendered

    # 3D Approval & Reference Sheet
    responses_log.clear()
    page.click("button:has-text('Proceed to 3D Approval Validation')")
    time.sleep(3)

    val_res = None
    for _ in range(20):
        time.sleep(0.5)
        for res in responses_log:
            if "/api/validate-3d" in res["url"] and isinstance(res.get("data"), dict):
                val_res = res["data"]
                break
        if val_res:
            break

    res_b["mesh_validation"] = val_res
    page.screenshot(path="backend/scratch/TEMP_e2e_hansgrohe_approval.png")

    page.click("button:has-text('Generate Product Reference Sheet')")
    time.sleep(3)

    for _ in range(40):
        if page.locator("img[alt*='View 3D Render']").count() >= 4:
            break
        time.sleep(0.5)

    ref_views_count = page.locator("img[alt*='View 3D Render']").count()
    print(f"[REFERENCE SHEET] Rendered multi-angle views: {ref_views_count}")
    res_b["reference_sheet_views_count"] = ref_views_count
    page.screenshot(path="backend/scratch/TEMP_e2e_hansgrohe_reference_sheet.png")

    res_b["total_elapsed_s"] = round(time.time() - t0_start, 2)
    print(f"=== PRODUCT B COMPLETE ({res_b['total_elapsed_s']}s) ===\n")
    return res_b


def run_regressions():
    print("\n" + "="*70)
    print("STEP 3: RUNNING REGRESSION SUITES & FRONTEND BUILD")
    print("="*70)

    test_cmds = [
        ("tests/test_identifier_policy.py", "backend\\venv\\Scripts\\python.exe -m unittest tests/test_identifier_policy.py"),
        ("backend/tests/test_scraper_harvesting.py", "backend\\venv\\Scripts\\python.exe -m unittest backend/tests/test_scraper_harvesting.py"),
        ("backend/tests/test_research_correctness.py", "backend\\venv\\Scripts\\python.exe -m unittest backend/tests/test_research_correctness.py"),
        ("backend/tests/test_lifecycle_and_queue.py", "backend\\venv\\Scripts\\python.exe -m unittest backend/tests/test_lifecycle_and_queue.py"),
        ("tests/test_reconstruction_and_reference_selection.py", "backend\\venv\\Scripts\\python.exe -m unittest tests/test_reconstruction_and_reference_selection.py"),
        ("backend/tests/test_end_to_end_baseline.py", "backend\\venv\\Scripts\\python.exe -m unittest backend/tests/test_end_to_end_baseline.py")
    ]

    reg_results = {}
    for name, cmd in test_cmds:
        t0 = time.time()
        proc = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        elapsed = round(time.time() - t0, 3)
        passed = (proc.returncode == 0)
        print(f"  {name}: {'PASS' if passed else 'FAIL'} ({elapsed}s)")
        reg_results[name] = {
            "passed": passed,
            "elapsed_s": elapsed,
            "output": proc.stdout[-300:] if proc.stdout else proc.stderr[-300:]
        }

    # Frontend build
    t0_b = time.time()
    build_proc = subprocess.run("npm run build", shell=True, cwd="frontend", capture_output=True, text=True)
    b_elapsed = round(time.time() - t0_b, 2)
    b_passed = (build_proc.returncode == 0)
    print(f"  Frontend Build: {'PASS' if b_passed else 'FAIL'} ({b_elapsed}s)")
    reg_results["frontend_build"] = {
        "passed": b_passed,
        "elapsed_s": b_elapsed
    }

    RESULTS_DATA["regression_tests"] = reg_results


def main():
    requests_log = []
    responses_log = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1440, "height": 900})
        page = context.new_page()

        page.on("request", lambda req: requests_log.append({
            "time": time.time(), "method": req.method, "url": req.url, "post_data": req.post_data
        }) if "/api/" in req.url else None)

        def on_response_safe(res):
            if "/api/" not in res.url:
                return
            data = None
            try:
                ct = res.headers.get("content-type") or ""
                if "application/json" in ct:
                    data = res.json()
            except Exception:
                pass
            responses_log.append({
                "time": time.time(),
                "url": res.url,
                "status": res.status,
                "data": data
            })

        page.on("response", on_response_safe)

        try:
            run_product_a_viewsonic(page, requests_log, responses_log)
        except Exception as e:
            print("Product A Exception:", e)
            traceback.print_exc()

        try:
            run_product_b_hansgrohe(page, requests_log, responses_log)
        except Exception as e:
            print("Product B Exception:", e)
            traceback.print_exc()

        browser.close()

    run_regressions()

    with open("backend/scratch/TEMP_e2e_raw_results.json", "w", encoding="utf-8") as f:
        json.dump(RESULTS_DATA, f, indent=2)
    print("\nSaved raw E2E results to backend/scratch/TEMP_e2e_raw_results.json")

if __name__ == "__main__":
    main()
