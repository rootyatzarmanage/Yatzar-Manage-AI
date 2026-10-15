/**
 * API Client Service for Independent Background Research Jobs and Serialized Pixal3D Reconstruction Queue.
 */

const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:5000';

// ==========================================
// RESEARCH JOB APIS (CONCURRENT)
// ==========================================

/**
 * Explicitly starts or reattaches to an independent background research job for a product.
 * @param {Object} data - Product details { id, name, modelNumber, articleNumber, category, prompt, thumbnail, sourceUrls, target_queries }
 */
export async function startResearchJob(data) {
  try {
    let response;
    if (data.seed_image instanceof File || data.image instanceof File || data.imageFile instanceof File) {
      const formData = new FormData();
      formData.append('image', data.seed_image || data.image || data.imageFile);
      formData.append('product_title', data.product_title || data.name || '');
      formData.append('product_sku', data.product_sku || data.modelNumber || '');
      formData.append('product_id', data.product_id || data.id || '');
      formData.append('model_number', data.model_number || data.modelNumber || '');
      formData.append('article_number', data.article_number || data.articleNumber || '');
      formData.append('part_number', data.part_number || data.partNumber || '');
      formData.append('brand', data.brand || '');
      formData.append('category', data.category || 'General');
      formData.append('prompt', data.prompt || data.user_prompt || data.description || '');
      if (data.target_queries) {
        formData.append('target_queries', JSON.stringify(data.target_queries));
      }
      if (data.sourceUrls || data.dynamic_urls) {
        formData.append('sourceUrls', JSON.stringify(data.sourceUrls || data.dynamic_urls));
      }

      response = await fetch(`${API_BASE}/api/research/start`, {
        method: 'POST',
        body: formData,
      });
    } else {
      response = await fetch(`${API_BASE}/api/research/start`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          id: data.id || data.product_id,
          product_id: data.product_id || data.id,
          name: data.name || data.product_title,
          product_title: data.product_title || data.name,
          modelNumber: data.modelNumber || data.model_number,
          articleNumber: data.articleNumber || data.article_number,
          partNumber: data.partNumber || data.part_number,
          brand: data.brand || '',
          category: data.category || 'General',
          prompt: data.prompt || data.user_prompt || data.description || '',
          thumbnail: data.thumbnail || data.seed_image,
          seed_image: data.seed_image || data.thumbnail,
          target_queries: data.target_queries,
          sourceUrls: data.sourceUrls || data.dynamic_urls || [],
        }),
      });
    }

    if (!response.ok) {
      const err = await response.json().catch(() => ({}));
      throw new Error(err.error || `Research start failed: ${response.statusText}`);
    }

    return await response.json();
  } catch (error) {
    console.error('Start research error:', error);
    throw error;
  }
}

/**
 * Retrieves the current status, phase, progress, and results of a research job.
 * @param {string} productIdOrJobId
 */
export async function getResearchStatus(productIdOrJobId) {
  try {
    const res = await fetch(`${API_BASE}/api/research/status/${encodeURIComponent(productIdOrJobId)}`);
    if (!res.ok) {
      if (res.status === 404) return { success: false, status: 'NOT_FOUND' };
      throw new Error(`Failed to fetch research status: ${res.statusText}`);
    }
    return await res.json();
  } catch (error) {
    console.error('Get research status error:', error);
    return { success: false, status: 'ERROR', error: error.message };
  }
}

/**
 * Retrieves completed candidate results and best reference.
 * @param {string} productIdOrJobId
 */
export async function getResearchResults(productIdOrJobId) {
  try {
    const res = await fetch(`${API_BASE}/api/research/results/${encodeURIComponent(productIdOrJobId)}`);
    if (!res.ok) {
      if (res.status === 404) return { success: false, status: 'NOT_FOUND' };
      throw new Error(`Failed to fetch research results: ${res.statusText}`);
    }
    return await res.json();
  } catch (error) {
    console.error('Get research results error:', error);
    throw error;
  }
}

/**
 * Explicitly cancels an active research job.
 * @param {string} productIdOrJobId
 */
export async function cancelResearchJob(productIdOrJobId) {
  try {
    const res = await fetch(`${API_BASE}/api/research/cancel/${encodeURIComponent(productIdOrJobId)}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ reason: 'User cancelled' }),
    });
    return await res.json();
  } catch (error) {
    console.error('Cancel research error:', error);
    throw error;
  }
}

/**
 * Explicitly retries a failed or cancelled research job.
 * @param {string} productIdOrJobId
 */
export async function retryResearchJob(productIdOrJobId) {
  try {
    const res = await fetch(`${API_BASE}/api/research/retry/${encodeURIComponent(productIdOrJobId)}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
    });
    return await res.json();
  } catch (error) {
    console.error('Retry research error:', error);
    throw error;
  }
}

/**
 * Retrieves all active and recent research jobs across all products.
 */
