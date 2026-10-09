import os
import sys
import unittest

backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend"))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from services.identifier_policy import ProductIdentity, CanonicalProductIdentity, normalize_product_identity, extract_brand_or_manufacturer
from services.candidate_analyzer_service import (
    CandidateAnalyzerService,
    ProductMatch,
    CandidateType,
    Viewpoint,
    EvidenceValue
)
from services.query_planner import QueryPlanner


class TestRetrievalContaminationFixes(unittest.TestCase):

    # ------------------------------------------------------------------------
    # TEST 1: Sony Movie Poster Contamination (Query Self-Corroboration)
    # ------------------------------------------------------------------------
    def test_01_sony_movie_poster_query_contamination(self):
        """
        Query contains 'WH1000XM5/B' but candidate page is an unrelated movie poster.
        Candidate must NOT be classified as TARGET_PRODUCT and must not get high confidence.
        """
        sony_identity = normalize_product_identity(ProductIdentity(
            brand="Sony",
            product_name="WH-1000XM5 Wireless Noise Canceling Headphones",
            model_number="WH1000XM5/B",
            category="Over-Ear Headphones",
            official_domains=["sony.com", "electronics.sony.com"]
        ))
        analyzer = CandidateAnalyzerService(canonical_identity=sony_identity)

        cand = {
            "id": "c_movie_poster",
            "url": "https://ar.inspiredpencil.com/pictures-2023/ip-man-2010/poster.jpg",
            "source_page_url": "https://ar.inspiredpencil.com/pictures-2023/ip-man-2010",
            "source_domain": "inspiredpencil.com",
            "title": "Ip Man 2010 - High Res Wallpapers & Movie Posters",
            "snippet": "Download free Ip Man 2010 martial arts cinema gallery photos.",
            "query": 'site:electronics.sony.com "WH1000XM5/B"',
            "query_family": "official_model",
            "query_priority": 1.0,
            "target_evidence": "front",
            "branch_angle": "front"
        }

        res = analyzer.analyze_candidate(cand)
        self.assertNotEqual(res.product_match, ProductMatch.TARGET_PRODUCT,
                            "Query string must not self-corroborate an unrelated candidate as TARGET_PRODUCT")
        self.assertLess(res.product_match_confidence, 0.60,
                        "Confidence must remain low when candidate-owned metadata lacks product evidence")
        self.assertNotIn("query", res.evidence_sources,
                         "Query must never be listed in candidate evidence sources")
        self.assertEqual(res.retrieval_context.get("query"), 'site:electronics.sony.com "WH1000XM5/B"',
                         "Query should be preserved in retrieval_context for provenance only")

    # ------------------------------------------------------------------------
    # TEST 2: Sony Camera Price Chart Contamination (Viewpoint & Model Isolation)
    # ------------------------------------------------------------------------
    def test_02_sony_camera_price_chart_contamination(self):
        """
        Query requests official photo of WH1000XM5/B, but candidate is a camera price review.
        Must NOT be TARGET_PRODUCT.
        requested_viewpoint may be FRONT, but verified_viewpoint must NOT become FRONT without candidate evidence.
        """
        sony_identity = normalize_product_identity(ProductIdentity(
            brand="Sony",
            product_name="WH-1000XM5 Wireless Noise Canceling Headphones",
            model_number="WH1000XM5/B",
            category="Over-Ear Headphones",
            official_domains=["sony.com", "electronics.sony.com"]
        ))
        analyzer = CandidateAnalyzerService(canonical_identity=sony_identity)

        cand = {
            "id": "c_camera_chart",
            "url": "https://topcamerareview.com/images/sony_pricing_table.png",
            "source_page_url": "https://topcamerareview.com/sony-camera-prices/",
            "source_domain": "topcamerareview.com",
            "title": "SONY camera prices - Top Camera Review",
            "snippet": "Complete listing of Sony Alpha mirrorless camera retail pricing and discounts.",
            "query": '"Sony" "WH1000XM5/B" official photo',
            "query_family": "isolated_official",
            "query_priority": 0.9,
            "target_evidence": "front",
            "branch_angle": "front"
        }

        res = analyzer.analyze_candidate(cand)
        self.assertNotEqual(res.product_match, ProductMatch.TARGET_PRODUCT,
                            "Generic Sony camera page must not match WH1000XM5 headphones")
        self.assertEqual(res.requested_viewpoint, "FRONT",
                         "Requested viewpoint should reflect query intent")
        self.assertNotEqual(res.verified_viewpoint, Viewpoint.FRONT,
                            "verified_viewpoint must not become FRONT solely from query intent")
        self.assertEqual(res.verified_viewpoint, Viewpoint.UNKNOWN,
                         "Without candidate-owned viewpoint evidence, verified_viewpoint must be UNKNOWN")

    # ------------------------------------------------------------------------
    # TEST 3: Ergonomic Office Chair Brand Contamination
    # ------------------------------------------------------------------------
    def test_03_ergonomic_office_chair_brand_extraction(self):
        """
        Input has Product Name = 'Ergonomic Office Chair', Brand = absent.
        Brand must NOT be inferred as 'Ergonomic', and queries must not contain 'Ergonomic Ergonomic'.
        """
        extracted_brand = extract_brand_or_manufacturer("Ergonomic Office Chair", None)
        self.assertIsNone(extracted_brand, "Generic capitalized word 'Ergonomic' must not be inferred as brand")

        chair_identity = normalize_product_identity(ProductIdentity(
            product_name="Ergonomic Office Chair",
            brand=None,
            category="Office Furniture"
        ))
        self.assertIsNone(chair_identity.canonical_brand, "Canonical brand must be None when no explicit or verified brand exists")

        queries = QueryPlanner.plan(chair_identity)
        for q in queries:
            self.assertNotIn("Ergonomic Ergonomic", q.query,
                             f"Query text must not repeat brand/product token: {q.query}")

    # ------------------------------------------------------------------------
    # TEST 4: Wild Horse Contamination (Side Profile Query vs Irrelevant Page)
    # ------------------------------------------------------------------------
    def test_04_wild_horse_side_profile_contamination(self):
        """
        Query requests 'side profile', candidate is an article about wild horses.
        Must NOT be TARGET_PRODUCT and verified_viewpoint must NOT become LEFT/SIDE.
        """
        chair_identity = normalize_product_identity(ProductIdentity(
            product_name="Ergonomic Office Chair",
            brand=None,
            category="Office Furniture"
        ))
        analyzer = CandidateAnalyzerService(canonical_identity=chair_identity)

        cand = {
            "id": "c_horse",
            "url": "https://savethewildhorse.org/img/przewalski_horse_grazing.jpg",
            "source_page_url": "https://savethewildhorse.org/en/takhi-przewalskis-horse/",
            "source_domain": "savethewildhorse.org",
            "title": "Save the Wild Horse - Takhi, the Wild Horse of Mongolia",
            "snippet": "Conservation project protecting the last remaining wild horses in Mongolia.",
            "query": '"Ergonomic Office Chair" side profile',
            "query_family": "orthogonal_views",
            "query_priority": 0.8,
            "target_evidence": "left",
            "branch_angle": "left"
        }

        res = analyzer.analyze_candidate(cand)
        self.assertNotEqual(res.product_match, ProductMatch.TARGET_PRODUCT)
        self.assertNotEqual(res.verified_viewpoint, Viewpoint.LEFT,
                            "Candidate must not receive verified_viewpoint LEFT solely from query")
        self.assertEqual(res.verified_viewpoint, Viewpoint.UNKNOWN)
        self.assertFalse(res.reconstruction_evidence)

    # ------------------------------------------------------------------------
    # TEST 5: Jaguar Olive Leaf Contamination (Rear View Query vs Herbal Blog)
    # ------------------------------------------------------------------------
    def test_05_jaguar_olive_leaf_rear_contamination(self):
        """
        Query: 'Jaguar XE-SV-PROJECT8' rear view
        Candidate: Olive leaf extract blog
        Must NOT be TARGET_PRODUCT, must NOT have verified_viewpoint REAR, must NOT be HIGH evidence.
        """
        jaguar_identity = normalize_product_identity(ProductIdentity(
            brand="Jaguar",
            product_name="XE SV Project 8",
            model_number="XE-SV-PROJECT8",
            category="Automotive",
            official_domains=["jaguar.com"]
        ))
        analyzer = CandidateAnalyzerService(canonical_identity=jaguar_identity)

        cand = {
            "id": "c_olive_leaf",
            "url": "https://leryarrow.weebly.com/uploads/1/2/3/4/olive_leaf_supplement.jpg",
            "source_page_url": "https://leryarrow.weebly.com/blog/olive-leaf-extract",
            "source_domain": "leryarrow.weebly.com",
            "title": "Olive leaf extract benefits and dosage recommendations",
            "snippet": "Natural antioxidant supplement for cardiovascular health and wellness.",
            "query": '"Jaguar XE-SV-PROJECT8" rear view',
            "query_family": "orthogonal_views",
            "query_priority": 0.85,
            "target_evidence": "rear",
            "branch_angle": "rear"
        }

        res = analyzer.analyze_candidate(cand)
        self.assertNotEqual(res.product_match, ProductMatch.TARGET_PRODUCT)
        self.assertNotEqual(res.verified_viewpoint, Viewpoint.REAR,
                            "Candidate must not receive verified_viewpoint REAR solely from query")
        self.assertNotEqual(res.evidence_value, EvidenceValue.HIGH,
                            "Unrelated blog must not receive HIGH reconstruction evidence value")
        self.assertEqual(res.evidence_value, EvidenceValue.NONE)

    # ------------------------------------------------------------------------
    # TEST 6: Valid Positive Control (Genuine Candidate-Owned Evidence)
    # ------------------------------------------------------------------------
    def test_06_valid_positive_candidate_passes(self):
        """
        Genuine official candidate with correct product title and model number in candidate-owned metadata.
        Must be accepted as TARGET_PRODUCT with high confidence supported by candidate evidence.
        """
        sony_identity = normalize_product_identity(ProductIdentity(
            brand="Sony",
            product_name="WH-1000XM5 Wireless Noise Canceling Headphones",
            model_number="WH1000XM5/B",
            category="Over-Ear Headphones",
            official_domains=["sony.com", "electronics.sony.com"]
        ))
        analyzer = CandidateAnalyzerService(canonical_identity=sony_identity)

        cand = {
            "id": "c_sony_genuine",
            "url": "https://electronics.sony.com/media/wh1000xm5_black_front_hero.jpg",
            "source_page_url": "https://electronics.sony.com/audio/headphones/headband/p/wh1000xm5-b",
            "source_domain": "electronics.sony.com",
            "title": "Sony WH-1000XM5 Wireless Noise Canceling Headphones (Black) - WH1000XM5/B",
            "snippet": "Industry Leading Noise Canceling with 8 microphones and Auto NC Optimizer. High-Resolution Audio.",
            "alt": "Sony WH1000XM5/B headphones front view",
            "query": 'site:electronics.sony.com "WH1000XM5/B"',
            "query_family": "official_model",
            "query_priority": 1.0,
            "target_evidence": "front",
            "branch_angle": "front"
        }

        res = analyzer.analyze_candidate(cand)
        self.assertIn(res.product_match, [ProductMatch.TARGET_PRODUCT, ProductMatch.EXACT_ID_MATCH],
                      "Genuine candidate with matching title and model number must be TARGET_PRODUCT or EXACT_ID_MATCH")

        self.assertGreaterEqual(res.product_match_confidence, 0.90,
                                "Genuine candidate should have high confidence from candidate metadata")
        self.assertTrue(res.reconstruction_evidence)
        self.assertEqual(res.verified_viewpoint, Viewpoint.FRONT,
                         "Candidate alt text 'front view' should verify FRONT viewpoint")
        self.assertIn("brand_metadata", res.evidence_sources)
        self.assertIn("model_or_article_number", res.evidence_sources)

    # ------------------------------------------------------------------------
    # TEST 7: Product-Aware Component Queries
    # ------------------------------------------------------------------------
    def test_07_product_aware_component_queries(self):
        """
        Verify:
        - Sony WH-1000XM5 does NOT generate 'camera island' or 'camera ports' or 'bolt assembly'.
        - Phone generates camera module / charging port / buttons.
        - Industrial PLC generates DIN rail / terminal blocks / mounting.
        """
        # 1. Headphones
        sony_identity = normalize_product_identity(ProductIdentity(
            brand="Sony",
            product_name="WH-1000XM5 Wireless Noise Canceling Headphones",
            model_number="WH1000XM5/B",
            category="Over-Ear Headphones"
        ))
        sony_queries = QueryPlanner.plan(sony_identity)
        sony_query_texts = [q.query.lower() for q in sony_queries]

        for q in sony_query_texts:
            self.assertNotIn("camera island", q, "Headphones must not have camera island queries")
            self.assertNotIn("bolt assembly", q, "Headphones must not have bolt assembly queries")
            self.assertNotIn("exploded spare parts", q, "Headphones must not have exploded spare parts queries")

        # Verify headphones generated relevant audio component queries
        has_headphone_components = any(
            any(term in q for term in ["ear cup", "ear pad", "headband", "hinge", "charging port", "controls"])
            for q in sony_query_texts
        )
        self.assertTrue(has_headphone_components, "Headphones should generate relevant audio component queries")

        # 2. Smartphone
        phone_identity = normalize_product_identity(ProductIdentity(
            brand="Apple",
            product_name="iPhone 15 Pro",
            model_number="A3102",
            category="Smartphone"
        ))
        phone_queries = QueryPlanner.plan(phone_identity)
        phone_query_texts = [q.query.lower() for q in phone_queries]

        has_camera_query = any("camera module" in q or "camera island" in q for q in phone_query_texts)
        self.assertTrue(has_camera_query, "Smartphone should generate camera module / island queries")

        # 3. Industrial PLC
        plc_identity = normalize_product_identity(ProductIdentity(
            brand="Siemens",
            product_name="SIMATIC S7-1200 CPU 1214C",
            model_number="6ES7214-1AG40-0XB0",
            category="Industrial Automation"
        ))
        plc_queries = QueryPlanner.plan(plc_identity)
        plc_query_texts = [q.query.lower() for q in plc_queries]

        for q in plc_query_texts:
            self.assertNotIn("camera island", q, "Industrial PLC must not have camera queries")
            self.assertNotIn("ear cup", q, "Industrial PLC must not have headphone queries")

        has_plc_components = any(
            any(term in q for term in ["terminal block", "din rail", "interface ports", "mounting points", "flange", "housing"])
            for q in plc_query_texts
        )
        self.assertTrue(has_plc_components, "Industrial PLC should generate relevant technical / wiring queries")


if __name__ == "__main__":
    unittest.main()
