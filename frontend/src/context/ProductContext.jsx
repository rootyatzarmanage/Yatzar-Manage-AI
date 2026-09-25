import React, { createContext, useContext, useState, useEffect } from 'react';
import { scrapeProductViews, triageProduct } from '../services/api';

const ProductContext = createContext();

// High-resolution realistic industrial images for the demo
const MOCK_SCRAPED_IMAGES = [
  {
    id: 'hex-1',
    title: 'hex_front_primary.jpg',
    url: 'https://images.unsplash.com/photo-1581092160607-ee22621dd758?w=600&auto=format&fit=crop&q=80',
    angle: '0° Front View',
    tag: 'Front View',
    source: 'oem_datasheet_cad',
    score: 0.964,
    selected: true,
    role: 'Base Frame Geometry',
    signals: { silhouette: 98, material: 95, topology: 92 }
  },
  {
    id: 'hex-2',
    title: 'hex_rear_nozzles.jpg',
    url: 'https://images.unsplash.com/photo-1581092580497-e0d23cbdf1dc?w=600&auto=format&fit=crop&q=80',
    angle: '180° Rear Ports',
    tag: 'Rear Ports',
    source: 'model_number_search_unfiltered',
    score: 0.871,
    selected: true,
    role: 'Fluid Connection Nozzles',
    signals: { silhouette: 94, material: 91, topology: 42 }
  },
  {
    id: 'hex-3',
    title: 'hex_side_tightening_bolts.jpg',
    url: 'https://images.unsplash.com/photo-1581092335397-9583fe92d232?w=600&auto=format&fit=crop&q=80',
    angle: '90° Side Profile',
    tag: 'Side Profile',
    source: 'targeted_port_cascade',
    score: 0.825,
    selected: true,
    role: 'Frame Depth & Bolt Spacing',
    signals: { silhouette: 89, material: 93, topology: 38 }
  },
  {
    id: 'hex-4',
    title: 'hex_isometric_factory.jpg',
    url: 'https://images.unsplash.com/photo-1581092795360-fd1ca04f0952?w=600&auto=format&fit=crop&q=80',
    angle: 'Isometric Angle',
    tag: 'Isometric',
    source: 'playwright_360_extractor',
    score: 0.910,
    selected: false,
    role: 'Proportions Validation',
    signals: { silhouette: 95, material: 92, topology: 86 }
  },
  {
    id: 'hex-5',
    title: 'hex_dual_plate_diagram.jpg',
    url: 'https://images.unsplash.com/photo-1581093458791-9f3c3900df4b?w=600&auto=format&fit=crop&q=80',
    angle: '2D CAD Schematic',
    tag: 'Spec Diagram',
    source: 'domain_spec_sheet',
    score: 0.783,
    selected: false,
    role: 'None',
    signals: { silhouette: 82, material: 60, topology: 75 }
  },
  {
    id: 'hex-6',
    title: 'hex_inlet_flange_closeup.jpg',
    url: 'https://images.unsplash.com/photo-1581091226825-a6a2a5aee158?w=600&auto=format&fit=crop&q=80',
    angle: '270° Port Flange',
    tag: 'Detail / Ports',
    source: 'targeted_port_cascade',
    score: 0.849,
    selected: false,
    role: 'None',
    signals: { silhouette: 76, material: 94, topology: 49 }
  },
  {
    id: 'hex-7',
    title: 'hex_assembly_line.jpg',
    url: 'https://images.unsplash.com/photo-1581092162384-8987c1d64718?w=600&auto=format&fit=crop&q=80',
    angle: 'Multi-Object Angle',
    tag: 'Multi-Object',
    source: 'direct_url_fallback',
    score: 0.712,
    selected: false,
    role: 'None',
    signals: { silhouette: 70, material: 84, topology: 55 }
  },
  {
    id: 'hex-8',
    title: 'hex_maintenance_exploded.jpg',
    url: 'https://images.unsplash.com/photo-1581092334651-ddf26d9a09d0?w=600&auto=format&fit=crop&q=80',
    angle: 'Exploded View',
    tag: 'Exploded View',
    source: 'parts_catalog',
    score: 0.680,
    selected: false,
    role: 'None',
    signals: { silhouette: 62, material: 75, topology: 50 }
  },
  {
    id: 'hex-9',
    title: 'alfalaval_corporate_logo.svg',
    url: 'https://images.unsplash.com/photo-1618005182384-a83a8bd57fbe?w=600&auto=format&fit=crop&q=80',
    angle: 'Noise (SVG)',
    tag: 'Logo / Noise',
    source: 'domain_header',
    score: 0.341,
    selected: false,
    role: 'None',
    signals: { silhouette: 12, material: 20, topology: 15 }
  },
  {
    id: 'hex-10',
    title: 'wooden_shipping_crate.jpg',
    url: 'https://images.unsplash.com/photo-1586528116311-ad8dd3c8310d?w=600&auto=format&fit=crop&q=80',
    angle: 'Packaging (Wood)',
    tag: 'Packaging / Noise',
    source: 'warehouse_logistics',
    score: 0.286,
    selected: false,
    role: 'None',
    signals: { silhouette: 18, material: 15, topology: 10 }
  }
];

