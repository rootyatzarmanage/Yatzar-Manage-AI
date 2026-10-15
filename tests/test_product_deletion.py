import unittest
import json
import sys
from pathlib import Path

# Add backend directory to path
backend_dir = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(backend_dir))

from app import app, PRODUCTS_DB
from services.job_manager import JOBS_CACHE_DIR
from services.reconstruction_service import MODELS_OUTPUT_DIR


class TestProductDeletion(unittest.TestCase):
    def setUp(self):
        self.app = app
        self.client = self.app.test_client()
        MODELS_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        JOBS_CACHE_DIR.mkdir(parents=True, exist_ok=True)

    def test_complete_product_deletion(self):
        test_prod_id = "TEST-DEL-999"
        safe_id = "TEST-DEL-999"

        # 1. Populate PRODUCTS_DB with the test product
        prod_meta = {
            "id": test_prod_id,
            "name": "Test Delete Item",
            "modelNumber": "SKU-DEL-999",
            "modelUrl": f"/api/models/{safe_id}_pixal3d_test_model.glb"
        }
        import app as app_module
        app_module.PRODUCTS_DB.append(prod_meta)

        # 2. Create mock stored files (GLBs and research cache)
        mock_glb_1 = MODELS_OUTPUT_DIR / f"{safe_id}_pixal3d_abc_1700000.glb"
        mock_glb_1.write_bytes(b"glTF mock binary content")

        mock_sku_glb = MODELS_OUTPUT_DIR / "SKU-DEL-999_pixal3d_test.glb"
        mock_sku_glb.write_bytes(b"glTF mock SKU content")

        mock_cache = JOBS_CACHE_DIR / f"research_{safe_id}.json"
        mock_cache.write_text(json.dumps({"product_id": test_prod_id, "status": "COMPLETED"}), encoding="utf-8")

        self.assertTrue(mock_glb_1.exists())
        self.assertTrue(mock_sku_glb.exists())
        self.assertTrue(mock_cache.exists())

        # 3. Call DELETE API endpoint
        response = self.client.delete(f"/api/products/{test_prod_id}")
        self.assertEqual(response.status_code, 200)

        data = response.get_json()
        self.assertTrue(data.get("success"))
        self.assertEqual(data.get("product_id"), test_prod_id)

        # 4. Verify physical asset destruction
        self.assertFalse(mock_glb_1.exists(), "Product ID GLB file should be completely unlinked")
        self.assertFalse(mock_sku_glb.exists(), "SKU GLB file should be completely unlinked")
        self.assertFalse(mock_cache.exists(), "Research cache file should be unlinked")

        # 5. Verify database purge
        remaining_ids = [p.get("id") for p in app_module.PRODUCTS_DB]
        self.assertNotIn(test_prod_id, remaining_ids)

    def test_delete_product_with_explicit_hints(self):
        test_prod_id = "HINT-DEL-888"
        
        # Create an orphan GLB that only the client knows the path/modelNumber to
        orphan_glb = MODELS_OUTPUT_DIR / "orphan_custom_model_888.glb"
        orphan_glb.write_bytes(b"glTF orphan content")
        self.assertTrue(orphan_glb.exists())

        response = self.client.delete(
            f"/api/products/{test_prod_id}",
            json={
                "modelNumber": "NON-EXISTENT",
                "modelUrl": "/api/models/orphan_custom_model_888.glb"
            }
        )
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertTrue(data.get("success"))
        self.assertIn("orphan_custom_model_888.glb", data.get("deleted_models", []))
        self.assertFalse(orphan_glb.exists(), "Explicitly referenced modelUrl should be unlinked")


if __name__ == "__main__":
    unittest.main()
