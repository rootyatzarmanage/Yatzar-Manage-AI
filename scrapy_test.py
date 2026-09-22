import scrapy
import os
import time
from urllib.parse import urljoin
from scrapy.crawler import CrawlerProcess

URL = "https://www.samsung.com/in/smartphones/galaxy-s25-ultra/buy/"
OUTPUT_FOLDER = "folder_A"


class ImageSpider(scrapy.Spider):
    name = "image_spider"
    start_urls = [URL]

    def parse(self, response):
        raw_urls = (
            response.css("img::attr(src)").getall()
            + response.css("img::attr(data-src)").getall()
            + response.css("img::attr(data-desktop-src)").getall()
            + response.css("img::attr(data-mobile-src)").getall()
        )

        image_urls = []
        for raw_url in raw_urls:
            raw_url = raw_url.strip()
            if raw_url and not raw_url.startswith("data:"):
                full_url = urljoin(response.url, raw_url)
                if full_url.startswith(("http://", "https://")):
                    image_urls.append(full_url)

        image_urls = list(dict.fromkeys(image_urls))

        print(f"Images found: {len(image_urls)}")

        for i, url in enumerate(image_urls, 1):
            yield scrapy.Request(
                url,
                callback=self.save_image,
                cb_kwargs={"index": i}
            )

    def save_image(self, response, index):
        content_type = response.headers.get(
            b"Content-Type", b""
        ).decode().lower()

        if "png" in content_type:
            ext = ".png"
        elif "webp" in content_type:
            ext = ".webp"
        elif "svg" in content_type:
            ext = ".svg"
        else:
            ext = ".jpg"

        filename = os.path.join(
            OUTPUT_FOLDER,
            f"image_{index}{ext}"
        )

        with open(filename, "wb") as f:
            f.write(response.body)


if __name__ == "__main__":
    os.makedirs(OUTPUT_FOLDER, exist_ok=True)

    start = time.perf_counter()

    settings = {
        "LOG_ENABLED": False,
        "ROBOTSTXT_OBEY": False,
        "CONCURRENT_REQUESTS": 16,
        "USER_AGENT": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
        "REQUEST_FINGERPRINTER_IMPLEMENTATION": "2.7",
    }

    process = CrawlerProcess(settings=settings)
    process.crawl(ImageSpider)
    process.start()

    end = time.perf_counter()

    count = len([
        f for f in os.listdir(OUTPUT_FOLDER)
        if f.lower().endswith((".jpg", ".jpeg", ".png", ".webp", ".svg"))
    ])

    print("\n--- Scrapy Results ---")
    print(f"Images downloaded: {count}")
    print(f"Time taken: {end - start:.4f} seconds")