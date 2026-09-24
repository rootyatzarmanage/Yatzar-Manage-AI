/**
 * API Client Service for Uncertainty-Aware 2D-to-3D Reconstruction Backend.
 */

const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:5000';

/**
 * Executes V-LLM Geometric Uncertainty and Viewpoint Triage.
 * @param {Object} data - { image, product_title, product_sku }
 */
export async function triageProduct(data) {
  try {
    let response;
    if (data.image instanceof File || data.image instanceof Blob) {
      const formData = new FormData();
      formData.append('image', data.image);
      formData.append('product_title', data.product_title || data.name || '');
      formData.append('product_sku', data.product_sku || data.modelNumber || '');
      
      response = await fetch(`${API_BASE}/api/v1/triage`, {
        method: 'POST',
        body: formData,
      });
    } else {
      response = await fetch(`${API_BASE}/api/v1/triage`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          product_title: data.product_title || data.name,
          product_sku: data.product_sku || data.modelNumber,
          thumbnail: data.thumbnail || data.seed_image,
        }),
      });
    }

    if (!response.ok) {
      throw new Error(`Triage API error: ${response.statusText}`);
    }

    return await response.json();
  } catch (error) {
    console.error('Triage service error:', error);
    throw error;
  }
}

/**
 * Ingests seed image & queries to harvest candidate viewpoints with DINOv2 scoring & PCA mapping.
 * @param {Object} data - { seed_image, product_title, product_sku, target_queries, sourceUrls }
 */
export async function scrapeProductViews(data) {
  try {
    let response;
    if (data.seed_image instanceof File || data.image instanceof File) {
      const formData = new FormData();
      formData.append('image', data.seed_image || data.image);
      formData.append('product_title', data.product_title || data.name || '');
      formData.append('product_sku', data.product_sku || data.modelNumber || '');
      if (data.target_queries) {
        formData.append('target_queries', JSON.stringify(data.target_queries));
      }
      
      response = await fetch(`${API_BASE}/api/v1/scrape`, {
        method: 'POST',
        body: formData,
      });
    } else {
      response = await fetch(`${API_BASE}/api/v1/scrape`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          seed_image: data.thumbnail || data.seed_image,
          product_title: data.name || data.product_title,
          product_sku: data.modelNumber || data.product_sku,
          target_queries: data.target_queries,
          dynamic_urls: data.sourceUrls || data.dynamic_urls || [],
        }),
      });
    }

    if (!response.ok) {
      throw new Error(`Scrape API error: ${response.statusText}`);
    }

    return await response.json();
  } catch (error) {
    console.error('Scrape service error:', error);
    throw error;
  }
}

/**
 * Triggers a targeted multi-query cascade cycle for missing viewpoints & dimensions.
 * @param {Object} data - { seed_image, product_title, product_sku, cascade_query, cycle_number }
 */
export async function triggerCascade(data) {
  try {
    const response = await fetch(`${API_BASE}/api/v1/cascade`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        seed_image: data.thumbnail || data.seed_image,
        product_title: data.name || data.product_title || 'Product Asset',
        product_sku: data.modelNumber || data.product_sku || 'SKU-01',
        cascade_query: data.cascade_query || data.query,
        cycle_number: data.cycle_number || 2,
      }),
    });

    if (!response.ok) {
      throw new Error(`Cascade API error: ${response.statusText}`);
    }

    return await response.json();
  } catch (error) {
    console.error('Cascade service error:', error);
    throw error;
  }
}

/**
 * Fetches benchmark and in-progress catalog products.
 */
export async function getProducts() {
  try {
    const res = await fetch(`${API_BASE}/api/products`);
    if (!res.ok) throw new Error('Failed to fetch products');
    return await res.json();
  } catch (err) {
    console.error('Failed to get products:', err);
    return { success: false, products: [] };
  }
}

/**
 * Generates Procedural CAD CSG parameters.
 */
export async function generateCSG(product) {
  try {
    const res = await fetch(`${API_BASE}/api/csg/generate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(product),
    });
    return await res.json();
  } catch (err) {
    console.error('CSG generation error:', err);
    throw err;
  }
}