export async function getActiveResearchJobs() {
  try {
    const res = await fetch(`${API_BASE}/api/research/jobs`);
    if (!res.ok) throw new Error('Failed to fetch active research jobs');
    return await res.json();
  } catch (error) {
    console.error('Get active research jobs error:', error);
    return { success: false, active_jobs: [], active_count: 0 };
  }
}

// Backward-compatible alias for scrapeProductViews
export const scrapeProductViews = async (data) => {
  const startRes = await startResearchJob(data);
  const jobId = startRes.job?.job_id || data.id;

  // Poll until terminal state
  let attempts = 0;
  while (attempts < 120) {
    await new Promise(r => setTimeout(r, 600));
    const statusRes = await getResearchStatus(jobId);
    if (statusRes.success && statusRes.job?.status === 'COMPLETED' && statusRes.results) {
      return statusRes.results;
    }
    if (statusRes.success && (statusRes.job?.status === 'FAILED' || statusRes.job?.status === 'CANCELLED')) {
      throw new Error(statusRes.job?.error || `Research job ended with ${statusRes.job?.status}`);
    }
    attempts++;
  }
  throw new Error('Research job polling timed out');
};

export const researchProductViews = scrapeProductViews;


// ==========================================
// RECONSTRUCTION QUEUE APIS (SERIALIZED)
// ==========================================

/**
 * Enqueues a 3D reconstruction request to the serialized Pixal3D single-slot GPU queue.
 * @param {Object} data - { reference_image, product_title, product_sku, product_id, engine }
 */
export async function queueReconstruction(data) {
  try {
    const response = await fetch(`${API_BASE}/api/reconstruct/queue`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        reference_image: data.reference_image || data.selected_reference || data.image || data.thumbnail,
        product_title: data.product_title || data.name || '',
        product_sku: data.product_sku || data.modelNumber || '',
        product_id: data.product_id || data.id || '',
        engine: data.engine || data.reconstruction_engine || 'Pixal3D',
      }),
    });

    if (!response.ok) {
      const err = await response.json().catch(() => ({}));
      throw new Error(err.error || `Reconstruction queue failed: ${response.statusText}`);
    }

    return await response.json();
  } catch (error) {
    console.error('Queue reconstruction error:', error);
    throw error;
  }
}

/**
 * Retrieves the status and queue position of a 3D reconstruction job.
 * @param {string} productIdOrJobId
 */
export async function getReconstructionStatus(productIdOrJobId) {
  try {
    const res = await fetch(`${API_BASE}/api/reconstruct/status/${encodeURIComponent(productIdOrJobId)}`);
    if (!res.ok) {
      if (res.status === 404) return { success: false, status: 'NOT_FOUND' };
      throw new Error(`Failed to fetch reconstruction status: ${res.statusText}`);
    }
    return await res.json();
  } catch (error) {
    console.error('Get reconstruction status error:', error);
    return { success: false, status: 'ERROR', error: error.message };
  }
}

/**
 * Retrieves the global GPU reconstruction queue status.
 */
export async function getReconstructionQueue() {
  try {
    const res = await fetch(`${API_BASE}/api/reconstruct/queue`);
    if (!res.ok) throw new Error('Failed to fetch reconstruction queue');
    return await res.json();
  } catch (error) {
    console.error('Get reconstruction queue error:', error);
    return { success: false, queued_count: 0, queue: [] };
  }
}

/**
 * Explicitly cancels a queued reconstruction job.
 * @param {string} productIdOrJobId
 */
export async function cancelReconstruction(productIdOrJobId) {
  try {
    const res = await fetch(`${API_BASE}/api/reconstruct/cancel/${encodeURIComponent(productIdOrJobId)}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
    });
    return await res.json();
  } catch (error) {
    console.error('Cancel reconstruction error:', error);
    throw error;
  }
}

// Backward-compatible alias for direct reconstruction
export const reconstruct3D = async (data) => {
  const queueRes = await queueReconstruction(data);
  const jobId = queueRes.job_id || data.product_id || data.id;

  // Poll until completed
  let attempts = 0;
  while (attempts < 120) {
    await new Promise(r => setTimeout(r, 400));
    const statusRes = await getReconstructionStatus(jobId);
    if (statusRes.success && statusRes.status === 'COMPLETED') {
      return statusRes;
    }
    if (statusRes.success && (statusRes.status === 'FAILED' || statusRes.status === 'CANCELLED')) {
      throw new Error(statusRes.job?.error || statusRes.error || `Reconstruction ended with ${statusRes.status}`);
    }
    attempts++;
  }
  throw new Error('Reconstruction polling timed out');
};


// ==========================================
// MISC / VALIDATION / TRIAGE APIS
// ==========================================

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

export async function validate3D(data) {
  try {
    const response = await fetch(`${API_BASE}/api/v1/validate-3d`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        model_url: data.model_url || data.modelUrl,
        model_path: data.model_path || data.modelPath,
      }),
    });

    if (!response.ok) {
      const err = await response.json().catch(() => ({}));
      throw new Error(err.error || `Validation failed: ${response.statusText}`);
    }

    return await response.json();
  } catch (error) {
    console.error('Validation API error:', error);
    throw error;
  }
}