const INITIAL_PRODUCTS = [
  {
    id: 'NIKE-AM90-RED',
    name: 'Nike Air Max 90 Running Shoe',
    slug: 'Nike_Air_Max_90_Running_Shoe',
    status: 'IN_PROGRESS',
    category: 'Footwear & Apparel',
    modelNumber: 'AM90-INFRARED',
    prompt: 'Nike Air Max 90 classic infrared running shoe with mesh toe box, visible Air unit in heel, and swoosh side panel',
    width: 310,
    height: 140,
    depth: 110,
    currentStage: 0,
    executionTime: '4.8s',
    imagesCount: 3,
    confidenceScore: 0.942,
    thumbnail: 'https://images.unsplash.com/photo-1542291026-7eec264c27ff?w=600&auto=format&fit=crop&q=80',
    triage: {
      rotationalSymmetry: 'Bilateral Symmetry (89%)',
      azimuthalUncertainty: 0.16,
      complexity: 'Moderate (Heel Cushion & Outsole)',
      recommendedBudget: 'Cascading Multi-Query (Cycle 2/3)',
      quadrantCoverage: { front: 0.98, profile: 0.92, rear: 0.74, ports: 0.58 },
      directives: [
        'Extract primary lateral chassis silhouette from seed image',
        'Targeted query: "Nike Air Max 90 Running Shoe rear features & dimensions"',
        'Targeted query: "Nike Air Max 90 outsole tread pattern & waffle sole"'
      ]
    },
    scrapedImages: [
      {
        id: 'nike-1',
        title: 'Nike Air Max 90 (0° Front Reference)',
        url: 'https://images.unsplash.com/photo-1542291026-7eec264c27ff?w=600&auto=format&fit=crop&q=80',
        angle: '0° Front Reference',
        tag: '0° Front Reference',
        source: 'Scrapy (Static)',
        score: 0.985,
        selected: true,
        role: 'Primary Reference View',
        signals: { silhouette: 98, material: 95, topology: 92 }
      },
      {
        id: 'nike-2',
        title: 'Nike Air Max 90 (Isometric Perspective)',
        url: 'https://images.unsplash.com/photo-1552346154-21d32810aba3?w=600&auto=format&fit=crop&q=80',
        angle: 'Isometric Perspective',
        tag: 'Isometric Angle',
        source: 'Playwright (Dynamic)',
        score: 0.962,
        selected: true,
        role: 'Proportions Validation',
        signals: { silhouette: 96, material: 94, topology: 88 }
      },
      {
        id: 'nike-3',
        title: 'Nike Air Max 90 (90° Right Profile)',
        url: 'https://images.unsplash.com/photo-1595950653106-6c9ebd614d3a?w=600&auto=format&fit=crop&q=80',
        angle: '90° Right Profile',
        tag: 'Side Profile',
        source: 'Scrapy (Static)',
        score: 0.948,
        selected: true,
        role: 'Frame Depth & Profile',
        signals: { silhouette: 95, material: 92, topology: 86 }
      }
    ],
    relatedUrls: [
      { title: 'Nike Air Max 90 - Official Product Specifications & Sizing Chart', url: 'https://www.nike.com/air-max-90', selected: true },
      { title: 'Sneaker Freaker: Anatomical Breakdown of Air Max 90 Heel Cushion', url: 'https://www.sneakerfreaker.com/air-max-90-history', selected: true }
    ]
  },
  {
    id: 'AL-HEX-TL10-P',
    name: 'Alfa Laval Industrial Plate Heat Exchanger',
    slug: 'Alfa_Laval_Industrial_Plate_Heat_Exchanger',
    status: 'APPROVED',
    category: 'Industrial Equipment',
    modelNumber: 'TL10-PFG',
    prompt: 'Alfa Laval industrial gasketed plate-and-frame heat exchanger with royal blue end plates, top carrying bar, tightening bolts, and 4 corner fluid port flanges',
    width: 1200,
    height: 1800,
    depth: 850,
    currentStage: 0, // Start at Input for the demo
    executionTime: '12s',
    imagesCount: 8,
    confidenceScore: 0.938,
    thumbnail: 'https://images.unsplash.com/photo-1581092160607-ee22621dd758?w=300&auto=format&fit=crop&q=80',
    triage: {
      rotationalSymmetry: 'Bilateral Symmetry (92%)',
      azimuthalUncertainty: 0.18,
      complexity: 'High (Asymmetric Nozzles & Plates)',
      recommendedBudget: 'Cascading Multi-Query (Cycle 2/3)',
      quadrantCoverage: { front: 0.98, profile: 0.88, rear: 0.72, ports: 0.45 },
      directives: [
        'Extract primary frame silhouette and plate stack depth from hex_front_primary.jpg',
        'Targeted query: "Alfa Laval rear fluid connection nozzle layout & port diameter"',
        'Targeted query: "Alfa Laval side tightening bolts spacing & compression limit"'
      ]
    },
    scrapedImages: MOCK_SCRAPED_IMAGES,
    relatedUrls: [
      { title: 'Industrial line gasketed plate-and-frame heat exchangers - Official CAD', url: 'https://www.alfalaval.com/products/heat-transfer/plate-heat-exchangers/industrial-line/', selected: true },
      { title: 'Alfa Laval TL10-P Dimensional Engineering Datasheet & Nozzle Specs', url: 'https://www.engineering-specs.com/datasheets/alfa-laval-tl10p.pdf', selected: true },
      { title: 'Distributor Parts Catalog: Plate Packs & Gasket Replacement', url: 'https://distributor.example.com/catalog/al-hex-tl10', selected: false }
    ],
    qaAudit: {
      overallIntegrity: 0.938,
      isWatertight: true,
      eulerCharacteristic: 2,
      nonManifoldEdges: 0,
      portDiameterAlignment: 0.912,
      colorDeltaE: 1.2,
      orthogonalViews: [
        { label: 'Rendered Image 01 (0° Front Master)', view: '0° Front Orthogonal', score: 0.964, img: 'https://images.unsplash.com/photo-1581092160607-ee22621dd758?w=400&auto=format&fit=crop&q=80' },
        { label: 'Rendered Image 02 (90° Side Profile)', view: '90° Profile Left', score: 0.925, img: 'https://images.unsplash.com/photo-1581092335397-9583fe92d232?w=400&auto=format&fit=crop&q=80' },
        { label: 'Rendered Image 03 (180° Rear Nozzles)', view: '180° Rear Ports', score: 0.912, img: 'https://images.unsplash.com/photo-1581092580497-e0d23cbdf1dc?w=400&auto=format&fit=crop&q=80' },
        { label: 'Rendered Image 04 (270° Port Flange Detail)', view: '270° Flange Cavities', score: 0.941, img: 'https://images.unsplash.com/photo-1581091226825-a6a2a5aee158?w=400&auto=format&fit=crop&q=80' },
        { label: 'Rendered Image 05 (Isometric Studio Master)', view: 'Isometric Studio', score: 0.958, img: 'https://images.unsplash.com/photo-1581092795360-fd1ca04f0952?w=400&auto=format&fit=crop&q=80' },
        { label: 'Rendered Image 06 (CSG Watertight Topology)', view: 'Solid CSG Manifold', score: 0.982, img: 'https://images.unsplash.com/photo-1581093458791-9f3c3900df4b?w=400&auto=format&fit=crop&q=80' }
      ]
    }
  },
  {
    id: 'IPHONE-15-PRO',
    name: 'iPhone 15 Pro Titanium',
    slug: 'iPhone_15_Pro_Titanium',
    status: 'APPROVED',
    category: 'Consumer Electronics',
    modelNumber: 'A3102',
    prompt: 'Apple iPhone 15 Pro natural titanium brushed metal chassis dynamic island triple camera plateau USB-C bottom port',
    width: 706,
    height: 1466,
    depth: 82,
    currentStage: 0,
    executionTime: '8s',
    imagesCount: 12,
    confidenceScore: 0.965,
    thumbnail: 'https://images.unsplash.com/photo-1695048133142-1a20484d2569?w=300&auto=format&fit=crop&q=80'
  }
];

