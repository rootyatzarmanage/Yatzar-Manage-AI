import os
import sys
import time
import json
import urllib.request
import urllib.error
from pathlib import Path

BACKEND_URL = "http://127.0.0.1:5000"
INPUT_IMAGE = str(Path("backend/cache/candidates/verified_4d28321d64f4.jpg").resolve())
PRODUCT_ID = f"PROD-VIEWSONIC-E2E-{int(time.time())}"
PRODUCT_TITLE = "ViewSonic LS800HD Laser Projector"

def post_json(url, data):
    req = urllib.request.Request(
        url,
        data=json.dumps(data).encode("utf-8"),
        headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode("utf-8"))

def get_json(url):
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode("utf-8"))

def main():
    print("=" * 70)
    print("STARTING REAL PRODUCTION E2E SHOWCASE VERIFICATION")
    print(f"Backend URL: {BACKEND_URL}")
    print(f"Product: {PRODUCT_TITLE} (ID: {PRODUCT_ID})")
    print(f"Reference Image: {INPUT_IMAGE}")
    print("=" * 70)

    # 1. Health check
    health = get_json(f"{BACKEND_URL}/api/health")
    print(f"[1/5] Backend health: {health.get('status')} (GPU: {health.get('gpu_available')})")

    # 2. Enqueue Reconstruction
    payload = {
        "product_id": PRODUCT_ID,
        "product_title": PRODUCT_TITLE,
        "product_sku": "LS800HD",
        "reference_image": INPUT_IMAGE,
        "engine": "Pixal3D"
    }

    print("\n[2/5] Enqueueing 3D reconstruction into serialized Pixal3D queue...")
    queue_res = post_json(f"{BACKEND_URL}/api/reconstruct/queue", payload)
    job_id = queue_res.get("job_id")
    print(f"  Enqueued Job ID: {job_id}")
    print(f"  Initial Status: {queue_res.get('status')}")
    print(f"  Queue Position: {queue_res.get('queue_position')}")

    # 3. Poll status until completion
    print("\n[3/5] Polling reconstruction status from live backend...")
    t0 = time.time()
    last_phase = None

    while True:
        status_res = get_json(f"{BACKEND_URL}/api/reconstruct/status/{job_id}")
        canonical_status = status_res.get("status")
        job_data = status_res.get("job", {})
        current_phase = job_data.get("current_phase", "Queued")
        progress = job_data.get("progress", 0.0)
        elapsed = round(time.time() - t0, 1)

        if current_phase != last_phase:
            print(f"  [{elapsed:6.1f}s] Stage: {current_phase} (Progress: {int(progress * 100)}%)")
            last_phase = current_phase

        if canonical_status == "COMPLETED":
            print(f"\n[4/5] Job COMPLETED successfully in {elapsed}s!")
            print(f"  Canonical Status: {canonical_status}")
            print(f"  Model URL: {status_res.get('model_url')}")
            print(f"  Local Path: {status_res.get('local_path')}")
            print(f"  Mesh Stats: {status_res.get('mesh_stats')}")
            break
        elif canonical_status in ("FAILED", "CANCELLED"):
            print(f"\n[ERROR] Job ended with status: {canonical_status}")
            print(f"  Error: {status_res.get('error') or job_data.get('error')}")
            sys.exit(1)

        time.sleep(5.0)

    # 4. Verify generated GLB on disk
    local_path = status_res.get("local_path")
    if not os.path.exists(local_path):
        print(f"[ERROR] Output GLB not found at: {local_path}")
        sys.exit(1)

    file_size_bytes = os.path.getsize(local_path)
    file_size_mb = file_size_bytes / (1024 * 1024)
    print(f"\n[5/5] GLB Asset Verification:")
    print(f"  Path: {local_path}")
    print(f"  Size: {file_size_bytes:,} bytes ({file_size_mb:.2f} MB)")

    # Save summary report
    summary = {
        "product_id": PRODUCT_ID,
        "product_title": PRODUCT_TITLE,
        "job_id": job_id,
        "input_image": INPUT_IMAGE,
        "output_glb": local_path,
        "file_size_bytes": file_size_bytes,
        "file_size_mb": round(file_size_mb, 2),
        "total_runtime_sec": elapsed,
        "mesh_stats": status_res.get("mesh_stats"),
        "telemetry": status_res.get("telemetry"),
        "status": canonical_status
    }

    with open("TEMP_E2E_SHOWCASE_SUMMARY.json", "w") as f:
        json.dump(summary, f, indent=2)

    print("\nSHOWCASE RUN COMPLETED SUCCESSFULLY.")
    print("Summary saved to TEMP_E2E_SHOWCASE_SUMMARY.json")

if __name__ == "__main__":
    main()
