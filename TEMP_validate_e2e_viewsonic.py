import os
import sys
import time
import json
from playwright.sync_api import sync_playwright

def run_viewsonic_e2e():
    print("=== STARTING VIEWSONIC LS800HD E2E VALIDATION ===")
    events = []
    requests_log = []
    responses_log = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1440, "height": 900})
        page = context.new_page()

        # Monitor API calls
        def on_request(req):
            if "/api/" in req.url:
                requests_log.append({
                    "time": time.time(),
                    "method": req.method,
                    "url": req.url,
                    "post_data": req.post_data
                })
        def on_response(res):
            if "/api/" in res.url:
                try:
                    data = res.json()
                except Exception:
                    data = res.text()[:200]
                responses_log.append({
                    "time": time.time(),
                    "url": res.url,
                    "status": res.status,
                    "data": data
                })

        page.on("request", on_request)
        page.on("response", on_response)

        # 1. Open Input Stage
        t0_start = time.time()
        page.goto("http://127.0.0.1:3000", wait_until="networkidle", timeout=15000)
        print(f"Page loaded: title='{page.title()}', url='{page.url}'")

        # Fill in Product Details
        page.fill("textarea[placeholder*='describe what to scrape']", "ViewSonic LS800HD 5000 Lumens 1080p Laser Installation Projector")
        page.fill("input[placeholder*='e.g. SINK-01']", "VS-LS800HD-01")
        page.fill("input[placeholder*='e.g. Hansgrohe']", "ViewSonic LS800HD Laser Projector")
        page.fill("input[placeholder*='e.g. 43218000']", "LS800HD")
        page.select_option("select", label="Electronics" if "Electronics" in page.content() else "General")

        print("Filled input form. Triggering Research...")
        t_research_click = time.time()
        page.click("button:has-text('Start Autonomous Pipeline')")

        # Wait for research job creation request
        research_job_id = None
        for _ in range(30):
            time.sleep(0.5)
            for r in responses_log:
                if "/api/research/jobs" in r["url"] and r.get("data") and isinstance(r["data"], dict):
                    if r["data"].get("job_id"):
                        research_job_id = r["data"]["job_id"]
                        break
            if research_job_id:
                break

        print(f"Research job created: {research_job_id}")

        # Resilience Test: While Research is running, navigate to Input and return to ScrapeStage, then reload
        time.sleep(3) # Wait for research to be actively RUNNING
        print("Executing Navigation & Refresh Resilience check during active research...")
        
        # Navigate to Stage 0 (Input)
        page.click("button:has-text('New Product')")
        time.sleep(1)
        print("Navigated back to Input Stage. Checking job status banner...")
        
        # Check that active research banner shows in Input stage
        in_progress_banner = page.locator("button:has-text('View Live Research')").count()
        print(f"Active research banner visible in Input stage: {in_progress_banner > 0}")

        # Return to Live Research
        if in_progress_banner > 0:
            page.click("button:has-text('View Live Research')")
        else:
            page.click("button:has-text('Research')")
        time.sleep(1)

        # Refresh browser
        print("Reloading browser window during active research...")
        page.reload(wait_until="networkidle")
        time.sleep(2)

        # Verify job is re-attached and not duplicated
        jobs_created = [r for r in requests_log if "/api/research/jobs" in r["url"] and r["method"] == "POST"]
        print(f"Total research jobs created so far: {len(jobs_created)} (Expected exactly 1)")

        # Wait for Research completion
        print("Waiting for Research to complete...")
        research_done = False
        t_research_start = time.time()
        for i in range(120): # up to 60s
            time.sleep(0.5)
            # Check if ScrapeStage shows "Proceed to Image Approval"
            proceed_btn = page.locator("button:has-text('Proceed to Image Approval')")
            if proceed_btn.count() > 0 and not proceed_btn.is_disabled():
                research_done = True
                print(f"Research completed in ~{time.time() - t_research_start:.1f}s")
                break
        
        if not research_done:
            print("WARNING: Research did not complete within timeout!")

        # Record Research accounting metrics
        time.sleep(1)
        page_content = page.content()
        cards = page.locator(".tailadmin-card, div[class*='border']").all()
        print(f"ScrapeStage loaded with images. Proceeding to Image Approval...")

        # 2. IMAGE APPROVAL
        page.click("button:has-text('Proceed to Image Approval')")
        time.sleep(2)
        print("Current Stage: Image Approval. Verifying no automatic reconstruction...")

        reconstruct_reqs = [r for r in requests_log if "/api/reconstruct" in r["url"]]
        print(f"Reconstruction requests before user click: {len(reconstruct_reqs)} (Expected 0)")

        # Save screenshot
        os.makedirs("backend/scratch", exist_ok=True)
        page.screenshot(path="backend/scratch/TEMP_viewsonic_image_approval.png")
        print("Saved screenshot to backend/scratch/TEMP_viewsonic_image_approval.png")

        # Pick candidate A
        # Let's inspect candidate cards on page
        cand_cards = page.locator("div[class*='cursor-pointer']").all()
        print(f"Found {len(cand_cards)} clickable candidate cards")

        # Let's extract candidate details from DOM
        candidates_data = page.evaluate("""() => {
            const cards = [];
            document.querySelectorAll('img').forEach((img, i) => {
                if (img.src && img.src.includes('/cache/candidates/')) {
                    cards.push({
                        src: img.src,
                        alt: img.alt,
                        parent: img.parentElement ? img.parentElement.className : ''
                    });
                }
            });
            return cards;
        }""")
        print(f"Candidate images on page: {len(candidates_data)}")
        for idx, c in enumerate(candidates_data[:5]):
            print(f"  [{idx}] {c['src']} (alt={c['alt']})")

        # Click second candidate to test deliberate manual selection (SELECTED_IMAGE_A)
        if len(cand_cards) > 1:
            cand_cards[1].click()
            time.sleep(1)
            print("Selected candidate index 1 as SELECTED_IMAGE_A")

        selected_image_a_src = page.evaluate("""() => {
            const sel = document.querySelector('div[class*=\"ring-brand-500\"] img, div[class*=\"border-brand-500\"] img');
            return sel ? sel.src : (document.querySelector('img[src*=\"/cache/candidates/\"]') ? document.querySelector('img[src*=\"/cache/candidates/\"]').src : null);
        }""")
        print(f"SELECTED_IMAGE_A: {selected_image_a_src}")

        # 3. GENERATE 3D MODEL
        print("Clicking Generate 3D Model with TripoSR (transitions to Stage 3)...")
        page.click("button:has-text('Generate 3D Model with TripoSR')")
        time.sleep(2)

        # In Stage 3, check if Start Reconstruction button is needed or already triggered
        gen_click = page.locator("button:has-text('Synthesize 3D Model'), button:has-text('Generate 3D'), button:has-text('Re-run')")
        # In Generate3DStage: `startReconstruction` is called either upon entry or button
        time.sleep(2)

        # Check reconstruct network call
        reconstruct_calls = [r for r in requests_log if "/api/reconstruct/queue" in r["url"]]
        print(f"Reconstruction queue requests: {len(reconstruct_calls)}")
        reconstruct_job_id = None
        if reconstruct_calls:
            print("Queue request payload:", reconstruct_calls[-1]["post_data"])
            for res in responses_log:
                if "/api/reconstruct/queue" in res["url"] and isinstance(res.get("data"), dict):
                    reconstruct_job_id = res["data"].get("job_id")
                    print(f"Reconstruction Job ID: {reconstruct_job_id}")

        # Wait for reconstruction to complete
        print("Waiting for Pixal3D reconstruction to finish on RTX 4060...")
        reconstruct_done = False
        t_rec_start = time.time()
        for i in range(80): # up to 40s
            time.sleep(0.5)
            # Check response for job status COMPLETED
            for res in responses_log:
                if f"/api/reconstruct/jobs/{reconstruct_job_id}" in res["url"] and isinstance(res.get("data"), dict):
                    if res["data"].get("status") == "COMPLETED":
                        reconstruct_done = True
                        break
            if reconstruct_done:
                print(f"Pixal3D finished in ~{time.time() - t_rec_start:.1f}s")
                break
        
        time.sleep(3) # Wait for Three.js canvas to render
        page.screenshot(path="backend/scratch/TEMP_viewsonic_3d_stage.png")
        print("Saved screenshot to backend/scratch/TEMP_viewsonic_3d_stage.png")

        # Verify Three.js Canvas is rendered
        canvas_count = page.locator("canvas").count()
        print(f"Three.js canvas elements rendered: {canvas_count}")

        # 4. STALE STATE TEST
        print("--- EXECUTING STALE STATE TEST ---")
        print("Navigating back to Image Approval...")
        page.click("button:has-text('Back to Image Approval')")
        time.sleep(2)

        # Select candidate index 0 (different from candidate 1)
        cand_cards_again = page.locator("div[class*='cursor-pointer']").all()
        if len(cand_cards_again) > 0:
            cand_cards_again[0].click()
            time.sleep(1)
            print("Selected candidate index 0 as SELECTED_IMAGE_B")

        selected_image_b_src = page.evaluate("""() => {
            const sel = document.querySelector('div[class*=\"ring-brand-500\"] img, div[class*=\"border-brand-500\"] img');
            return sel ? sel.src : null;
        }""")
        print(f"SELECTED_IMAGE_B: {selected_image_b_src}")
        print(f"Proof A != B: {selected_image_a_src != selected_image_b_src}")

        # Proceed to 3D again
        page.click("button:has-text('Generate 3D Model with TripoSR')")
        time.sleep(2)

        # Check if previous model was invalidated
        # If it was invalidated, activeProduct.modelUrl is null until newly reconstructed
        print("Waiting for second reconstruction for Image B...")
        time.sleep(8)
        page.screenshot(path="backend/scratch/TEMP_viewsonic_3d_stage_b.png")

        # 5. 3D APPROVAL STAGE
        print("Navigating to 3D Approval Stage...")
        proceed_3d_appr = page.locator("button:has-text('Proceed to 3D Approval Validation')")
        if proceed_3d_appr.count() > 0 and not proceed_3d_appr.is_disabled():
            proceed_3d_appr.click()
            time.sleep(3)
            print("Current Stage: 3D Approval. Running mesh validation...")
            page.screenshot(path="backend/scratch/TEMP_viewsonic_approval_stage.png")

            # 6. REFERENCE SHEET STAGE
            ref_sheet_btn = page.locator("button:has-text('Generate Product Reference Sheet')")
            if ref_sheet_btn.count() > 0 and not ref_sheet_btn.is_disabled():
                print("Clicking Generate Product Reference Sheet...")
                ref_sheet_btn.click()
                time.sleep(3)
                print("Current Stage: Reference Sheet Stage.")
                page.screenshot(path="backend/scratch/TEMP_viewsonic_reference_sheet.png")
                views_rendered = page.locator("img, canvas").count()
                print(f"Reference sheet views elements: {views_rendered}")

        browser.close()
        print("ViewSonic E2E Run Complete!")

if __name__ == "__main__":
    run_viewsonic_e2e()
