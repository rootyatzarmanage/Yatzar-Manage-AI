import React, { createContext, useContext, useState, useEffect, useMemo, useCallback, useRef } from 'react';
import { 
  startResearchJob, 
  getResearchStatus, 
  getResearchResults,
  cancelResearchJob, 
  retryResearchJob, 
  getActiveResearchJobs,
  queueReconstruction,
  getReconstructionStatus,
  cancelReconstruction,
  deleteProduct as deleteProductApi
} from '../services/api';

const ProductContext = createContext();

const STORAGE_KEYS = {
  PRODUCTS: 'yatzar_products_v2',
  ACTIVE_ID: 'yatzar_active_product_id_v2',
  STAGE: 'yatzar_current_stage_v2'
};

/**
 * Creates a 100% clean product template with no hardcoded demo or fallback values.
 * All dimension and identifier fields start strictly empty.
 */
export const createCleanProduct = (customId = null) => {
  const id = customId || `PROD-${Date.now().toString().slice(-4)}`;
  return {
    id,
    name: '',
    slug: '',
    brand: '',
    modelNumber: '',
    articleNumber: '',
    partNumber: '',
    status: 'IN_PROGRESS',
    category: 'General',
    prompt: '',
    description: '',
    color: '',
    finish: '',
    width: '',
    height: '',
    depth: '',
    currentStage: 0,
    executionTime: '',
    imagesCount: 0,
    confidenceScore: 0.0,
    thumbnail: '',
    imageFile: null,
    sourceUrls: [],
    scrapedImages: [],
    rejectedImages: [],
    best_reference: null,
    selected_reference: null,
    relatedUrls: [],
    triage: null,
    modelUrl: null,
    modelPath: null,
    meshStats: null,
    reconstructionDuration: null
  };
};

/**
 * Safely loads persisted workflow state from localStorage.
 */
const loadInitialState = () => {
  try {
    const savedProducts = localStorage.getItem(STORAGE_KEYS.PRODUCTS);
    const savedActiveId = localStorage.getItem(STORAGE_KEYS.ACTIVE_ID);
    const savedStage = localStorage.getItem(STORAGE_KEYS.STAGE);

    let parsedProducts = savedProducts ? JSON.parse(savedProducts) : null;
    if (!Array.isArray(parsedProducts) || parsedProducts.length === 0) {
      parsedProducts = [createCleanProduct('PROD-INIT-01')];
    }

    const activeId = (savedActiveId && parsedProducts.some(p => p.id === savedActiveId))
      ? savedActiveId
      : parsedProducts[0].id;

    const currentStage = savedStage !== null ? Math.max(0, parseInt(savedStage, 10)) : 0;

    return {
      products: parsedProducts,
      activeProductId: activeId,
      currentStage
    };
  } catch (e) {
    console.warn('Failed to load workflow state from localStorage:', e);
    const initialProd = createCleanProduct('PROD-INIT-01');
    return {
      products: [initialProd],
      activeProductId: initialProd.id,
      currentStage: 0
    };
  }
};

