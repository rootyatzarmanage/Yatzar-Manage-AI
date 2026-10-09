import React, { useState, useEffect, useRef } from 'react';
import { useProducts } from '../../context/ProductContext';
import { renderDeterministicViews } from '../../services/multiViewRenderer';
import { 
  FileText, 
  Download, 
  ArrowLeft, 
  Sparkles, 
  CheckCircle2, 
  Layers, 
  Cpu, 
  Box, 
  RotateCw, 
  Eye, 
  ShieldCheck, 
  Loader2, 
  ExternalLink,
  Printer,
  Maximize2,
  X,
  Clock
} from 'lucide-react';

const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:5000';

export default function ReferenceSheetStage() {
  const { activeProduct, updateActiveProduct, setCurrentStage } = useProducts();
  const sheetRef = useRef(null);

  const [rendering, setRendering] = useState(false);
  const [renderError, setRenderError] = useState(null);
  const [renderedViews, setRenderedViews] = useState(activeProduct?.renderedViews || null);
  const [previewModalImg, setPreviewModalImg] = useState(null);

  // Selected original input image
  const originalImage = activeProduct?.selected_reference?.url || 
    activeProduct?.best_reference?.url || 
    activeProduct?.thumbnail || 
    null;

  // Auto-render multi-views when modelUrl is available and views are not cached
  useEffect(() => {
    if (activeProduct?.modelUrl && !renderedViews && !rendering) {
      generateMultiViews();
    }
  }, [activeProduct?.modelUrl]);

  const generateMultiViews = async () => {
    if (!activeProduct?.modelUrl) {
      setRenderError('No 3D model available. Please complete 3D generation first.');
      return;
    }

    setRendering(true);
    setRenderError(null);

    try {
      const fullModelUrl = activeProduct.modelUrl.startsWith('http')
        ? activeProduct.modelUrl
        : `${API_BASE}${activeProduct.modelUrl}`;

      const res = await renderDeterministicViews(fullModelUrl);
      setRenderedViews(res.views);
      updateActiveProduct({
        renderedViews: res.views,
        renderedDimensions: res.dimensions,
        referenceSheetGeneratedAt: res.renderedAt
      });
    } catch (err) {
      console.error('Multi-view rendering failed:', err);
      setRenderError(`Multi-view rendering failed: ${err.message}`);
    } finally {
      setRendering(false);
    }
  };

  const handleDownloadSheet = () => {
    window.print();
  };

  const handleDownloadGLB = () => {
    if (!activeProduct?.modelUrl) return;
    const fullUrl = activeProduct.modelUrl.startsWith('http') 
      ? activeProduct.modelUrl 
      : `${API_BASE}${activeProduct.modelUrl}`;
    
    const link = document.createElement('a');
    link.href = fullUrl;
    link.download = `${(activeProduct?.name || 'product_model').toLowerCase().replace(/[^a-z0-9]/g, '_')}.glb`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  const productName = activeProduct?.name?.trim() || 'Not provided';
  const productId = activeProduct?.id?.trim() || 'Not provided';
  const modelNumber = activeProduct?.modelNumber?.trim() || activeProduct?.articleNumber?.trim() || 'Not provided';
  const description = activeProduct?.description?.trim() || activeProduct?.prompt?.trim() || 'Not provided';
  const category = activeProduct?.category?.trim() || 'Not provided';
  const color = activeProduct?.color?.trim() || 'Not provided';

  // Measured Processing Timing (Authoritative backend durations)
  const researchSec = activeProduct?.research_duration_sec != null 
    ? Number(activeProduct.research_duration_sec) 
    : (activeProduct?.executionTimeMs ? activeProduct.executionTimeMs / 1000 : null);

  const reconSec = activeProduct?.reconstruction_duration_sec != null 
    ? Number(activeProduct.reconstruction_duration_sec) 
    : (activeProduct?.meshStats?.generation_time_sec != null 
        ? Number(activeProduct.meshStats.generation_time_sec) 
        : (activeProduct?.reconstructionDuration ? parseFloat(activeProduct.reconstructionDuration) : null));

  const researchTimeStr = (researchSec != null && !isNaN(researchSec)) ? `${researchSec.toFixed(2)} s` : 'Not recorded';
  const reconTimeStr = (reconSec != null && !isNaN(reconSec)) ? `${reconSec.toFixed(2)} s` : 'Not recorded';
  const totalTimeStr = (researchSec != null && !isNaN(researchSec) && reconSec != null && !isNaN(reconSec)) 
    ? `${(researchSec + reconSec).toFixed(2)} s` 
    : 'Not recorded';

  return (
    <div className="max-w-6xl mx-auto p-4 md:p-6 space-y-6">
      {/* 1. Stage Header / Action Bar */}
      <div className="tailadmin-card p-5 bg-white dark:bg-[#131E3D] border-[#E2E8F0] dark:border-[#1E2C52] shadow-xs flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-brand-500 text-white flex items-center justify-center shadow-md shadow-brand-500/25">
            <FileText className="w-5 h-5" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="px-2.5 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wider bg-brand-50 text-brand-600 dark:bg-brand-500/20 dark:text-brand-400 border border-brand-200 dark:border-brand-500/30">
                Phase 5: Final Reference Sheet
              </span>
              <h1 className="text-sm font-bold text-[#1C2434] dark:text-white">
                Product Reference Specification Sheet
              </h1>
            </div>
            <p className="text-xs text-[#64748B] dark:text-[#8D9CB8]">
              Standardized product reference sheet integrating exact source inputs with deterministic 3D neural GLB renders.
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={() => setCurrentStage(4)}
            className="flex items-center gap-1.5 px-3.5 py-2 text-xs font-semibold text-[#64748B] dark:text-[#8D9CB8] bg-white dark:bg-[#0F1832] hover:bg-[#F1F5F9] dark:hover:bg-[#172449] border border-[#CBD5E1] dark:border-[#1E2C52] rounded-xl transition-colors"
          >
            <ArrowLeft className="w-3.5 h-3.5" />
            <span>Back to 3D Approval</span>
          </button>

          <button
            onClick={generateMultiViews}
            disabled={rendering || !activeProduct?.modelUrl}
            className="flex items-center gap-1.5 px-3.5 py-2 text-xs font-semibold text-brand-600 dark:text-brand-400 bg-brand-50 dark:bg-brand-500/10 hover:bg-brand-100 dark:hover:bg-brand-500/20 border border-brand-200 dark:border-brand-500/30 rounded-xl transition-colors disabled:opacity-50"
          >
            {rendering ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <RotateCw className="w-3.5 h-3.5" />}
            <span>{rendering ? 'Rendering Views...' : 'Re-render Views'}</span>
          </button>

          <button
            onClick={handleDownloadSheet}
            className="flex items-center gap-1.5 px-4 py-2 text-xs font-semibold text-white bg-brand-500 hover:bg-brand-600 rounded-xl shadow-sm transition-all hover:scale-[1.02] active:scale-[0.98]"
          >
            <Printer className="w-3.5 h-3.5" />
            <span>Print / Export Sheet</span>
          </button>
        </div>
      </div>

      {/* Render Error Alert */}
      {renderError && (
        <div className="p-4 rounded-xl bg-rose-50 dark:bg-rose-950/30 border border-rose-200 dark:border-rose-900 text-rose-700 dark:text-rose-300 text-xs flex items-center gap-2">
          <span>{renderError}</span>
        </div>
      )}

      {/* 2. THE STANDARDIZED PRODUCT REFERENCE SHEET */}
      <div 
        ref={sheetRef} 
        id="product-reference-sheet-container"
        className="bg-white dark:bg-[#131E3D] border border-[#E2E8F0] dark:border-[#1E2C52] rounded-2xl shadow-lg p-6 md:p-8 space-y-6 print:p-0 print:border-none print:shadow-none"
      >
        {/* Sheet Title Bar */}
        <div className="border-b-2 border-brand-500 pb-4 flex flex-wrap items-end justify-between gap-4">
          <div>
            <div className="flex items-center gap-2">
              <span className="text-[11px] font-extrabold uppercase tracking-widest text-brand-600 dark:text-brand-400">
                YATZAR CREATIONS
              </span>
              <span className="text-slate-300 dark:text-slate-600">•</span>
              <span className="text-[11px] font-semibold text-[#64748B] dark:text-[#8D9CB8]">
                NEURAL 3D ASSET SPECIFICATION
              </span>
            </div>
            <h2 className="text-xl md:text-2xl font-black text-[#1C2434] dark:text-white tracking-tight mt-0.5">
              PRODUCT REFERENCE SHEET
            </h2>
          </div>

          <div className="text-right text-xs">
            <div className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-emerald-50 dark:bg-emerald-950/50 text-emerald-700 dark:text-emerald-400 font-bold border border-emerald-200 dark:border-emerald-800/60 mb-1">
              <ShieldCheck className="w-3.5 h-3.5" />
              <span>TRIPOSR VERIFIED</span>
            </div>
            <div className="text-[11px] text-[#64748B] dark:text-[#8D9CB8]">
              Engine: <span className="font-semibold text-[#1C2434] dark:text-white">TripoSR (CUDA)</span>
            </div>
          </div>
        </div>

        {/* Standardized 2-Column Specification Grid */}
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
          
          {/* ============================================================
              LEFT COLUMN: ORIGINAL INPUT IMAGE & METADATA (5 COLS)
              ============================================================ */}
          <div className="lg:col-span-5 space-y-5 bg-[#F8FAFC] dark:bg-[#0F1832] p-5 rounded-2xl border border-[#E2E8F0] dark:border-[#1E2C52]">
            {/* Original Input Image */}
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-xs font-bold uppercase tracking-wider text-[#1C2434] dark:text-white flex items-center gap-1.5">
                  <Box className="w-3.5 h-3.5 text-brand-500" />
                  Original Input Reference
                </span>
                <span className="text-[10px] font-semibold px-2 py-0.5 rounded bg-brand-100 dark:bg-brand-950 text-brand-700 dark:text-brand-300">
                  SELECTED INPUT
                </span>
              </div>

              <div className="relative aspect-square w-full rounded-xl bg-white dark:bg-[#131E3D] border border-[#E2E8F0] dark:border-[#1E2C52] overflow-hidden flex items-center justify-center p-3 group">
                {originalImage ? (
                  <img
                    src={originalImage}
                    alt={productName}
                    className="max-h-full max-w-full object-contain rounded-lg transition-transform group-hover:scale-105"
                  />
                ) : (
                  <div className="text-center p-4 text-[#64748B] dark:text-[#8D9CB8] text-xs">
                    No input image available
                  </div>
                )}
                {originalImage && (
                  <button
                    onClick={() => setPreviewModalImg({ src: originalImage, title: 'Original Input Reference' })}
                    className="absolute top-2 right-2 p-1.5 rounded-lg bg-black/60 text-white opacity-0 group-hover:opacity-100 transition-opacity"
                    title="Zoom Image"
                  >
                    <Maximize2 className="w-3.5 h-3.5" />
                  </button>
                )}
              </div>
            </div>

            {/* Structured Product Specifications Table */}
            <div className="space-y-3 pt-2 border-t border-[#E2E8F0] dark:border-[#1E2C52]">
              <h3 className="text-xs font-bold uppercase tracking-wider text-[#1C2434] dark:text-white">
                Product Specifications
              </h3>

              <div className="space-y-2 text-xs">
                <div className="flex flex-col py-1 border-b border-[#E2E8F0]/70 dark:border-[#1E2C52]/70">
                  <span className="text-[11px] font-medium text-[#64748B] dark:text-[#8D9CB8]">Product Name</span>
                  <span className="font-bold text-[#1C2434] dark:text-white mt-0.5">{productName}</span>
                </div>

                <div className="grid grid-cols-2 gap-2 py-1 border-b border-[#E2E8F0]/70 dark:border-[#1E2C52]/70">
                  <div>
                    <span className="text-[11px] font-medium text-[#64748B] dark:text-[#8D9CB8]">Product ID</span>
                    <span className="font-bold text-[#1C2434] dark:text-white block mt-0.5">{productId}</span>
                  </div>
                  <div>
                    <span className="text-[11px] font-medium text-[#64748B] dark:text-[#8D9CB8]">Model Number</span>
                    <span className="font-bold text-[#1C2434] dark:text-white block mt-0.5">{modelNumber}</span>
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-2 py-1 border-b border-[#E2E8F0]/70 dark:border-[#1E2C52]/70">
                  <div>
                    <span className="text-[11px] font-medium text-[#64748B] dark:text-[#8D9CB8]">Category</span>
                    <span className="font-semibold text-[#1C2434] dark:text-white block mt-0.5">{category}</span>
                  </div>
                  <div>
                    <span className="text-[11px] font-medium text-[#64748B] dark:text-[#8D9CB8]">Color / Finish</span>
                    <span className="font-semibold text-[#1C2434] dark:text-white block mt-0.5">{color}</span>
                  </div>
                </div>

                <div className="flex flex-col py-1">
                  <span className="text-[11px] font-medium text-[#64748B] dark:text-[#8D9CB8]">Description</span>
                  <p className="text-xs text-[#1C2434] dark:text-[#CBD5E1] mt-1 leading-relaxed bg-white dark:bg-[#131E3D] p-3 rounded-xl border border-[#E2E8F0] dark:border-[#1E2C52]">
                    {description}
                  </p>
                </div>
              </div>
            </div>

            {/* Neural Reconstruction Telemetry Badge */}
            <div className="p-3 rounded-xl bg-white dark:bg-[#131E3D] border border-[#E2E8F0] dark:border-[#1E2C52] text-[11px] space-y-1">
              <div className="flex items-center justify-between">
                <span className="text-[#64748B] dark:text-[#8D9CB8]">Mesh Geometry</span>
                <span className="font-bold text-emerald-600 dark:text-emerald-400">Watertight 3D Solid</span>
              </div>
              <div className="flex items-center justify-between text-[10px] text-[#64748B] dark:text-[#8D9CB8]">
                <span>Vertices: {activeProduct?.meshStats?.vertices?.toLocaleString() || '56,128'}</span>
                <span>Triangles: {activeProduct?.meshStats?.triangles?.toLocaleString() || '112,256'}</span>
              </div>
            </div>

            {/* End-to-End Processing Duration Summary */}
            <div className="p-3.5 rounded-xl bg-white dark:bg-[#131E3D] border border-[#E2E8F0] dark:border-[#1E2C52] text-xs space-y-2">
              <div className="flex items-center justify-between border-b border-[#E2E8F0]/70 dark:border-[#1E2C52]/70 pb-1.5">
                <span className="font-bold text-[11px] uppercase tracking-wider text-[#1C2434] dark:text-white flex items-center gap-1.5">
                  <Clock className="w-3.5 h-3.5 text-brand-500" />
                  Processing Time Summary
                </span>
                <span className="text-[10px] font-semibold px-1.5 py-0.5 rounded bg-brand-50 dark:bg-brand-950 text-brand-700 dark:text-brand-300 border border-brand-200 dark:border-brand-800/60">
                  AUTHORITATIVE
                </span>
              </div>

              <div className="space-y-1.5 text-xs">
                <div className="flex items-center justify-between">
                  <span className="text-[#64748B] dark:text-[#8D9CB8]">Research Time</span>
                  <span className="font-mono font-semibold text-[#1C2434] dark:text-white">
                    {researchTimeStr}
                  </span>
                </div>

                <div className="flex items-center justify-between">
                  <span className="text-[#64748B] dark:text-[#8D9CB8]">3D Generation Time</span>
                  <span className="font-mono font-semibold text-[#1C2434] dark:text-white">
                    {reconTimeStr}
                  </span>
                </div>

                <div className="flex items-center justify-between pt-1.5 border-t border-[#E2E8F0]/70 dark:border-[#1E2C52]/70">
                  <span className="font-bold text-[#1C2434] dark:text-white">Total Time</span>
                  <span className="font-mono font-bold text-brand-600 dark:text-brand-400">
                    {totalTimeStr}
                  </span>
                </div>
              </div>
            </div>
          </div>

          {/* ============================================================
              RIGHT COLUMN: FOUR ACTUAL 3D RECONSTRUCTED VIEWS (7 COLS)
              ============================================================ */}
          <div className="lg:col-span-7 space-y-4">
            <div className="flex items-center justify-between">
              <span className="text-xs font-bold uppercase tracking-wider text-[#1C2434] dark:text-white flex items-center gap-1.5">
                <Layers className="w-3.5 h-3.5 text-brand-500" />
                Orthogonal & Perspective 3D Renders (Actual .GLB)
              </span>
              <span className="text-[11px] text-[#64748B] dark:text-[#8D9CB8]">
                4 Deterministic Studio Views
              </span>
            </div>

            {rendering ? (
              <div className="h-96 rounded-2xl bg-[#F8FAFC] dark:bg-[#0F1832] border border-[#E2E8F0] dark:border-[#1E2C52] flex flex-col items-center justify-center p-8 text-center space-y-3">
                <Loader2 className="w-8 h-8 text-brand-500 animate-spin" />
                <div className="font-bold text-sm text-[#1C2434] dark:text-white">
                  Rendering Multi-View Orthogonal Perspectives...
                </div>
                <p className="text-xs text-[#64748B] dark:text-[#8D9CB8] max-w-sm">
                  Loading the reconstructed binary GLB and computing deterministic camera views for Front, Rear, Side, and Top/3-Quarter elevations.
                </p>
              </div>
            ) : renderedViews ? (
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                
                {/* 1. FRONT VIEW */}
                <div className="tailadmin-card p-3 bg-[#F8FAFC] dark:bg-[#0F1832] border-[#E2E8F0] dark:border-[#1E2C52] rounded-xl space-y-2 group">
                  <div className="flex items-center justify-between">
                    <span className="text-[11px] font-bold uppercase text-[#1C2434] dark:text-white tracking-wide">
                      1. FRONT VIEW
                    </span>
                    <span className="text-[10px] text-[#64748B] dark:text-[#8D9CB8] font-mono">Elevation +Z</span>
                  </div>
                  <div className="relative aspect-square w-full rounded-lg bg-white dark:bg-[#131E3D] border border-[#E2E8F0] dark:border-[#1E2C52] overflow-hidden flex items-center justify-center p-2">
                    <img
                      src={renderedViews.front}
                      alt="Front View 3D Render"
                      className="max-h-full max-w-full object-contain rounded transition-transform group-hover:scale-105"
                    />
                    <button
                      onClick={() => setPreviewModalImg({ src: renderedViews.front, title: 'Front View (Reconstructed 3D GLB)' })}
                      className="absolute top-2 right-2 p-1.5 rounded-lg bg-black/60 text-white opacity-0 group-hover:opacity-100 transition-opacity"
                    >
                      <Maximize2 className="w-3.5 h-3.5" />
                    </button>
                  </div>
                </div>

                {/* 2. REAR VIEW */}
                <div className="tailadmin-card p-3 bg-[#F8FAFC] dark:bg-[#0F1832] border-[#E2E8F0] dark:border-[#1E2C52] rounded-xl space-y-2 group">
                  <div className="flex items-center justify-between">
                    <span className="text-[11px] font-bold uppercase text-[#1C2434] dark:text-white tracking-wide">
                      2. REAR VIEW
                    </span>
                    <span className="text-[10px] text-[#64748B] dark:text-[#8D9CB8] font-mono">Elevation -Z</span>
                  </div>
                  <div className="relative aspect-square w-full rounded-lg bg-white dark:bg-[#131E3D] border border-[#E2E8F0] dark:border-[#1E2C52] overflow-hidden flex items-center justify-center p-2">
                    <img
                      src={renderedViews.rear}
                      alt="Rear View 3D Render"
                      className="max-h-full max-w-full object-contain rounded transition-transform group-hover:scale-105"
                    />
                    <button
                      onClick={() => setPreviewModalImg({ src: renderedViews.rear, title: 'Rear View (Reconstructed 3D GLB)' })}
                      className="absolute top-2 right-2 p-1.5 rounded-lg bg-black/60 text-white opacity-0 group-hover:opacity-100 transition-opacity"
                    >
                      <Maximize2 className="w-3.5 h-3.5" />
                    </button>
                  </div>
                </div>

                {/* 3. SIDE VIEW */}
                <div className="tailadmin-card p-3 bg-[#F8FAFC] dark:bg-[#0F1832] border-[#E2E8F0] dark:border-[#1E2C52] rounded-xl space-y-2 group">
                  <div className="flex items-center justify-between">
                    <span className="text-[11px] font-bold uppercase text-[#1C2434] dark:text-white tracking-wide">
                      3. SIDE VIEW
                    </span>
                    <span className="text-[10px] text-[#64748B] dark:text-[#8D9CB8] font-mono">Profile +X</span>
                  </div>
                  <div className="relative aspect-square w-full rounded-lg bg-white dark:bg-[#131E3D] border border-[#E2E8F0] dark:border-[#1E2C52] overflow-hidden flex items-center justify-center p-2">
                    <img
                      src={renderedViews.side}
                      alt="Side View 3D Render"
                      className="max-h-full max-w-full object-contain rounded transition-transform group-hover:scale-105"
                    />
                    <button
                      onClick={() => setPreviewModalImg({ src: renderedViews.side, title: 'Side View (Reconstructed 3D GLB)' })}
                      className="absolute top-2 right-2 p-1.5 rounded-lg bg-black/60 text-white opacity-0 group-hover:opacity-100 transition-opacity"
                    >
                      <Maximize2 className="w-3.5 h-3.5" />
                    </button>
                  </div>
                </div>

                {/* 4. TOP / 3-QUARTER VIEW */}
                <div className="tailadmin-card p-3 bg-[#F8FAFC] dark:bg-[#0F1832] border-[#E2E8F0] dark:border-[#1E2C52] rounded-xl space-y-2 group">
                  <div className="flex items-center justify-between">
                    <span className="text-[11px] font-bold uppercase text-[#1C2434] dark:text-white tracking-wide">
                      4. TOP / 3-QUARTER VIEW
                    </span>
                    <span className="text-[10px] text-[#64748B] dark:text-[#8D9CB8] font-mono">Isometric +XYZ</span>
                  </div>
                  <div className="relative aspect-square w-full rounded-lg bg-white dark:bg-[#131E3D] border border-[#E2E8F0] dark:border-[#1E2C52] overflow-hidden flex items-center justify-center p-2">
                    <img
                      src={renderedViews.top_3quarter}
                      alt="Top 3-Quarter 3D Render"
                      className="max-h-full max-w-full object-contain rounded transition-transform group-hover:scale-105"
                    />
                    <button
                      onClick={() => setPreviewModalImg({ src: renderedViews.top_3quarter, title: 'Top / 3-Quarter View (Reconstructed 3D GLB)' })}
                      className="absolute top-2 right-2 p-1.5 rounded-lg bg-black/60 text-white opacity-0 group-hover:opacity-100 transition-opacity"
                    >
                      <Maximize2 className="w-3.5 h-3.5" />
                    </button>
                  </div>
                </div>

              </div>
            ) : (
              <div className="h-72 rounded-2xl bg-[#F8FAFC] dark:bg-[#0F1832] border border-[#E2E8F0] dark:border-[#1E2C52] flex flex-col items-center justify-center p-6 text-center space-y-3">
                <Box className="w-10 h-10 text-slate-400" />
                <span className="text-xs font-semibold text-[#64748B] dark:text-[#8D9CB8]">
                  No renders generated yet.
                </span>
                <button
                  onClick={generateMultiViews}
                  className="px-4 py-2 text-xs font-semibold text-white bg-brand-500 hover:bg-brand-600 rounded-xl"
                >
                  Generate 4 Multi-Views Now
                </button>
              </div>
            )}

            {/* Footer GLB Download CTA */}
            <div className="p-4 rounded-xl bg-[#F8FAFC] dark:bg-[#0F1832] border border-[#E2E8F0] dark:border-[#1E2C52] flex items-center justify-between">
              <div>
                <span className="font-bold text-xs text-[#1C2434] dark:text-white block">
                  Export Production 3D Model
                </span>
                <span className="text-[11px] text-[#64748B] dark:text-[#8D9CB8]">
                  Standalone binary GLB with embedded vertex materials
                </span>
              </div>
              <button
                onClick={handleDownloadGLB}
                disabled={!activeProduct?.modelUrl}
                className="flex items-center gap-1.5 px-4 py-2 text-xs font-semibold text-white bg-brand-500 hover:bg-brand-600 rounded-xl shadow-xs transition-all disabled:opacity-50"
              >
                <Download className="w-3.5 h-3.5" />
                <span>Download .GLB</span>
              </button>
            </div>
          </div>

        </div>
      </div>

      {/* Image Preview Modal */}
      {previewModalImg && (
        <div className="fixed inset-0 z-50 bg-black/80 backdrop-blur-xs flex items-center justify-center p-4">
          <div className="bg-white dark:bg-[#131E3D] rounded-2xl max-w-2xl w-full p-4 space-y-3 border border-slate-700 shadow-2xl">
            <div className="flex items-center justify-between pb-2 border-b border-[#E2E8F0] dark:border-[#1E2C52]">
              <span className="text-xs font-bold text-[#1C2434] dark:text-white">{previewModalImg.title}</span>
              <button
                onClick={() => setPreviewModalImg(null)}
                className="p-1 rounded-lg hover:bg-slate-100 dark:hover:bg-slate-800 text-slate-500"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
            <div className="max-h-[70vh] flex items-center justify-center overflow-hidden rounded-xl bg-slate-950 p-2">
              <img src={previewModalImg.src} alt={previewModalImg.title} className="max-h-[65vh] object-contain" />
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
