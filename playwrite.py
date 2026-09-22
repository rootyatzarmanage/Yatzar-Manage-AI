import asyncio
import os
import time
from urllib.parse import urljoin
from playwright.async_api import async_playwright

URL = "https://www.samsung.com/in/smartphones/galaxy-s25-ultra/buy/"
OUTPUT_FOLDER = "folder_B"


async def download_image(request_context, url, index, semaphore):
    async with semaphore:
        try:
            response = await request_context.get(url, timeout=15000)
            if response.ok:
                content_type = response.headers.get("content-type", "").lower()

                if "png" in content_type:
                    ext = ".png"
                elif "webp" in content_type:
                    ext = ".webp"
                elif "svg" in content_type:
                    ext = ".svg"
                elif "gif" in content_type:
                    ext = ".gif"
                else:
                    ext = ".jpg"

                filename = os.path.join(OUTPUT_FOLDER, f"image_{index}{ext}")
                with open(filename, "wb") as f:
                    f.write(await response.body())
        except Exception:
            pass


async def scrape_images():
    os.makedirs(OUTPUT_FOLDER, exist_ok=True)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080}
        )
        page = await context.new_page()

        await page.goto(URL, wait_until="domcontentloaded", timeout=60000)
        await page.wait_for_timeout(2000)

        # Scroll to load lazy-loaded elements
        await page.evaluate("window.scrollBy(0, 1500)")
        await page.wait_for_timeout(1000)

        images = await page.locator("img").all()
        image_urls = []

        for image in images:
            for attr in ["src", "data-src", "data-desktop-src", "data-mobile-src"]:
                val = await image.get_attribute(attr)
                if val and val.strip() and not val.strip().startswith("data:"):
                    full_url = urljoin(URL, val.strip())
                    if full_url.startswith(("http://", "https://")):
                        image_urls.append(full_url)

        image_urls = list(dict.fromkeys(image_urls))
        print(f"Images found: {len(image_urls)}")

        semaphore = asyncio.Semaphore(16)
        tasks = [
            download_image(context.request, url, i, semaphore)
            for i, url in enumerate(image_urls, 1)
        ]
        await asyncio.gather(*tasks)

        await browser.close()


if __name__ == "__main__":
    start = time.perf_counter()

    asyncio.run(scrape_images())

    end = time.perf_counter()

    count = len([
        f for f in os.listdir(OUTPUT_FOLDER)
        if f.lower().endswith((".jpg", ".jpeg", ".png", ".webp", ".svg", ".gif"))
    ])

    print("\n--- Playwright Results ---")
    print(f"Images downloaded: {count}")
    print(f"Time taken: {end - start:.4f} seconds")