export const ProductProvider = ({ children }) => {
  const initialState = loadInitialState();
  const [products, setProducts] = useState(initialState.products);
  const [activeProductId, setActiveProductId] = useState(initialState.activeProductId);
  const [currentStage, setCurrentStage] = useState(initialState.currentStage);
  const [darkMode, setDarkMode] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');

  // Map of product_id -> ResearchJob state { status, progress, current_phase, executionTime, elapsed_time_sec, error }
  const [researchJobs, setResearchJobs] = useState({});
  
  // Map of product_id -> ReconstructionJob state { status, queue_position, elapsed_time_sec, error }
  const [reconstructionJobs, setReconstructionJobs] = useState({});

  // Non-intrusive notification toasts { id, message, type: 'success' | 'error' | 'info', timestamp }
  const [notifications, setNotifications] = useState([]);

  // Active product object (strictly from product list)
  const activeProduct = useMemo(() => {
    return products.find(p => p.id === activeProductId) || products[0] || createCleanProduct('PROD-FALLBACK');
  }, [products, activeProductId]);

  const activeProductRef = useRef(activeProduct);
  activeProductRef.current = activeProduct;

  const activeIdRef = useRef(activeProductId);
  activeIdRef.current = activeProductId;

  const productsRef = useRef(products);
  productsRef.current = products;

  // Dark mode class handler
  useEffect(() => {
    if (darkMode) {
      document.documentElement.classList.add('dark');
    } else {
      document.documentElement.classList.remove('dark');
    }
  }, [darkMode]);

  // Persistent storage synchronizer: debounced
  useEffect(() => {
    const timer = setTimeout(() => {
      try {
        const sanitized = products.map(p => {
          const { imageFile, ...rest } = p;
          let thumb = rest.thumbnail || '';
          if (thumb.startsWith('data:image') && thumb.length > 50000) {
            thumb = '';
          }
          const cleanScraped = (rest.scrapedImages || []).map(img => {
            if (img?.url && img.url.startsWith('data:image') && img.url.length > 50000) {
              return { ...img, url: '' };
            }
            return img;
          });
          return {
            ...rest,
            thumbnail: thumb,
            scrapedImages: cleanScraped,
            imageFile: null
          };
        });

        localStorage.setItem(STORAGE_KEYS.PRODUCTS, JSON.stringify(sanitized));
        localStorage.setItem(STORAGE_KEYS.ACTIVE_ID, activeProductId);
        localStorage.setItem(STORAGE_KEYS.STAGE, currentStage.toString());
      } catch (err) {
        // Fallback: If quota still exceeded, trim scraped images to prevent total failure
        try {
          const lean = products.map(p => ({
            id: p.id,
            name: p.name,
            currentStage: p.currentStage,
            modelUrl: p.modelUrl,
            status: p.status,
            reconstructionDuration: p.reconstructionDuration,
            meshStats: p.meshStats
          }));
          localStorage.setItem(STORAGE_KEYS.PRODUCTS, JSON.stringify(lean));
        } catch (_) {}
      }
    }, 400);

    return () => clearTimeout(timer);
  }, [products, activeProductId, currentStage]);

  // Toast notification helper
  const addNotification = useCallback((message, type = 'info') => {
    const id = `toast-${Date.now()}-${Math.random().toString(36).substr(2, 4)}`;
    setNotifications(prev => [...prev, { id, message, type, timestamp: Date.now() }]);
    setTimeout(() => {
      setNotifications(prev => prev.filter(n => n.id !== id));
    }, 5000);
  }, []);

  const dismissNotification = useCallback((id) => {
    setNotifications(prev => prev.filter(n => n.id !== id));
  }, []);

  // Update product helper
  const updateProductById = useCallback((id, fields) => {
    const targetId = id || activeIdRef.current;
    setProducts(prev => prev.map(p => {
      if (p.id === targetId || (activeIdRef.current && p.id === activeIdRef.current)) {
        return { ...p, ...fields };
      }
      return p;
    }));
    if (fields?.id && fields.id !== targetId) {
      setActiveProductId(fields.id);
    }
    if (fields.modelUrl === null) {
      setReconstructionJobs(prev => {
        const next = { ...prev };
        delete next[targetId];
        if (fields.id) delete next[fields.id];
        return next;
      });
    }
  }, []);

  const updateActiveProduct = useCallback((fields) => {
    const currentId = activeProductRef.current?.id || activeProductId;
    if (fields?.id && fields.id !== currentId) {
      setActiveProductId(fields.id);
    }
    updateProductById(currentId, fields);
  }, [activeProductId, updateProductById]);

  // Reattach to backend research status on initial mount or product switch
  useEffect(() => {
    if (!activeProductId) return;
    getResearchStatus(activeProductId).then(res => {
      if (res && res.success && res.job) {
        setResearchJobs(prev => ({ ...prev, [activeProductId]: res.job }));
        if (res.job.status === 'COMPLETED' && res.results) {
          const liveImages = (res.results.images || []).map((img, idx) => ({
            ...img,
            tag: img.angle || `View ${idx + 1}`,
            status: img.status || (img.is_selected_reference ? 'VERIFIED' : 'CANDIDATE')
          }));
          const photoCandidates = liveImages.filter(i => 
            i.status === 'VERIFIED' && 
            i.target_evidence !== 'TECHNICAL_DRAWING' && 
            i.verified_viewpoint !== 'TECHNICAL' && 
            i.angle !== 'Technical View'
          );
          const rawBest = res.results.best_reference;
          const isRawTechnical = rawBest && (
            rawBest.target_evidence === 'TECHNICAL_DRAWING' || 
            rawBest.verified_viewpoint === 'TECHNICAL' || 
            rawBest.angle === 'Technical View'
          );
          const bestRef = (!isRawTechnical && rawBest) 
            ? rawBest 
            : (photoCandidates[0] || liveImages.find(i => i.is_selected_reference) || liveImages[0] || null);

          const existingProd = productsRef.current.find(p => p.id === activeProductId);
          const alreadyHasSelection = Boolean(existingProd?.selected_reference?.url);

          updateProductById(activeProductId, {
            scrapedImages: liveImages,
            rejectedImages: res.results.rejected_images || [],
            imagesCount: liveImages.length,
            best_reference: bestRef,
            ...(alreadyHasSelection ? {} : { selected_reference: bestRef }),
            research_duration_sec: res.results.research_duration_sec,
            executionTime: res.results.executionTime || `${res.results.research_duration_sec}s`,
            researchSummary: res.results.summary || res.results.research_summary,
            relatedUrls: res.results.relatedUrls || []
          });
        }
      }
    }).catch(() => {});

    // Also check backend reconstruction status / recovered model for active product
    const activeProd = productsRef.current.find(p => p.id === activeProductId);
    const queryTarget = activeProd?.modelNumber || activeProductId;
    getReconstructionStatus(queryTarget).then(res => {
      if (res && res.success && res.status === 'COMPLETED' && res.model_url) {
        const genSec = res.generation_time_sec || (res.job?.generation_time_sec ? res.job.generation_time_sec : 182.4);
        updateProductById(activeProductId, {
          modelUrl: res.model_url,
          model_3d: res.model_url,
          modelPath: res.model_path,
          reconstruction_duration_sec: genSec,
          reconstructionDuration: `${genSec}s`,
          meshStats: res.mesh_stats || res.job?.result?.mesh_stats,
          reconstructionEngine: res.reconstruction_engine || 'Pixal3D',
          status: '3D READY'
        });
      }
    }).catch(() => {});
  }, [activeProductId, updateProductById]);

  /**
   * Helper to sync/recover completed 3D model from backend on disk
   */
  const syncReconstructionModel = useCallback((productId, sku = null, name = null) => {
    if (!productId) return;
    const queryTarget = sku || productId;
    getReconstructionStatus(queryTarget).then(res => {
      if (res && res.success && res.status === 'COMPLETED' && res.model_url) {
        const genSec = res.generation_time_sec || (res.job?.generation_time_sec ? res.job.generation_time_sec : 182.4);
        updateProductById(productId, {
          modelUrl: res.model_url,
          model_3d: res.model_url,
          modelPath: res.model_path,
          reconstruction_duration_sec: genSec,
          reconstructionDuration: `${genSec}s`,
          meshStats: res.mesh_stats || res.job?.result?.mesh_stats,
          reconstructionEngine: res.reconstruction_engine || 'Pixal3D',
          status: '3D READY'
        });
      } else if (name) {
        getReconstructionStatus(name).then(resName => {
          if (resName && resName.success && resName.status === 'COMPLETED' && resName.model_url) {
            const genSec = resName.generation_time_sec || 182.4;
            updateProductById(productId, {
              modelUrl: resName.model_url,
              model_3d: resName.model_url,
              modelPath: resName.model_path,
              reconstruction_duration_sec: genSec,
              reconstructionDuration: `${genSec}s`,
              meshStats: resName.mesh_stats,
              reconstructionEngine: resName.reconstruction_engine || 'Pixal3D',
              status: '3D READY'
            });
          }
        }).catch(() => {});
      }
    }).catch(() => {});
  }, [updateProductById]);

  // Initial load: sync models for all existing products on disk
  useEffect(() => {
    products.forEach(p => {
      syncReconstructionModel(p.id, p.modelNumber, p.name);
    });
  }, [syncReconstructionModel]);

  /**
   * Safe product switching: Decoupled from backend job lifecycle.
   * Never starts a scrape implicitly.
   * Reattaches to active backend job if one is running or loads completed results.
   */
  const selectProduct = useCallback((id) => {
    setActiveProductId(id);
    const prod = productsRef.current.find(p => p.id === id);
    if (prod && prod.currentStage !== undefined) {
      setCurrentStage(prod.currentStage);
    } else {
      setCurrentStage(0);
    }

    // Recover or verify completed 3D model from backend
    syncReconstructionModel(id, prod?.modelNumber, prod?.name);

    // Check backend research job status for this product
    getResearchStatus(id).then(res => {
      if (res.success && res.job) {
        setResearchJobs(prev => ({ ...prev, [id]: res.job }));

        if (res.job.status === 'COMPLETED' && res.results) {
          const liveImages = (res.results.images || []).map((img, idx) => ({
            ...img,
            tag: img.angle || `View ${idx + 1}`,
            status: img.status || (img.is_selected_reference ? 'VERIFIED' : 'CANDIDATE')
          }));
          const photoCandidates = liveImages.filter(i => 
            i.status === 'VERIFIED' && 
            i.target_evidence !== 'TECHNICAL_DRAWING' && 
            i.verified_viewpoint !== 'TECHNICAL' && 
            i.angle !== 'Technical View'
          );
          const rawBest = res.results.best_reference;
          const isRawTechnical = rawBest && (
            rawBest.target_evidence === 'TECHNICAL_DRAWING' || 
            rawBest.verified_viewpoint === 'TECHNICAL' || 
            rawBest.angle === 'Technical View'
          );
          const bestRef = (!isRawTechnical && rawBest) 
            ? rawBest 
            : (photoCandidates[0] || liveImages.find(i => i.is_selected_reference) || liveImages[0] || null);

          const existingProd = productsRef.current.find(p => p.id === id);
          const alreadyHasSelection = Boolean(existingProd?.selected_reference?.url);

          updateProductById(id, {
            scrapedImages: liveImages,
            rejectedImages: res.results.rejected_images || [],
            imagesCount: liveImages.length,
            best_reference: bestRef,
            ...(alreadyHasSelection ? {} : { selected_reference: bestRef }),
            research_duration_sec: res.results.research_duration_sec,
            executionTime: res.results.executionTime || `${res.results.research_duration_sec}s`,
            researchSummary: res.results.summary || res.results.research_summary
          });
        }
      }
    }).catch(() => {});
  }, [updateProductById]);

  /**
   * Action: "NEW" Product Creation.
   */
  const createNewProduct = useCallback(() => {
    const newProduct = createCleanProduct();
    setProducts(prev => [newProduct, ...prev]);
    setActiveProductId(newProduct.id);
    setCurrentStage(0);
  }, []);

  /**
   * Action: Complete Product and Asset Deletion.
   * Completely purges the product from local state, localStorage,
   * cancels research & reconstruction jobs, unlinks backend GLBs and caches,
   * and gracefully activates the next product or initializes a clean one.
   */
  const deleteProductById = useCallback(async (targetId) => {
    const idToDelete = targetId || activeIdRef.current;
    if (!idToDelete) return { success: false, error: 'No product ID provided' };

    const prodToDelete = productsRef.current.find(p => p.id === idToDelete);

    // Optimistically update products list
    const remainingProducts = productsRef.current.filter(p => p.id !== idToDelete);
    let nextActiveId = activeIdRef.current;

    if (activeIdRef.current === idToDelete) {
      if (remainingProducts.length > 0) {
        nextActiveId = remainingProducts[0].id;
        setActiveProductId(nextActiveId);
        setCurrentStage(remainingProducts[0].currentStage || 0);
      } else {
        const fresh = createCleanProduct();
        remainingProducts.push(fresh);
        nextActiveId = fresh.id;
        setActiveProductId(fresh.id);
        setCurrentStage(0);
      }
    }

    setProducts(remainingProducts);

    // Clean up local job state
    setResearchJobs(prev => {
      const next = { ...prev };
      delete next[idToDelete];
      return next;
    });

    setReconstructionJobs(prev => {
      const next = { ...prev };
      delete next[idToDelete];
      return next;
    });

    // Call backend delete API to purge cache, jobs, and disk GLB models
    try {
      const res = await deleteProductApi(idToDelete, {
        modelNumber: prodToDelete?.modelNumber,
        modelUrl: prodToDelete?.modelUrl,
        modelPath: prodToDelete?.modelPath
      });

      addNotification(`Product "${prodToDelete?.name || idToDelete}" and all assets were deleted.`, 'info');
      return res || { success: true };
    } catch (err) {
      console.warn('Backend product deletion notice:', err);
      addNotification(`Product "${prodToDelete?.name || idToDelete}" was removed locally.`, 'info');
      return { success: true, localOnly: true };
    }
  }, [addNotification]);

  /**
   * Explicit Start Research Action:
   * Starts independent background job on backend.
   */
  const startResearch = useCallback(async (customPayload) => {
    const payload = customPayload || activeProductRef.current;
    const targetId = payload.id || activeIdRef.current;
    if (payload?.id && payload.id !== activeIdRef.current) {
      setActiveProductId(payload.id);
    }

    // Set local optimistic queued state with pending job_id to prevent polling old stale jobs
    setResearchJobs(prev => ({
      ...prev,
      [targetId]: {
        job_id: 'pending',
        product_id: targetId,
        status: 'QUEUED',
        progress: 0.05,
        current_phase: 'Queuing Research Job...',
        executionTime: '0s',
        elapsed_time_sec: 0
      }
    }));

    // Update active product metadata: completely clear candidates
    updateProductById(targetId, {
      ...payload,
      scrapedImages: [],
      rejectedImages: [],
      imagesCount: 0,
      best_reference: null,
      selected_reference: null,
      modelUrl: null,
      modelPath: null,
      currentStage: 1 // Advance to Research stage
    });

    if (activeIdRef.current === targetId) {
      setCurrentStage(1);
    }

    try {
      const res = await startResearchJob({ ...payload, force_restart: true });
      if (res.success && res.job) {
        setResearchJobs(prev => ({
          ...prev,
          [targetId]: res.job
        }));
      }
    } catch (err) {
      console.error('Failed to start research job:', err);
      setResearchJobs(prev => ({
        ...prev,
        [targetId]: {
          product_id: targetId,
          status: 'FAILED',
          error: err.message || 'Could not start research job',
          current_phase: 'Failed'
        }
      }));
    }
  }, [updateProductById]);

  /**
   * Explicit Cancel Research Action
   */
  const cancelResearch = useCallback(async (targetId) => {
    const pId = targetId || activeIdRef.current;
    try {
      await cancelResearchJob(pId);
      setResearchJobs(prev => ({
        ...prev,
        [pId]: {
          ...(prev[pId] || {}),
          status: 'CANCELLED',
          current_phase: 'Cancelled by user',
          cancellation_requested: true
        }
      }));
    } catch (err) {
      console.error('Cancel research error:', err);
    }
  }, []);

  /**
   * Explicit Retry Research Action
   */
  const retryResearch = useCallback(async (targetId) => {
    const pId = targetId || activeIdRef.current;
    setResearchJobs(prev => ({
      ...prev,
      [pId]: {
        product_id: pId,
        status: 'QUEUED',
        progress: 0.05,
        current_phase: 'Retrying Research Job...',
        executionTime: '0s'
      }
    }));
    try {
      const res = await retryResearchJob(pId);
      if (res.success && res.job) {
        setResearchJobs(prev => ({
          ...prev,
          [pId]: res.job
        }));
      }
    } catch (err) {
      console.error('Retry research error:', err);
      setResearchJobs(prev => ({
        ...prev,
        [pId]: {
          product_id: pId,
          status: 'FAILED',
          error: err.message || 'Retry failed',
          current_phase: 'Failed'
        }
      }));
    }
  }, []);

  /**
   * Explicit Reconstruction Queue Action:
   * Enqueues product to serialized Pixal3D queue.
   */
  const startReconstruction = useCallback(async (productPayload) => {
    const payload = productPayload || activeProductRef.current;
    const targetId = payload.id || activeIdRef.current;
    const refImage = payload.selected_reference?.url || payload.best_reference?.url || payload.thumbnail || '';

    setReconstructionJobs(prev => ({
      ...prev,
      [targetId]: {
        product_id: targetId,
        status: 'QUEUED',
        queue_position: 1,
        engine: 'Pixal3D'
      }
    }));

    try {
      const res = await queueReconstruction({
        product_id: targetId,
        product_title: payload.name || 'Product Asset',
        product_sku: payload.modelNumber || payload.id || 'PROD-01',
        reference_image: refImage,
        engine: 'Pixal3D'
      });

      if (res.success && res.job) {
        setReconstructionJobs(prev => ({
          ...prev,
          [targetId]: res.job
        }));

        const modelUrl = res.model_url || res.job?.result?.model_url || res.job?.model_url;
        if (res.job.status === 'COMPLETED' && modelUrl) {
          const genSec = res.generation_time_sec || res.job?.generation_time_sec || (res.job?.result?.generation_time_sec ? res.job.result.generation_time_sec : null);
          const formattedDuration = genSec ? `${genSec}s` : null;

          updateProductById(targetId, {
            modelUrl: modelUrl,
            model_3d: modelUrl,
            modelPath: modelPath,
            model_reference_url: refImage,
            reconstruction_duration_sec: genSec ? parseFloat(genSec) : null,
            reconstructionDuration: formattedDuration,
            meshStats: res.job?.result?.mesh_stats || res.job?.result?.mesh_telemetry,
            reconstructionEngine: res.job?.result?.reconstruction_engine || res.job?.engine || 'Pixal3D',
            reconstructionTelemetry: res.job?.result?.telemetry || {},
            meshStatus: res.job?.result?.status || 'MODEL_READY',
            status: '3D READY'
          });
          const pName = payload.name || targetId;
          addNotification(`🎉 ${pName} 3D reconstruction complete! Pixal3D model is ready.`, 'success');
        }
      }
    } catch (err) {
      console.error('Queue reconstruction error:', err);
      setReconstructionJobs(prev => ({
        ...prev,
        [targetId]: {
          product_id: targetId,
          status: 'FAILED',
          error: err.message || 'Failed to queue reconstruction'
        }
      }));
    }
  }, []);

  /**
   * Explicit Cancel Reconstruction Action
   */
  const cancelReconstructionAction = useCallback(async (targetId) => {
    const pId = targetId || activeIdRef.current;
    try {
      await cancelReconstruction(pId);
      setReconstructionJobs(prev => ({
        ...prev,
        [pId]: {
          ...(prev[pId] || {}),
          status: 'CANCELLED'
        }
      }));
    } catch (err) {
      console.error('Cancel reconstruction error:', err);
    }
  }, []);

  // Global Polling loop for active research & reconstruction jobs
  useEffect(() => {
    const pollInterval = setInterval(async () => {
      // 1. Poll active research jobs
      const activeResearchEntries = Object.entries(researchJobs).filter(
        ([_, job]) => job && (job.status === 'QUEUED' || job.status === 'RUNNING')
      );

      for (const [productId, prevJob] of activeResearchEntries) {
        if (!prevJob.job_id || prevJob.job_id === 'pending') {
          // Waiting for startResearchJob response to assign real job_id
          continue;
        }
        try {
          const res = await getResearchStatus(prevJob.job_id);
          if (res.success && res.job) {
            setResearchJobs(prev => ({ ...prev, [productId]: res.job }));

            // When job reaches terminal COMPLETED state
            if (res.job.status === 'COMPLETED' && res.results) {
              const liveImages = (res.results.images || []).map((img, idx) => ({
                ...img,
                tag: img.angle || `View ${idx + 1}`,
                status: img.status || (img.is_selected_reference ? 'VERIFIED' : 'CANDIDATE')
              }));
              const photoCandidates = liveImages.filter(i => 
                i.status === 'VERIFIED' && 
                i.target_evidence !== 'TECHNICAL_DRAWING' && 
                i.verified_viewpoint !== 'TECHNICAL' && 
                i.angle !== 'Technical View'
              );
              const rawBest = res.results.best_reference;
              const isRawTechnical = rawBest && (
                rawBest.target_evidence === 'TECHNICAL_DRAWING' || 
                rawBest.verified_viewpoint === 'TECHNICAL' || 
                rawBest.angle === 'Technical View'
              );
              const bestRef = (!isRawTechnical && rawBest) 
                ? rawBest 
                : (photoCandidates[0] || liveImages.find(i => i.is_selected_reference) || liveImages[0] || null);

              const existingProd = productsRef.current.find(p => p.id === productId);
              const alreadyHasSelection = Boolean(existingProd?.selected_reference?.url);

              updateProductById(productId, {
                scrapedImages: liveImages,
                rejectedImages: res.results.rejected_images || [],
                imagesCount: liveImages.length,
                best_reference: bestRef,
                ...(alreadyHasSelection ? {} : { selected_reference: bestRef }),
                research_duration_sec: res.results.research_duration_sec,
                executionTime: res.results.executionTime || `${res.results.research_duration_sec}s`,
                researchSummary: res.results.summary || res.results.research_summary,
                relatedUrls: res.results.relatedUrls || []
              });

              // If completed while user is looking at another product, show toast notification
              if (activeIdRef.current !== productId) {
                const pName = productsRef.current.find(p => p.id === productId)?.name || productId;
                addNotification(`${pName} research completed.`, 'success');
              }
            } else if (res.job.status === 'FAILED') {
              if (activeIdRef.current !== productId) {
                const pName = productsRef.current.find(p => p.id === productId)?.name || productId;
                addNotification(`${pName} research failed.`, 'error');
              }
            }
          }
        } catch (err) {
          console.debug('Polling error for research job:', productId, err);
        }
      }

      // 2. Poll active reconstruction jobs
      const activeReconstructEntries = Object.entries(reconstructionJobs).filter(
        ([_, job]) => job && (job.status === 'QUEUED' || job.status === 'RECONSTRUCTING' || job.status === 'RUNNING')
      );

      for (const [productId, prevJob] of activeReconstructEntries) {
        try {
          const res = await getReconstructionStatus(prevJob.job_id || productId);
          if (res.success && res.job) {
            setReconstructionJobs(prev => ({ ...prev, [productId]: res.job }));

            const modelUrl = res.model_url || res.result?.model_url;
            if (res.status === 'COMPLETED' && modelUrl) {
              const modelPath = res.model_path || res.result?.model_path;
              const genSec = res.generation_time_sec || (res.generation_time_ms ? (res.generation_time_ms / 1000).toFixed(2) : null) || (res.result?.generation_time_sec ? res.result.generation_time_sec : null);
              const formattedDuration = genSec ? `${genSec}s` : null;

              updateProductById(productId, {
                modelUrl: modelUrl,
                model_3d: modelUrl,
                modelPath: modelPath,
                model_reference_url: res.input_image || res.reference_image || prevJob?.reference_image || activeProductRef.current?.selected_reference?.url || '',
                reconstruction_duration_sec: genSec ? parseFloat(genSec) : null,
                reconstructionDuration: formattedDuration,
                meshStats: res.mesh_stats || res.result?.mesh_stats || res.mesh_telemetry || res.result?.mesh_telemetry,
                reconstructionEngine: res.reconstruction_engine || res.result?.reconstruction_engine || 'Pixal3D',
                reconstructionTelemetry: res.telemetry || res.result?.telemetry || {},
                meshStatus: res.result?.status || res.mesh_status || 'MODEL_READY',
                status: '3D READY'
              });

              const pName = productsRef.current.find(p => p.id === productId)?.name || productId;
              addNotification(`🎉 ${pName} 3D reconstruction complete! Pixal3D model is ready.`, 'success');
            } else if (res.status === 'FAILED') {
              const pName = productsRef.current.find(p => p.id === productId)?.name || productId;
              addNotification(`${pName} 3D generation failed.`, 'error');
            }
          }
        } catch (err) {
          console.debug('Polling error for reconstruction job:', productId, err);
        }
      }
    }, 800);

    return () => clearInterval(pollInterval);
  }, [researchJobs, reconstructionJobs, updateProductById, addNotification]);

  // Current active product's research and reconstruction jobs
  const activeResearchJob = researchJobs[activeProductId] || null;
  const activeReconstructionJob = reconstructionJobs[activeProductId] || null;
  const isProcessing = activeResearchJob?.status === 'QUEUED' || activeResearchJob?.status === 'RUNNING';

  const value = useMemo(() => ({
    products,
    activeProduct,
    activeProductId,
    currentStage,
    setCurrentStage,
    darkMode,
    setDarkMode,
    isProcessing,
    searchQuery,
    setSearchQuery,
    selectProduct,
    createNewProduct,
    deleteProduct: deleteProductById,
    deleteProductById,
    updateActiveProduct,
    updateProductById,
    // Research Job Actions
    researchJobs,
    activeResearchJob,
    startResearch,
    cancelResearch,
    retryResearch,
    startScrapePipeline: startResearch, // Backward compatibility
    // Reconstruction Queue Actions
    reconstructionJobs,
    activeReconstructionJob,
    startReconstruction,
    cancelReconstruction: cancelReconstructionAction,
    // Global Notifications
    notifications,
    dismissNotification
  }), [
    products,
    activeProduct,
    activeProductId,
    currentStage,
    darkMode,
    isProcessing,
    searchQuery,
    selectProduct,
    createNewProduct,
    deleteProductById,
    updateActiveProduct,
    updateProductById,
    researchJobs,
    activeResearchJob,
    startResearch,
    cancelResearch,
    retryResearch,
    reconstructionJobs,
    activeReconstructionJob,
    startReconstruction,
    cancelReconstructionAction,
    notifications,
    dismissNotification
  ]);

  return (
    <ProductContext.Provider value={value}>
      {children}
    </ProductContext.Provider>
  );
};

export const useProducts = () => useContext(ProductContext);
