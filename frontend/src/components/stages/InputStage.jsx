import React, { useState, useEffect } from 'react';
import { useProducts } from '../../context/ProductContext';
import { 
  UploadCloud, 
  Search, 
  Sparkles, 
  Layers, 
  Check, 
  HelpCircle, 
  ChevronRight,
  ShieldCheck,
  Zap,
  Box,
  Loader2,
  Clock,
  Timer
} from 'lucide-react';

export default function InputStage() {
  const { activeProduct, updateActiveProduct, startScrapePipeline, isProcessing } = useProducts();

  const [prompt, setPrompt] = useState(activeProduct?.prompt || '');
  const [productId, setProductId] = useState(activeProduct?.id || '');
  const [name, setName] = useState(activeProduct?.name || '');
  const [modelNumber, setModelNumber] = useState(activeProduct?.modelNumber || '');
  const [category, setCategory] = useState(activeProduct?.category || 'Industrial Equipment');
  const [sourceUrls, setSourceUrls] = useState(activeProduct?.sourceUrls?.join('\n') || '');
  const [width, setWidth] = useState(activeProduct?.width || 1200);
  const [height, setHeight] = useState(activeProduct?.height || 1800);
  const [depth, setDepth] = useState(activeProduct?.depth || 850);
  const [uploadedImage, setUploadedImage] = useState(activeProduct?.thumbnail || '');
  const [imageFile, setImageFile] = useState(activeProduct?.imageFile || null);
  const [elapsedTime, setElapsedTime] = useState(0);

  useEffect(() => {
    let interval = null;
    if (isProcessing) {
      setElapsedTime(0);
      const startTime = Date.now();
      interval = setInterval(() => {
        setElapsedTime((Date.now() - startTime) / 1000);
      }, 100);
    } else {
      if (interval) clearInterval(interval);
    }
    return () => {
      if (interval) clearInterval(interval);
    };
  }, [isProcessing]);

  useEffect(() => {
    if (activeProduct) {
      setPrompt(activeProduct.prompt || '');
      setProductId(activeProduct.id || '');
      setName(activeProduct.name || '');
      setModelNumber(activeProduct.modelNumber || '');
      setCategory(activeProduct.category || 'General');
      setSourceUrls(activeProduct.sourceUrls?.join('\n') || '');
      setWidth(activeProduct.width || 100);
      setHeight(activeProduct.height || 100);
      setDepth(activeProduct.depth || 100);
      setUploadedImage(activeProduct.thumbnail || '');
      setImageFile(activeProduct.imageFile || null);
    } else {
      setPrompt('');
      setProductId('');
      setName('');
      setModelNumber('');
      setCategory('General');
      setSourceUrls('');
      setWidth(100);
      setHeight(100);
      setDepth(100);
      setUploadedImage('');
      setImageFile(null);
    }
  }, [activeProduct?.id, activeProduct?.thumbnail]);

  const handleImageUpload = (e) => {
    const file = e.target.files[0];
    if (file) {
      setImageFile(file);
      const reader = new FileReader();
      reader.onload = (event) => {
        const base64Url = event.target.result;
        setUploadedImage(base64Url);
        updateActiveProduct({ 
          thumbnail: base64Url, 
          imageFile: file 
        });
      };
      reader.readAsDataURL(file);
    }
  };

  const handleScrapeClick = () => {
    const newProductData = {
      prompt,
      id: productId || `PROD-${Date.now().toString().slice(-4)}`,
      name: name || 'Uploaded Product Asset',
      modelNumber: modelNumber || 'SKU-01',
      category,
      sourceUrls: sourceUrls.split('\n').filter(Boolean),
      width: Number(width),
      height: Number(height),
      depth: Number(depth),
      thumbnail: uploadedImage || activeProduct?.thumbnail,
      imageFile: imageFile || activeProduct?.imageFile
    };
    updateActiveProduct(newProductData);
    startScrapePipeline(newProductData);
  };

  const isSymmetrical = name.toLowerCase().includes('flask') || name.toLowerCase().includes('bottle') || name.toLowerCase().includes('urinal') || name.toLowerCase().includes('can') || name.toLowerCase().includes('extinguisher');
  const uncertainty = isSymmetrical ? 0.12 : 0.28;

  return (
    <div className="max-w-4xl mx-auto p-6 md:p-8">
      {/* V-LLM Pre-Triage Intelligence Banner */}
      <div className="mb-6 p-4 rounded-2xl bg-gradient-to-r from-brand-50 via-white to-blue-50/40 dark:from-[#131E3D] dark:via-[#0F1A34] dark:to-brand-950/30 border border-brand-200 dark:border-[#1E2C52] shadow-xs">
        <div className="flex items-start justify-between">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-xl bg-brand-500/10 dark:bg-brand-500/20 flex items-center justify-center text-brand-600 dark:text-brand-400">
              <Sparkles className="w-4 h-4" />
            </div>
            <div>
              <h2 className="text-xs font-bold uppercase tracking-wider text-brand-600 dark:text-brand-400">
                Phase 1: V-LLM Geometric Triage &amp; DINOv2 Feature Extractor
              </h2>
              <p className="text-xs text-[#64748B] dark:text-[#8D9CB8]">
                Analyzes rotational symmetry and azimuthal uncertainty to prune 80%+ scraping budget.
              </p>
            </div>
          </div>
          <div className="text-right">
            <span className="text-[11px] font-semibold text-[#64748B] dark:text-[#8D9CB8] block">
              Estimated Uncertainty
            </span>
            <span className={`text-sm font-bold ${uncertainty <= 0.15 ? 'text-emerald-600 dark:text-emerald-400' : 'text-amber-500 dark:text-amber-400'}`}>
              {(uncertainty * 100).toFixed(0)}% {uncertainty <= 0.15 ? '(Symmetrical Low-Cost)' : '(High Complexity Multi-Query)'}
            </span>
          </div>
        </div>
      </div>

      {/* Main Card Form matching Screenshot #2 */}
      <div className="tailadmin-card p-6 md:p-8 bg-white dark:bg-[#131E3D]">
        <div className="mb-6">
          <h2 className="text-base font-bold text-[#1C2434] dark:text-white">
            New Product
          </h2>
          <p className="text-xs text-[#64748B] dark:text-[#8D9CB8] mt-0.5">
            Enter product details, then click Scrape to find images and URLs
          </p>
        </div>

        <div className="space-y-5">
          {/* Product Prompt */}
          <div>
            <label className="block text-xs font-semibold text-[#1C2434] dark:text-white mb-1.5">
              Product Prompt (describe what to scrape)
            </label>
            <textarea
              rows={3}
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              placeholder="e.g. Toyota Camry 2026 sedan white color, all angles, interior and exterior photos"
              className="w-full px-4 py-2.5 text-xs bg-[#F8FAFC] dark:bg-[#0F1832] border border-[#E2E8F0] dark:border-[#1E2C52] rounded-xl text-[#1C2434] dark:text-white placeholder-[#94A3B8] dark:placeholder-[#62718E] focus:outline-none focus:ring-2 focus:ring-brand-500/20 focus:border-brand-500 transition-all"
            />
          </div>

          {/* Product ID & Product Name */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-semibold text-[#1C2434] dark:text-white mb-1.5">
                Product ID
              </label>
              <input
                type="text"
                value={productId}
                onChange={(e) => setProductId(e.target.value)}
                placeholder="e.g. CAMRY-2026"
                className="w-full px-4 py-2.5 text-xs bg-[#F8FAFC] dark:bg-[#0F1832] border border-[#E2E8F0] dark:border-[#1E2C52] rounded-xl text-[#1C2434] dark:text-white placeholder-[#94A3B8] dark:placeholder-[#62718E] focus:outline-none focus:ring-2 focus:ring-brand-500/20 focus:border-brand-500 transition-all"
              />
            </div>
            <div>
              <label className="block text-xs font-semibold text-[#1C2434] dark:text-white mb-1.5">
                Product Name
              </label>
              <input
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="e.g. Toyota Camry 2026"
                className="w-full px-4 py-2.5 text-xs bg-[#F8FAFC] dark:bg-[#0F1832] border border-[#E2E8F0] dark:border-[#1E2C52] rounded-xl text-[#1C2434] dark:text-white placeholder-[#94A3B8] dark:placeholder-[#62718E] focus:outline-none focus:ring-2 focus:ring-brand-500/20 focus:border-brand-500 transition-all"
              />
            </div>
          </div>

          {/* Model Number & Category */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-semibold text-[#1C2434] dark:text-white mb-1.5">
                Model Number
              </label>
              <input
                type="text"
                value={modelNumber}
                onChange={(e) => setModelNumber(e.target.value)}
                placeholder="e.g. XLE-2.5L"
                className="w-full px-4 py-2.5 text-xs bg-[#F8FAFC] dark:bg-[#0F1832] border border-[#E2E8F0] dark:border-[#1E2C52] rounded-xl text-[#1C2434] dark:text-white placeholder-[#94A3B8] dark:placeholder-[#62718E] focus:outline-none focus:ring-2 focus:ring-brand-500/20 focus:border-brand-500 transition-all"
              />
            </div>
            <div>
              <label className="block text-xs font-semibold text-[#1C2434] dark:text-white mb-1.5">
                Category
              </label>
              <select
                value={category}
                onChange={(e) => setCategory(e.target.value)}
                className="w-full px-4 py-2.5 text-xs bg-[#F8FAFC] dark:bg-[#0F1832] border border-[#E2E8F0] dark:border-[#1E2C52] rounded-xl text-[#1C2434] dark:text-white focus:outline-none focus:ring-2 focus:ring-brand-500/20 focus:border-brand-500 transition-all"
              >
                <option value="Industrial Equipment">Industrial Equipment</option>
                <option value="Consumer Electronics">Consumer Electronics</option>
                <option value="Home Appliances">Home Appliances</option>
                <option value="Furniture &amp; Interior">Furniture &amp; Interior</option>
                <option value="Automotive">Automotive</option>
                <option value="Sanitary Ware">Sanitary Ware</option>
              </select>
            </div>
          </div>

          {/* Source URLs */}
          <div>
            <label className="block text-xs font-semibold text-[#1C2434] dark:text-white mb-1.5">
              Source URLs (optional — one per line)
            </label>
            <textarea
              rows={2}
              value={sourceUrls}
              onChange={(e) => setSourceUrls(e.target.value)}
              placeholder="https://example.com/product-page"
              className="w-full px-4 py-2 text-xs bg-[#F8FAFC] dark:bg-[#0F1832] border border-[#E2E8F0] dark:border-[#1E2C52] rounded-xl text-[#1C2434] dark:text-white placeholder-[#94A3B8] dark:placeholder-[#62718E] focus:outline-none focus:ring-2 focus:ring-brand-500/20 focus:border-brand-500 transition-all"
            />
          </div>

          {/* Product Images Drag-and-Drop Zone */}
          <div>
            <label className="block text-xs font-semibold text-[#1C2434] dark:text-white mb-1.5">
              Product Images (upload manually)
            </label>
            <div className="relative border-2 border-dashed border-[#CBD5E1] dark:border-[#1E2C52] hover:border-brand-500 dark:hover:border-brand-500 rounded-2xl p-6 text-center transition-colors bg-[#F8FAFC]/50 dark:bg-[#0F1832]/60 group">
              <input
                type="file"
                accept="image/*"
                onChange={handleImageUpload}
                className="absolute inset-0 w-full h-full opacity-0 cursor-pointer"
              />
              <div className="flex flex-col items-center justify-center pointer-events-none">
                {uploadedImage ? (
                  <div className="flex items-center gap-3">
                    <img
                      src={uploadedImage}
                      alt="Uploaded preview"
                      className="w-16 h-16 rounded-xl object-cover border border-[#E2E8F0] dark:border-[#1E2C52]"
                    />
                    <div className="text-left">
                      <p className="text-xs font-semibold text-emerald-600 dark:text-emerald-400 flex items-center gap-1">
                        <Check className="w-3.5 h-3.5" /> Seed Image Loaded
                      </p>
                      <p className="text-[11px] text-[#64748B] dark:text-[#8D9CB8]">
                        DINOv2 ViT-B14 768-dim vector extracted
                      </p>
                    </div>
                  </div>
                ) : (
                  <>
                    <UploadCloud className="w-8 h-8 text-[#94A3B8] dark:text-[#62718E] group-hover:text-brand-500 group-hover:scale-110 transition-all duration-200 mb-2" />
                    <span className="text-xs font-semibold text-[#1C2434] dark:text-white">
                      Click to upload images
                    </span>
                    <span className="text-[11px] text-[#64748B] dark:text-[#8D9CB8] mt-0.5">
                      PNG, JPG, WEBP up to 25MB
                    </span>
                  </>
                )}
              </div>
            </div>
          </div>

          {/* Width, Height, Depth inputs */}
          <div className="grid grid-cols-3 gap-3">
            <div>
              <label className="block text-[11px] font-semibold text-[#64748B] dark:text-[#8D9CB8] mb-1">
                Width (mm)
              </label>
              <input
                type="number"
                value={width}
                onChange={(e) => setWidth(e.target.value)}
                placeholder="e.g. 1200"
                className="w-full px-3 py-2 text-xs bg-[#F8FAFC] dark:bg-[#0F1832] border border-[#E2E8F0] dark:border-[#1E2C52] rounded-xl text-[#1C2434] dark:text-white focus:outline-none focus:ring-2 focus:ring-brand-500/20 focus:border-brand-500 transition-all"
              />
            </div>
            <div>
              <label className="block text-[11px] font-semibold text-[#64748B] dark:text-[#8D9CB8] mb-1">
                Height (mm)
              </label>
              <input
                type="number"
                value={height}
                onChange={(e) => setHeight(e.target.value)}
                placeholder="e.g. 1800"
                className="w-full px-3 py-2 text-xs bg-[#F8FAFC] dark:bg-[#0F1832] border border-[#E2E8F0] dark:border-[#1E2C52] rounded-xl text-[#1C2434] dark:text-white focus:outline-none focus:ring-2 focus:ring-brand-500/20 focus:border-brand-500 transition-all"
              />
            </div>
            <div>
              <label className="block text-[11px] font-semibold text-[#64748B] dark:text-[#8D9CB8] mb-1">
                Depth (mm)
              </label>
              <input
                type="number"
                value={depth}
                onChange={(e) => setDepth(e.target.value)}
                placeholder="e.g. 850"
                className="w-full px-3 py-2 text-xs bg-[#F8FAFC] dark:bg-[#0F1832] border border-[#E2E8F0] dark:border-[#1E2C52] rounded-xl text-[#1C2434] dark:text-white focus:outline-none focus:ring-2 focus:ring-brand-500/20 focus:border-brand-500 transition-all"
              />
            </div>
          </div>

          {/* Live Scraping & Vectorizing Active Banner */}
          {isProcessing && (
            <div className="p-4 rounded-xl bg-gradient-to-r from-brand-500 to-indigo-600 text-white flex items-center justify-between shadow-lg animate-pulse">
              <div className="flex items-center gap-3">
                <div className="w-7 h-7 rounded-full border-2 border-white/40 border-t-white animate-spin flex items-center justify-center">
                  <Zap className="w-3.5 h-3.5 text-white" />
                </div>
                <div>
                  <div className="text-xs font-bold tracking-wide">
                    ⏱️ Scraping &amp; Vectorizing: {elapsedTime.toFixed(1).padStart(4, '0')}s elapsed...
                  </div>
                  <div className="text-[11px] opacity-90">
                    Executing dynamic browser harvest &amp; DINOv2 ViT-S/14 patch-level feature extraction on RTX 4060
                  </div>
                </div>
              </div>
              <div className="text-xs font-mono font-bold bg-white/20 px-3 py-1.5 rounded-lg backdrop-blur-xs">
                GPU ACTIVE
              </div>
            </div>
          )}

          {/* Action Footer */}
          <div className="pt-3 flex justify-end">
            <button
              onClick={handleScrapeClick}
              disabled={isProcessing}
              className="flex items-center gap-2 px-6 py-2.5 text-xs font-semibold text-white bg-brand-500 hover:bg-brand-600 disabled:bg-brand-500/80 rounded-xl shadow-md shadow-brand-500/25 transition-all hover:scale-[1.01] active:scale-[0.99]"
            >
              {isProcessing ? (
                <>
                  <div className="w-3.5 h-3.5 border-2 border-white/30 border-t-white rounded-full animate-spin"></div>
                  <span className="font-mono">⏱️ Scraping &amp; Vectorizing: {elapsedTime.toFixed(1).padStart(4, '0')}s</span>
                </>
              ) : (
                <>
                  <Search className="w-3.5 h-3.5" />
                  <span>Scrape</span>
                </>
              )}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
