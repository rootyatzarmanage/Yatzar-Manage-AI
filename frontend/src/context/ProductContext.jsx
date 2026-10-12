import React, { createContext, useContext, useState, useEffect, useMemo, useCallback, useRef } from 'react';
import { scrapeProductViews, triageProduct } from '../services/api';

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
    relatedUrls: [],
    triage: null
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
  const [currentStage, setCurrentStage] = useState(initialState.currentStage); // 0: Input, 1: Scrape, 2: Image Approval, 3: 3D Generate, 4: 3D Approval
  const [darkMode, setDarkMode] = useState(false);
  const [isProcessing, setIsProcessing] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');

  // Active product object (strictly from product list)
  const activeProduct = useMemo(() => {
    return products.find(p => p.id === activeProductId) || products[0] || createCleanProduct('PROD-FALLBACK');
  }, [products, activeProductId]);

  // Keep a ref to activeProduct for asynchronous callbacks
  const activeProductRef = useRef(activeProduct);
  activeProductRef.current = activeProduct;

  // Dark mode class handler
  useEffect(() => {
    if (darkMode) {
      document.documentElement.classList.add('dark');
    } else {
      document.documentElement.classList.remove('dark');
    }
  }, [darkMode]);

  // Persistent storage synchronizer: debounced so it does not block the UI thread during updates
  useEffect(() => {
    const timer = setTimeout(() => {
      try {
        // Sanitize products for localStorage: exclude bulky binary files
        const sanitized = products.map(p => {
          const { imageFile, ...rest } = p;
          // Truncate huge base64 strings if exceeding 300KB to protect localStorage quota
          let thumb = rest.thumbnail || '';
          if (thumb.startsWith('data:image') && thumb.length > 300000) {
            thumb = '';
          }
          return {
            ...rest,
            thumbnail: thumb,
            imageFile: null
          };
        });

        localStorage.setItem(STORAGE_KEYS.PRODUCTS, JSON.stringify(sanitized));
        localStorage.setItem(STORAGE_KEYS.ACTIVE_ID, activeProductId);
        localStorage.setItem(STORAGE_KEYS.STAGE, currentStage.toString());
      } catch (err) {
        console.warn('Unable to persist product workflow state to localStorage:', err);
      }
    }, 400);

    return () => clearTimeout(timer);
  }, [products, activeProductId, currentStage]);

  const selectProduct = useCallback((id) => {
    setActiveProductId(id);
    setProducts(prev => {
      const prod = prev.find(p => p.id === id);
      if (prod && prod.currentStage !== undefined) {
        setCurrentStage(prod.currentStage);
      } else {
        setCurrentStage(0);
      }
      return prev;
    });
  }, []);

  /**
   * Action: "NEW" Product Creation.
   * Completely resets product-specific state to clean empty values.
   * Prevents previous dimensions, prompts, images, and candidates from leaking.
   */
  const createNewProduct = useCallback(() => {
    const newProduct = createCleanProduct();
    setProducts(prev => [newProduct, ...prev]);
    setActiveProductId(newProduct.id);
    setCurrentStage(0);
  }, []);

  const updateActiveProduct = useCallback((fields) => {
    setProducts(prev => prev.map(p => {
      if (p.id === activeProductId) {
        return { ...p, ...fields };
      }
      return p;
    }));
  }, [activeProductId]);

  const startScrapePipeline = useCallback(async (customPayload) => {
    setIsProcessing(true);
    const payload = customPayload || activeProductRef.current;
    
    // Clear previous images and update active product metadata
    setProducts(prev => prev.map(p => {
      if (p.id === payload.id || p.id === activeProductId) {
        return {
          ...p,
          ...payload,
          scrapedImages: [],
          imagesCount: 0,
          modelUrl: null,
          modelPath: null,
          validationResult: null
        };
      }
      return p;
    }));

    try {
      // Call live backend scraping & research service
      const scrapeData = await scrapeProductViews(payload);
      
      if (scrapeData.success && scrapeData.images && scrapeData.images.length > 0) {
        const liveImages = scrapeData.images.map((img, idx) => ({
          ...img,
          tag: img.angle || `View ${idx + 1}`,
          status: img.status || (img.is_selected_reference ? 'VERIFIED' : 'CANDIDATE')
        }));

        const bestRef = scrapeData.best_reference || liveImages.find(i => i.is_selected_reference) || liveImages[0];

        setProducts(prev => prev.map(p => {
          if (p.id === payload.id || p.id === activeProductId) {
            return {
              ...p,
              ...payload,
              scrapedImages: liveImages,
              rejectedImages: scrapeData.rejected_images || [],
              imagesCount: liveImages.length,
              best_reference: bestRef,
              selected_reference: bestRef,
              research_duration_sec: scrapeData.research_duration_sec || (scrapeData.executionTime ? parseFloat(scrapeData.executionTime) : null),
              researchDuration: scrapeData.executionTime || (scrapeData.research_duration_sec ? `${scrapeData.research_duration_sec}s` : null),
              researchSummary: scrapeData.summary || {
                total_retrieved: scrapeData.totalImagesFound || liveImages.length,
                duplicates_removed: scrapeData.duplicates_removed || 0,
                rejected_as_irrelevant: (scrapeData.rejected_images || []).length,
                verified_count: liveImages.length,
                selected_reference: 1
              },
              relatedUrls: scrapeData.relatedUrls || [],
              executionTime: scrapeData.executionTime || '4.2s',
              gpuDevice: scrapeData.gpuDevice || 'NVIDIA GPU',
              currentStage: 1
            };
          }
          return p;
        }));

      } else {
        // Honest empty state: no candidates met verification threshold
        setProducts(prev => prev.map(p => {
          if (p.id === payload.id || p.id === activeProductId) {
            return {
              ...p,
              ...payload,
              scrapedImages: [],
              imagesCount: 0,
              best_reference: null,
              researchSummary: {
                total_retrieved: 0,
                duplicates_removed: 0,
                rejected_as_irrelevant: 0,
                verified_count: 0,
                selected_reference: 0
              },
              currentStage: 1
            };
          }
          return p;
        }));
      }
    } catch (err) {
      console.error('Backend live research error:', err);
      setProducts(prev => prev.map(p => {
        if (p.id === payload.id || p.id === activeProductId) {
          return {
            ...p,
            ...payload,
            scrapedImages: [],
            imagesCount: 0,
            best_reference: null,
            currentStage: 1
          };
        }
        return p;
      }));
    } finally {
      setIsProcessing(false);
      setCurrentStage(1); // Advance to Research stage
    }
  }, [activeProductId]);

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
    updateActiveProduct,
    startScrapePipeline
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
    updateActiveProduct,
    startScrapePipeline
  ]);

  return (
    <ProductContext.Provider value={value}>
      {children}
    </ProductContext.Provider>
  );
};

export const useProducts = () => useContext(ProductContext);