export const ProductProvider = ({ children }) => {
  const [products, setProducts] = useState(INITIAL_PRODUCTS);
  const [activeProductId, setActiveProductId] = useState(INITIAL_PRODUCTS[0].id);
  const [currentStage, setCurrentStage] = useState(0); // 0: Input, 1: Scrape, 2: Image Approval, 3: 3D Generate, 4: 3D Approval
  const [darkMode, setDarkMode] = useState(false);
  const [isProcessing, setIsProcessing] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');

  // Active product object
  const activeProduct = products.find(p => p.id === activeProductId) || products[0];

  useEffect(() => {
    if (darkMode) {
      document.documentElement.classList.add('dark');
    } else {
      document.documentElement.classList.remove('dark');
    }
  }, [darkMode]);

  const selectProduct = (id) => {
    setActiveProductId(id);
    const prod = products.find(p => p.id === id);
    if (prod && prod.currentStage !== undefined) {
      setCurrentStage(prod.currentStage);
    } else {
      setCurrentStage(0);
    }
  };

  const createNewProduct = () => {
    const newId = `PROD-${Date.now().toString().slice(-4)}`;
    const newProduct = {
      id: newId,
      name: '',
      slug: '',
      status: 'IN_PROGRESS',
      category: 'General',
      modelNumber: '',
      prompt: '',
      width: 100,
      height: 100,
      depth: 100,
      currentStage: 0,
      executionTime: '0s',
      imagesCount: 0,
      confidenceScore: 0.0,
      thumbnail: '',
      imageFile: null,
      sourceUrls: [],
      scrapedImages: [],
      relatedUrls: [],
      triage: null
    };
    setProducts(prev => [newProduct, ...prev]);
    setActiveProductId(newId);
    setCurrentStage(0);
  };

  const updateActiveProduct = (fields) => {
    setProducts(prev => prev.map(p => {
      if (p.id === activeProductId) {
        return { ...p, ...fields };
      }
      return p;
    }));
  };

  const startScrapePipeline = async (customPayload) => {
    setIsProcessing(true);
    const payload = customPayload || activeProduct;
    
    // Clear previous images and update active product metadata
    updateActiveProduct({
      ...payload,
      scrapedImages: [],
      imagesCount: 0
    });

    try {
      // Call live backend scraping service (DINOv2 + Web Scraping)
      const scrapeData = await scrapeProductViews(payload);
      
      if (scrapeData.success && scrapeData.images && scrapeData.images.length > 0) {
        const liveImages = scrapeData.images.map((img, idx) => ({
          ...img,
          tag: img.angle || `View ${idx + 1}`,
          role: idx === 0 ? 'Primary Reference View' : idx === 1 ? 'Secondary Profile' : 'Supporting Angle',
          signals: {
            silhouette: Math.round((img.score || 0.85) * 100),
            material: Math.round((img.patch_score || 0.80) * 100),
            topology: Math.round((img.global_similarity || 0.75) * 100)
          }
        }));

        updateActiveProduct({
          ...payload,
          scrapedImages: liveImages,
          imagesCount: liveImages.filter(i => i.selected).length,
          relatedUrls: scrapeData.relatedUrls || [],
          seedCoordinates: scrapeData.seed_coordinates || { x: 0, y: 0 },
          executionTime: scrapeData.executionTime || '4.2s',
          gpuDevice: scrapeData.gpuDevice || 'NVIDIA GeForce RTX 4060 Laptop GPU',
          currentStage: 1
        });
      } else {
        // Honest empty state: no candidates met the threshold
        updateActiveProduct({
          ...payload,
          scrapedImages: [],
          imagesCount: 0,
          currentStage: 1
        });
      }
    } catch (err) {
      console.error('Backend live scraping error:', err);
      updateActiveProduct({
        ...payload,
        scrapedImages: [],
        imagesCount: 0,
        currentStage: 1
      });
    } finally {
      setIsProcessing(false);
      setCurrentStage(1); // Advance to Scrape stage
    }
  };

  return (
    <ProductContext.Provider
      value={{
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
      }}
    >
      {children}
    </ProductContext.Provider>
  );
};

export const useProducts = () => useContext(ProductContext);
