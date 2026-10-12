import React, { useState, useEffect, useRef } from 'react';
import { useProducts } from '../../context/ProductContext';
import { 
  UploadCloud, 
  Search, 
  Check, 
  Loader2,
  Clock,
  Palette,
  Sparkles
} from 'lucide-react';

export default function InputStage() {
  const { activeProduct, updateActiveProduct, startScrapePipeline, isProcessing } = useProducts();

  // Local draft state for zero-latency instant typing
  const [draft, setDraft] = useState(() => ({
    id: activeProduct?.id || '',
    name: activeProduct?.name || '',
    prompt: activeProduct?.prompt || activeProduct?.description || '',
    modelNumber: activeProduct?.modelNumber || activeProduct?.articleNumber || '',
    category: activeProduct?.category || 'General',
    color: activeProduct?.color || '',
    finish: activeProduct?.finish || '',
    width: activeProduct?.width ?? '',
    height: activeProduct?.height ?? '',
    depth: activeProduct?.depth ?? '',
    thumbnail: activeProduct?.thumbnail || '',
    imageFile: activeProduct?.imageFile || null
  }));

  const activeIdRef = useRef(activeProduct?.id);
  const [elapsedTime, setElapsedTime] = useState(0);

  // Sync draft state only when switching to a different product ID
  useEffect(() => {
    if (activeProduct?.id && activeProduct.id !== activeIdRef.current) {
      activeIdRef.current = activeProduct.id;
      setDraft({
        id: activeProduct?.id || '',
        name: activeProduct?.name || '',
        prompt: activeProduct?.prompt || activeProduct?.description || '',
        modelNumber: activeProduct?.modelNumber || activeProduct?.articleNumber || '',
        category: activeProduct?.category || 'General',
        color: activeProduct?.color || '',
        finish: activeProduct?.finish || '',
        width: activeProduct?.width ?? '',
        height: activeProduct?.height ?? '',
        depth: activeProduct?.depth ?? '',
        thumbnail: activeProduct?.thumbnail || '',
        imageFile: activeProduct?.imageFile || null
      });
    }
  }, [activeProduct?.id]);

  // Live timer during scraping
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

  // Local input change handler: pure local state update with 0 global rerender overhead
  const handleChange = (field, value) => {
    setDraft(prev => ({ ...prev, [field]: value }));
  };

  // Commit field to global context on blur
  const handleBlur = (field) => {
    const value = draft[field];
    const updateObj = { [field]: value };
    if (field === 'prompt') {
      updateObj.description = value;
    }
    updateActiveProduct(updateObj);
  };

  const handleImageUpload = (e) => {
    const file = e.target.files[0];
    if (file) {
      const reader = new FileReader();
      reader.onload = (event) => {
        const base64Url = event.target.result;
        setDraft(prev => ({
          ...prev,
          thumbnail: base64Url,
          imageFile: file
        }));
        updateActiveProduct({ 
          thumbnail: base64Url, 
          imageFile: file 
        });
      };
      reader.readAsDataURL(file);
    }
  };

  const handleScrapeClick = () => {
    const payload = {
      ...activeProduct,
      ...draft,
      prompt: draft.prompt || '',
      description: draft.prompt || '',
      id: draft.id || `PROD-${Date.now().toString().slice(-4)}`,
      name: draft.name || 'Custom Product',
      modelNumber: draft.modelNumber || '',
      category: draft.category || 'General',
      color: draft.color || '',
      finish: draft.finish || '',
      width: draft.width !== '' && draft.width !== undefined ? Number(draft.width) : '',
      height: draft.height !== '' && draft.height !== undefined ? Number(draft.height) : '',
      depth: draft.depth !== '' && draft.depth !== undefined ? Number(draft.depth) : '',
      thumbnail: draft.thumbnail || '',
      imageFile: draft.imageFile || null
    };
    updateActiveProduct(payload);
    startScrapePipeline(payload);
  };

  return (
    <div className="max-w-4xl mx-auto p-6 md:p-8">
      {/* Main Card Form */}
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
          {/* Product Prompt / Description */}
          <div>
            <label className="block text-xs font-semibold text-[#1C2434] dark:text-white mb-1.5">
              Product Prompt / Description (describe what to scrape)
            </label>
            <textarea
              rows={3}
              value={draft.prompt}
              onChange={(e) => handleChange('prompt', e.target.value)}
              onBlur={() => handleBlur('prompt')}
              placeholder="e.g. Stainless steel kitchen sink, single bowl with drainer, satin finish"
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
                value={draft.id}
                onChange={(e) => handleChange('id', e.target.value)}
                onBlur={() => handleBlur('id')}
                placeholder="e.g. SINK-01"
                className="w-full px-4 py-2.5 text-xs bg-[#F8FAFC] dark:bg-[#0F1832] border border-[#E2E8F0] dark:border-[#1E2C52] rounded-xl text-[#1C2434] dark:text-white placeholder-[#94A3B8] dark:placeholder-[#62718E] focus:outline-none focus:ring-2 focus:ring-brand-500/20 focus:border-brand-500 transition-all"
              />
            </div>
            <div>
              <label className="block text-xs font-semibold text-[#1C2434] dark:text-white mb-1.5">
                Product Name
              </label>
              <input
                type="text"
                value={draft.name}
                onChange={(e) => handleChange('name', e.target.value)}
                onBlur={() => handleBlur('name')}
                placeholder="e.g. Hansgrohe C51 Sink Combi 660 Select"
                className="w-full px-4 py-2.5 text-xs bg-[#F8FAFC] dark:bg-[#0F1832] border border-[#E2E8F0] dark:border-[#1E2C52] rounded-xl text-[#1C2434] dark:text-white placeholder-[#94A3B8] dark:placeholder-[#62718E] focus:outline-none focus:ring-2 focus:ring-brand-500/20 focus:border-brand-500 transition-all"
              />
            </div>
          </div>

          {/* Model Number & Category */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-semibold text-[#1C2434] dark:text-white mb-1.5">
                Model Number / Article Number
              </label>
              <input
                type="text"
                value={draft.modelNumber}
                onChange={(e) => handleChange('modelNumber', e.target.value)}
                onBlur={() => handleBlur('modelNumber')}
                placeholder="e.g. 43218000"
                className="w-full px-4 py-2.5 text-xs bg-[#F8FAFC] dark:bg-[#0F1832] border border-[#E2E8F0] dark:border-[#1E2C52] rounded-xl text-[#1C2434] dark:text-white placeholder-[#94A3B8] dark:placeholder-[#62718E] focus:outline-none focus:ring-2 focus:ring-brand-500/20 focus:border-brand-500 transition-all"
              />
            </div>
            <div>
              <label className="block text-xs font-semibold text-[#1C2434] dark:text-white mb-1.5">
                Category
              </label>
              <select
                value={draft.category}
                onChange={(e) => {
                  handleChange('category', e.target.value);
                  updateActiveProduct({ category: e.target.value });
                }}
                className="w-full px-4 py-2.5 text-xs bg-[#F8FAFC] dark:bg-[#0F1832] border border-[#E2E8F0] dark:border-[#1E2C52] rounded-xl text-[#1C2434] dark:text-white focus:outline-none focus:ring-2 focus:ring-brand-500/20 focus:border-brand-500 transition-all"
              >
                <option value="General">General</option>
                <option value="Sanitary Ware">Sanitary Ware</option>
                <option value="Industrial Equipment">Industrial Equipment</option>
                <option value="Consumer Electronics">Consumer Electronics</option>
                <option value="Home Appliances">Home Appliances</option>
                <option value="Furniture &amp; Interior">Furniture &amp; Interior</option>
                <option value="Automotive">Automotive</option>
              </select>
            </div>
          </div>

          {/* Color & Finish Options */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-semibold text-[#1C2434] dark:text-white mb-1.5">
                Color (optional)
              </label>
              <input
                type="text"
                value={draft.color}
                onChange={(e) => handleChange('color', e.target.value)}
                onBlur={() => handleBlur('color')}
                placeholder="e.g. Stainless Steel / Matte Black"
                className="w-full px-4 py-2.5 text-xs bg-[#F8FAFC] dark:bg-[#0F1832] border border-[#E2E8F0] dark:border-[#1E2C52] rounded-xl text-[#1C2434] dark:text-white placeholder-[#94A3B8] dark:placeholder-[#62718E] focus:outline-none focus:ring-2 focus:ring-brand-500/20 focus:border-brand-500 transition-all"
              />
            </div>
            <div>
              <label className="block text-xs font-semibold text-[#1C2434] dark:text-white mb-1.5">
                Finish / Material (optional)
              </label>
              <input
                type="text"
                value={draft.finish}
                onChange={(e) => handleChange('finish', e.target.value)}
                onBlur={() => handleBlur('finish')}
                placeholder="e.g. Brushed Satin / Powder Coated"
                className="w-full px-4 py-2.5 text-xs bg-[#F8FAFC] dark:bg-[#0F1832] border border-[#E2E8F0] dark:border-[#1E2C52] rounded-xl text-[#1C2434] dark:text-white placeholder-[#94A3B8] dark:placeholder-[#62718E] focus:outline-none focus:ring-2 focus:ring-brand-500/20 focus:border-brand-500 transition-all"
              />
            </div>
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
                {draft.thumbnail ? (
                  <div className="flex items-center gap-3">
                    <img
                      src={draft.thumbnail}
                      alt="Uploaded preview"
                      className="w-16 h-16 rounded-xl object-cover border border-[#E2E8F0] dark:border-[#1E2C52]"
                    />
                    <div className="text-left">
                      <p className="text-xs font-semibold text-emerald-600 dark:text-emerald-400 flex items-center gap-1">
                        <Check className="w-3.5 h-3.5" /> Image Loaded
                      </p>
                      <p className="text-[11px] text-[#64748B] dark:text-[#8D9CB8]">
                        Click or drag to replace image
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
                value={draft.width}
                onChange={(e) => handleChange('width', e.target.value)}
                onBlur={() => handleBlur('width')}
                placeholder="e.g. 660"
                className="w-full px-3 py-2 text-xs bg-[#F8FAFC] dark:bg-[#0F1832] border border-[#E2E8F0] dark:border-[#1E2C52] rounded-xl text-[#1C2434] dark:text-white focus:outline-none focus:ring-2 focus:ring-brand-500/20 focus:border-brand-500 transition-all"
              />
            </div>
            <div>
              <label className="block text-[11px] font-semibold text-[#64748B] dark:text-[#8D9CB8] mb-1">
                Height (mm)
              </label>
              <input
                type="number"
                value={draft.height}
                onChange={(e) => handleChange('height', e.target.value)}
                onBlur={() => handleBlur('height')}
                placeholder="e.g. 190"
                className="w-full px-3 py-2 text-xs bg-[#F8FAFC] dark:bg-[#0F1832] border border-[#E2E8F0] dark:border-[#1E2C52] rounded-xl text-[#1C2434] dark:text-white focus:outline-none focus:ring-2 focus:ring-brand-500/20 focus:border-brand-500 transition-all"
              />
            </div>
            <div>
              <label className="block text-[11px] font-semibold text-[#64748B] dark:text-[#8D9CB8] mb-1">
                Depth (mm)
              </label>
              <input
                type="number"
                value={draft.depth}
                onChange={(e) => handleChange('depth', e.target.value)}
                onBlur={() => handleBlur('depth')}
                placeholder="e.g. 450"
                className="w-full px-3 py-2 text-xs bg-[#F8FAFC] dark:bg-[#0F1832] border border-[#E2E8F0] dark:border-[#1E2C52] rounded-xl text-[#1C2434] dark:text-white focus:outline-none focus:ring-2 focus:ring-brand-500/20 focus:border-brand-500 transition-all"
              />
            </div>
          </div>

          {/* Action Footer with Normal Timer */}
          <div className="pt-3 flex justify-end">
            <button
              onClick={handleScrapeClick}
              disabled={isProcessing}
              className="flex items-center gap-2 px-6 py-2.5 text-xs font-semibold text-white bg-brand-500 hover:bg-brand-600 disabled:bg-brand-500/80 rounded-xl shadow-md shadow-brand-500/25 transition-all hover:scale-[1.01] active:scale-[0.99]"
            >
              {isProcessing ? (
                <>
                  <Loader2 className="w-3.5 h-3.5 animate-spin" />
                  <span className="font-mono">Researching... ({elapsedTime.toFixed(1)}s)</span>
                </>
              ) : (
                <>
                  <Search className="w-3.5 h-3.5" />
                  <span>Start Autonomous Pipeline</span>
                </>
              )}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
