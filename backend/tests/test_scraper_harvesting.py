import os
import sys
import unittest
from unittest.mock import MagicMock, patch

# Ensure backend directory is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from services.scraper_service import PlaywrightSearchEngine, PlannedQuery, QueryFamily, URLDeduplicator

class TestScraperHarvestingLayer(unittest.TestCase):
    """
    Focused regression tests for the Yatzar image retrieval and harvesting layer.
    Verifies that unrelated trending murl strings are rejected, genuine image-result containers
    are extracted, strict-quoted queries retry unquoted on zero results, and provenance is preserved.
    """

    def test_criterion_a_unrelated_raw_murls_rejected(self):
        """
        Criterion A: Raw Bing unrelated murl values (trending carousel, sidebars, arbitrary scripts)
        are NOT accepted unless attached to a valid image-result record.
        """
        raw_wallpaper_trending_html = """
        <html>
        <head><title>Bing Images</title></head>
        <body>
            <!-- Wallpaper / Trending Banner -->
            <div class="carousel trending">
                <div class="irh">
                    <a class="iusc" m='{"murl":"https://wallpapercave.com/cricket_trending.jpg","t":"Cricket Wallpaper"}'></a>
                </div>
            </div>
            <!-- Sidebar Recommendations -->
            <div id="b_side" class="sidebar">
                <a class="iusc" m='{"murl":"https://deviantart.com/devotional_painting.jpg","t":"Devotional Art"}'></a>
            </div>
            <!-- Arbitrary page script containing raw murl strings -->
            <script>
                var bg = {"murl":"https://bing.com/az/hprichbg/car_wallpaper.jpg"};
            </script>
            <!-- Unrelated navigation footer -->
            <div class="b_explore">
                <a class="iusc" m='{"murl":"https://explore.org/nature_festival.jpg","t":"Festival"}'></a>
            </div>
            <!-- Random container without result card markers -->
            <div>
                <a class="iusc" m='{"murl":"https://random.org/orphan_image.jpg","t":"Orphan"}'></a>
            </div>
        </body>
        </html>
        """
        extracted = PlaywrightSearchEngine.extract_records_from_html(raw_wallpaper_trending_html)
        self.assertEqual(len(extracted), 0, "Unrelated trending/sidebar/script murls must yield 0 records")

    def test_criterion_b_valid_result_containers_extracted(self):
        """
        Criterion B: Valid Bing image-result records (inside .imgpt, .iuscp, [data-idx], .dgControl)
        ARE extracted with metadata.
        """
        genuine_search_html = """
        <html>
        <body>
            <div class="dgControl">
                <ul class="dgControl_list">
                    <li data-idx="0">
                        <div class="imgpt">
                            <div class="iuscp">
                                <a class="iusc" m='{"murl":"https://www.viewsonic.com/assets/ls800hd_front.jpg","purl":"https://www.viewsonic.com/us/ls800hd.html","turl":"https://t.bing.com/th?id=OIP.123","t":"ViewSonic LS800HD Laser Projector","desc":"5000 ANSI Lumens installation projector"}'></a>
                            </div>
                        </div>
                    </li>
                    <li data-idx="1">
                        <div class="imgpt">
                            <div class="iuscp">
                                <a class="iusc" m='{"murl":"https://m.media-amazon.com/images/I/71xyzLS800HD.jpg","purl":"https://www.amazon.com/dp/B07XYZ","turl":"https://t.bing.com/th?id=OIP.456","t":"ViewSonic LS800HD Projector Rear Ports","desc":"Official rear connectivity"}'></a>
                            </div>
                        </div>
                    </li>
                </ul>
            </div>
        </body>
        </html>
        """
        records = PlaywrightSearchEngine.extract_records_from_html(genuine_search_html)
        self.assertEqual(len(records), 2, "Expected 2 genuine image records")
        
        rec1 = records[0]
        self.assertEqual(rec1["murl"], "https://www.viewsonic.com/assets/ls800hd_front.jpg")
        self.assertEqual(rec1["purl"], "https://www.viewsonic.com/us/ls800hd.html")
        self.assertEqual(rec1["turl"], "https://t.bing.com/th?id=OIP.123")
        self.assertEqual(rec1["title"], "ViewSonic LS800HD Laser Projector")
        self.assertIn("5000 ANSI Lumens", rec1["desc"])

        rec2 = records[1]
        self.assertEqual(rec2["murl"], "https://m.media-amazon.com/images/I/71xyzLS800HD.jpg")
        self.assertEqual(rec2["title"], "ViewSonic LS800HD Projector Rear Ports")

    def test_criterion_c_strict_quoted_zero_results_triggers_retry(self):
        """
        Criterion C: Strict quoted query with zero valid records triggers exactly one controlled unquoted retry.
        """
        strict_query = '"ViewSonic LS800HD"'
        should_retry, unquoted = PlaywrightSearchEngine.should_attempt_unquoted_retry(strict_query, results_count=0)
        self.assertTrue(should_retry, "Should attempt retry when strict quoted query has 0 results")
        self.assertEqual(unquoted, "ViewSonic LS800HD")

        multi_quoted = '"ViewSonic" "LS800HD" official photo'
        should_retry2, unquoted2 = PlaywrightSearchEngine.should_attempt_unquoted_retry(multi_quoted, results_count=0)
        self.assertTrue(should_retry2)
        self.assertEqual(unquoted2, "ViewSonic LS800HD official photo")

    def test_criterion_d_strict_query_with_results_does_not_retry(self):
        """
        Criterion D: Strict query with valid results does NOT trigger retry.
        Also, unquoted queries with zero results do NOT trigger retry (no infinite expansion).
        """
        # When results > 0
        strict_query = '"ViewSonic LS800HD"'
        should_retry, unquoted = PlaywrightSearchEngine.should_attempt_unquoted_retry(strict_query, results_count=5)
        self.assertFalse(should_retry, "Must not retry when results > 0")
        self.assertIsNone(unquoted)

        # When query has no quotes and 0 results
        unquoted_query = 'ViewSonic LS800HD'
        should_retry_no_q, _ = PlaywrightSearchEngine.should_attempt_unquoted_retry(unquoted_query, results_count=0)
        self.assertFalse(should_retry_no_q, "Must not retry unquoted queries")

    def test_criterion_e_provenance_preserved(self):
        """
        Criterion E: Harvested candidates preserve complete provenance:
        query, original_query, retry_query, is_unquoted_retry, source_engine, rank, source_domain, thumbnail_url.
        """
        pq = PlannedQuery(
            query='"ViewSonic LS800HD"',
            query_family=QueryFamily.EXACT_PRODUCT,
            pass_stage=1,
            priority=0.95,
            target_evidence="exact_match",
            angle_tag="Front Reference",
            expected_information="Manufacturer hero image"
        )

        mock_page = MagicMock()
        # Mock _execute_bing_query to return empty on first call (strict), then 1 record on retry
        def side_effect(page, query_str, max_results, timeout_ms=6000):
            if '"' in query_str:
                return []
            return [{
                "murl": "https://www.viewsonic.com/images/ls800hd.jpg",
                "turl": "https://t.bing.com/th?id=123",
                "purl": "https://www.viewsonic.com/p/ls800hd",
                "title": "ViewSonic LS800HD Projector",
                "desc": "Official image"
            }]

        with patch.object(PlaywrightSearchEngine, '_execute_bing_query', side_effect=side_effect):
            with patch('playwright.sync_api.sync_playwright') as mock_pw:
                mock_browser = MagicMock()
                mock_context = MagicMock()
                mock_context.new_page.return_value = mock_page
                mock_browser.new_context.return_value = mock_context
                mock_pw.return_value.__enter__.return_value.chromium.launch.return_value = mock_browser

                results = PlaywrightSearchEngine.search_queries_batch([pq], max_results_per_query=4)

        self.assertEqual(len(results), 1)
        cand = results[0]
        self.assertEqual(cand["url"], "https://viewsonic.com/images/ls800hd.jpg")
        self.assertEqual(cand["thumbnail_url"], "https://t.bing.com/th?id=123")
        self.assertEqual(cand["source_domain"], "viewsonic.com")
        self.assertEqual(cand["source_page_url"], "https://www.viewsonic.com/p/ls800hd")
        self.assertEqual(cand["source_engine"], "bing_playwright")
        self.assertEqual(cand["original_query"], '"ViewSonic LS800HD"')
        self.assertEqual(cand["retry_query"], "ViewSonic LS800HD")
        self.assertTrue(cand["is_unquoted_retry"])
        self.assertEqual(cand["rank"], 1)
        self.assertEqual(cand["title"], "ViewSonic LS800HD Projector")

    def test_criterion_f_duplicate_image_urls_deduplicated(self):
        """
        Criterion F: Duplicate image URLs are deduplicated across queries.
        """
        pq1 = PlannedQuery(
            query="ViewSonic LS800HD",
            query_family=QueryFamily.EXACT_PRODUCT,
            pass_stage=1,
            priority=0.9,
            target_evidence="front",
            angle_tag="Front Reference",
            expected_information="Front view"
        )
        pq2 = PlannedQuery(
            query="ViewSonic LS800HD projector",
            query_family=QueryFamily.PRODUCT_VIEWPOINT,
            pass_stage=2,
            priority=0.8,
            target_evidence="side",
            angle_tag="Side Reference",
            expected_information="Side view"
        )

        same_murl = "https://www.viewsonic.com/images/hero.jpg"
        records_q1 = [{"murl": same_murl, "purl": "https://viewsonic.com", "turl": "", "title": "ViewSonic 1"}]
        records_q2 = [{"murl": same_murl, "purl": "https://viewsonic.com", "turl": "", "title": "ViewSonic 2"}]

        with patch.object(PlaywrightSearchEngine, '_execute_bing_query', side_effect=[records_q1, records_q2]):
            with patch('playwright.sync_api.sync_playwright') as mock_pw:
                mock_browser = MagicMock()
                mock_context = MagicMock()
                mock_context.new_page.return_value = MagicMock()
                mock_browser.new_context.return_value = mock_context
                mock_pw.return_value.__enter__.return_value.chromium.launch.return_value = mock_browser

                results = PlaywrightSearchEngine.search_queries_batch([pq1, pq2], max_results_per_query=4)

        self.assertEqual(len(results), 1, "Duplicate image URL must be deduplicated across queries")
        self.assertEqual(results[0]["url"], "https://viewsonic.com/images/hero.jpg")

if __name__ == '__main__':
    unittest.main()
