import React, { useState, useEffect } from 'react';
import { useProducts } from '../../context/ProductContext';
import { 
  Search, 
  CheckCircle2, 
  XCircle, 
  Sparkles, 
  ArrowLeft, 
  ArrowRight, 
  ShieldCheck, 
  Layers, 
  Filter, 
  Clock, 
  Check, 
  Image as ImageIcon,
  ExternalLink,
  Loader2,
  AlertTriangle,
  RotateCcw,
  Ban
} from 'lucide-react';

export default function ScrapeStage() {
  const { 
    activeProduct, 
    updateActiveProduct, 
    setCurrentStage, 
    activeResearchJob, 
    cancelResearch, 
    retryResearch 
  } = useProducts();

  const curatedImages = React.useMemo(() => {
    return (activeProduct?.scrapedImages || []).map(img => ({
      ...img,
      is_rejected: false
    }));
  }, [activeProduct?.scrapedImages]);

  const urls = React.useMemo(() => activeProduct?.relatedUrls || [], [activeProduct?.relatedUrls]);
  const isRunning = activeResearchJob?.status === 'RUNNING' || activeResearchJob?.status === 'QUEUED';
  const isFailed = activeResearchJob?.status === 'FAILED';
  const isCancelled = activeResearchJob?.status === 'CANCELLED';

  const handleProceedToApproval = () => {
    // Only derive selected reference from eligible curated candidates
    let selectedRef = activeProduct?.best_reference;
    if (!selectedRef && curatedImages.length > 0) {
      selectedRef = curatedImages.find(i => i.is_selected_reference || i.status === 'VERIFIED') || curatedImages[0];
    }
    
    updateActiveProduct({
      currentStage: 2,
      best_reference: selectedRef,
      selected_reference: selectedRef
    });
    setCurrentStage(2); // Go to Image Approval Stage
  };

  const researchSummary = {
    total_retrieved: activeProduct?.researchSummary?.total_retrieved ?? curatedImages.length,
    duplicates_removed: activeProduct?.researchSummary?.duplicates_removed ?? (activeProduct?.duplicates_removed || 0),
    verified_count: curatedImages.length,
    selected_reference: (activeProduct?.best_reference && curatedImages.length > 0) ? 1 : (curatedImages.length > 0 ? 1 : 0)
  };

  // Only showcase accepted/verified images. Never showcase rejected images.
  // When actively running/scraping, do not display preloaded/stale images.
  const filteredImages = React.useMemo(() => {
    if (isRunning) return [];
    return curatedImages;
  }, [isRunning, curatedImages]);

  return (
    <div className="max-w-6xl mx-auto p-4 md:p-6 space-y-5">
      {/* 1. Research Overview & Statistics Header */}
      <div className="tailadmin-card p-5 bg-white dark:bg-[#131E3D] border-brand-500/20 shadow-xs">
        <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4 pb-4 border-b border-[#E2E8F0] dark:border-[#1E2C52]">
          <div>
            <div className="flex items-center gap-2 mb-1">
              <span className="px-2.5 py-0.5 rounded-full text-xs font-bold uppercase tracking-wider bg-brand-50 text-brand-600 dark:bg-brand-500/20 dark:text-brand-400 border border-brand-200 dark:border-brand-500/30">
                Phase 2: Research
              </span>
              <h1 className="text-base font-bold text-[#1C2434] dark:text-white">
                Autonomous Multi-Source Reference Discovery
              </h1>
            </div>
            <p className="text-xs text-[#64748B] dark:text-[#8D9CB8]">
              Decoupled background worker with DINOv2 visual deduplication and manufacturer identity corroboration.
            </p>
          </div>

          <div className="flex items-center gap-2 text-xs">
            {isRunning ? (
              <div className="flex items-center gap-2 px-3 py-1.5 rounded-xl bg-brand-50 dark:bg-brand-950/40 border border-brand-200 dark:border-brand-800 text-brand-700 dark:text-brand-300 font-semibold">
                <Loader2 className="w-3.5 h-3.5 animate-spin text-brand-500" />
                <span>Active Job ({activeResearchJob?.executionTime || '0s'})</span>
              </div>
            ) : isFailed ? (
              <div className="flex items-center gap-2 px-3 py-1.5 rounded-xl bg-rose-50 dark:bg-rose-950/40 border border-rose-200 dark:border-rose-800 text-rose-700 dark:text-rose-300 font-semibold">
                <AlertTriangle className="w-3.5 h-3.5 text-rose-500" />
                <span>Job Failed</span>
              </div>
            ) : isCancelled ? (
              <div className="flex items-center gap-2 px-3 py-1.5 rounded-xl bg-slate-100 dark:bg-slate-800 border border-slate-300 dark:border-slate-700 text-slate-700 dark:text-slate-300 font-semibold">
                <Ban className="w-3.5 h-3.5 text-slate-500" />
                <span>Job Cancelled</span>
              </div>
            ) : (
              <div className="flex items-center gap-2 px-3 py-1.5 rounded-xl bg-emerald-50 dark:bg-emerald-950/40 border border-emerald-200 dark:border-emerald-800/60 text-emerald-800 dark:text-emerald-300 font-semibold">
                <Clock className="w-3.5 h-3.5 text-emerald-600 dark:text-emerald-400" />
                <span>{activeProduct?.executionTime ? `Completed in ${activeProduct.executionTime}` : 'Research Ready'}</span>
              </div>
            )}
          </div>
        </div>

        {/* 2. Structured Summary Metrics */}
        <div className="pt-4 grid grid-cols-2 sm:grid-cols-4 gap-3">
          <div className="p-3 rounded-xl bg-[#F8FAFC] dark:bg-[#0F1832] border border-[#E2E8F0] dark:border-[#1E2C52]">
            <span className="text-[11px] text-[#64748B] dark:text-[#8D9CB8] block">Total Harvested</span>
            <span className="text-lg font-bold text-[#1C2434] dark:text-white">{researchSummary.total_retrieved}</span>
          </div>

          <div className="p-3 rounded-xl bg-[#F8FAFC] dark:bg-[#0F1832] border border-[#E2E8F0] dark:border-[#1E2C52]">
            <span className="text-[11px] text-[#64748B] dark:text-[#8D9CB8] block">Duplicates Removed</span>
            <span className="text-lg font-bold text-amber-600 dark:text-amber-400">{researchSummary.duplicates_removed}</span>
          </div>

          <div className="p-3 rounded-xl bg-[#F8FAFC] dark:bg-[#0F1832] border border-[#E2E8F0] dark:border-[#1E2C52]">
            <span className="text-[11px] text-[#64748B] dark:text-[#8D9CB8] block">Accepted Candidates</span>
            <span className="text-lg font-bold text-emerald-600 dark:text-emerald-400">{researchSummary.verified_count}</span>
          </div>

          <div className="p-3 rounded-xl bg-brand-50/60 dark:bg-brand-500/15 border border-brand-200 dark:border-brand-500/30">
            <span className="text-[11px] text-brand-700 dark:text-brand-300 block font-semibold">Selected Reference</span>
            <span className="text-lg font-bold text-brand-600 dark:text-brand-400">{researchSummary.selected_reference}</span>
          </div>
        </div>
      </div>

      {/* 2B. Live Active Job / Running Banner */}
      {isRunning && (
        <div className="tailadmin-card p-6 bg-brand-50/40 dark:bg-brand-950/20 border-2 border-brand-500/30 shadow-sm space-y-4">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-xl bg-brand-500 text-white flex items-center justify-center shadow-md shadow-brand-500/20">
                <Loader2 className="w-5 h-5 animate-spin" />
              </div>
              <div>
                <h2 className="text-sm font-bold text-[#1C2434] dark:text-white">
                  Research Running in Background
                </h2>
                <p className="text-xs text-[#64748B] dark:text-[#8D9CB8]">
                  Current Phase: <strong className="text-brand-600 dark:text-brand-400">{activeResearchJob?.current_phase || 'Processing...'}</strong>
                </p>
              </div>
            </div>

            <div className="flex items-center gap-3">
              <span className="font-mono text-xs font-semibold text-[#1C2434] dark:text-white">
                Elapsed: {activeResearchJob?.executionTime || '0s'}
              </span>
              <button
                onClick={() => cancelResearch(activeProduct?.id)}
                className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold text-rose-600 bg-rose-50 dark:bg-rose-950/40 hover:bg-rose-100 rounded-xl border border-rose-200 dark:border-rose-800 transition-colors"
              >
                <Ban className="w-3.5 h-3.5" />
                <span>Cancel Job</span>
              </button>
            </div>
          </div>

          {/* Progress Bar */}
          <div className="w-full bg-[#E2E8F0] dark:bg-[#1E2C52] h-2 rounded-full overflow-hidden">
            <div 
              className="bg-brand-500 h-full rounded-full transition-all duration-300"
              style={{ width: `${Math.round((activeResearchJob?.progress || 0.1) * 100)}%` }}
            ></div>
          </div>
        </div>
      )}

      {/* 2C. Failed or Cancelled State Card */}
      {(isFailed || isCancelled) && (
        <div className={`tailadmin-card p-6 border ${isFailed ? 'bg-rose-50/20 border-rose-200 dark:border-rose-900/50' : 'bg-slate-50 dark:bg-slate-900/40 border-slate-200 dark:border-slate-800'} shadow-sm`}>
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
            <div className="flex items-center gap-3">
              <div className={`w-10 h-10 rounded-xl flex items-center justify-center ${isFailed ? 'bg-rose-100 text-rose-600' : 'bg-slate-200 text-slate-600'}`}>
                {isFailed ? <AlertTriangle className="w-5 h-5" /> : <Ban className="w-5 h-5" />}
              </div>
              <div>
                <h2 className="text-sm font-bold text-[#1C2434] dark:text-white">
                  {isFailed ? 'Research Job Failed' : 'Research Job Cancelled'}
                </h2>
                <p className="text-xs text-[#64748B] dark:text-[#8D9CB8]">
                  {activeResearchJob?.error || activeResearchJob?.cancel_reason || 'Job ended before completion.'}
                </p>
              </div>
            </div>

            <button
              onClick={() => retryResearch(activeProduct?.id)}
              className="flex items-center gap-2 px-5 py-2 text-xs font-semibold text-white bg-brand-500 hover:bg-brand-600 rounded-xl shadow-md shadow-brand-500/25 transition-all"
            >
              <RotateCcw className="w-3.5 h-3.5" />
              <span>Retry Research</span>
            </button>
          </div>
        </div>
      )}

      {/* 3. Candidate Images Gallery */}
      <div className="tailadmin-card p-6 bg-white dark:bg-[#131E3D]">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-4 mb-5 border-b border-[#E2E8F0] dark:border-[#1E2C52]">
          {/* Header */}
          <div className="flex items-center gap-2">
            <span className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-semibold bg-emerald-600 text-white shadow-xs">
              <ShieldCheck className="w-3.5 h-3.5" />
              <span>Accepted Candidates ({curatedImages.length})</span>
            </span>
          </div>

          <span className="text-xs text-[#64748B] dark:text-[#8D9CB8]">
            Product Identity: <strong className="text-[#1C2434] dark:text-white">{activeProduct?.name || 'Asset'}</strong> ({activeProduct?.modelNumber || activeProduct?.id || 'SKU'})
          </span>
        </div>

        {/* Grid of Candidates */}
        {filteredImages.length === 0 ? (
          <div className="p-8 text-center border-2 border-dashed border-[#CBD5E1] dark:border-[#1E2C52] rounded-2xl mb-6 bg-[#F8FAFC]/50 dark:bg-[#0F1832]/40">
            {isRunning ? (
              <div className="flex flex-col items-center justify-center space-y-2">
                <Loader2 className="w-8 h-8 text-brand-500 animate-spin" />
                <p className="text-xs font-semibold text-[#1C2434] dark:text-white">
                  Discovering and verifying reference candidates in background...
                </p>
                <p className="text-[11px] text-[#64748B] dark:text-[#8D9CB8]">
                  Results will appear once verification completes.
                </p>
              </div>
            ) : (
              <div className="flex flex-col items-center justify-center space-y-1">
                <ImageIcon className="w-8 h-8 text-[#94A3B8] mx-auto mb-2" />
                <p className="text-xs font-semibold text-[#1C2434] dark:text-white">
                  No accepted candidates available yet.
                </p>
                <p className="text-[11px] text-[#64748B] dark:text-[#8D9CB8]">
                  You can upload a reference image directly or run autonomous discovery.
                </p>
              </div>
            )}
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4 mb-6">
            {filteredImages.map((img, idx) => {
              const isSelectedRef = (img.is_selected_reference || (activeProduct?.best_reference && (activeProduct.best_reference.id === img.id || activeProduct.best_reference.url === img.url)));

              return (
                <div
                  key={img.id || idx}
                  className={`rounded-2xl border p-3 flex flex-col justify-between transition-all ${
                    isSelectedRef
                      ? 'border-brand-500 bg-brand-50/20 dark:bg-brand-500/10 ring-2 ring-brand-500/20'
                      : 'border-[#E2E8F0] dark:border-[#1E2C52] bg-white dark:bg-[#0F1832]/60'
                  }`}
                >
                  <div>
                    {/* Candidate Image Preview */}
                    <div className="relative aspect-4/3 rounded-xl overflow-hidden bg-[#F8FAFC] dark:bg-[#0B1120] mb-2.5 flex items-center justify-center">
                      <img
                        src={img.url}
                        alt={img.title || 'Candidate'}
                        className="w-full h-full object-cover"
                      />

                      {/* Semantic Status Badge */}
                      <div className="absolute top-2 right-2">
                        {isSelectedRef ? (
                          <span className="px-2 py-0.5 rounded-md text-[10px] font-bold bg-brand-500 text-white shadow-xs">
                            Selected Reference
                          </span>
                        ) : (
                          <span className="px-2 py-0.5 rounded-md text-[10px] font-bold bg-emerald-500 text-white shadow-xs">
                            Accepted
                          </span>
                        )}
                      </div>

                      {/* Viewpoint Tag */}
                      {img.angle && (
                        <div className="absolute bottom-2 left-2">
                          <span className="px-2 py-0.5 rounded-md text-[10px] font-semibold bg-black/75 text-white backdrop-blur-xs">
                            {img.angle}
                          </span>
                        </div>
                      )}
                    </div>

                    {/* Information */}
                    <p className="text-xs font-semibold text-[#1C2434] dark:text-white truncate" title={img.title}>
                      {img.title || 'Candidate Image'}
                    </p>
                    <p className="text-[11px] text-[#64748B] dark:text-[#8D9CB8] truncate mt-0.5">
                      {img.source || 'Discovered via web retrieval'}
                    </p>
                  </div>
                </div>
              );
            })}
          </div>
        )}

        {/* Section: Related URLs */}
        {urls.length > 0 && (
          <div className="mb-6 pt-4 border-t border-[#E2E8F0] dark:border-[#1E2C52]">
            <span className="text-xs font-bold uppercase tracking-wider text-[#1C2434] dark:text-white block mb-3">
              Technical Datasheets &amp; Sources ({urls.length})
            </span>
            <div className="space-y-1.5">
              {urls.slice(0, 4).map((item, idx) => (
                <div
                  key={idx}
                  className="flex items-center justify-between p-2.5 rounded-xl border border-[#E2E8F0] dark:border-[#1E2C52] bg-[#F8FAFC]/50 dark:bg-[#0F1832]/60 text-xs"
                >
                  <span className="font-semibold text-[#1C2434] dark:text-white truncate mr-2">
                    {item.title}
                  </span>
                  <a
                    href={item.url}
                    target="_blank"
                    rel="noreferrer"
                    className="text-[11px] text-brand-600 dark:text-brand-400 hover:underline flex items-center gap-1 flex-shrink-0"
                  >
                    <span>View Datasheet</span>
                    <ExternalLink className="w-2.5 h-2.5" />
                  </a>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Footer Navigation */}
        <div className="flex items-center justify-between pt-4 border-t border-[#E2E8F0] dark:border-[#1E2C52]">
          <button
            onClick={() => setCurrentStage(0)}
            className="flex items-center gap-2 px-4 py-2 text-xs font-semibold text-[#64748B] dark:text-[#8D9CB8] bg-white dark:bg-[#131E3D] hover:bg-[#F1F5F9] dark:hover:bg-[#172449] border border-[#CBD5E1] dark:border-[#1E2C52] rounded-xl transition-colors"
          >
            <ArrowLeft className="w-3.5 h-3.5" />
            <span>Back to Input</span>
          </button>

          <button
            onClick={handleProceedToApproval}
            disabled={curatedImages.length === 0 || isRunning}
            className="flex items-center gap-2 px-6 py-2.5 text-xs font-semibold text-white bg-brand-500 hover:bg-brand-600 disabled:bg-slate-400 dark:disabled:bg-slate-700 disabled:cursor-not-allowed rounded-xl shadow-md shadow-brand-500/25 transition-all hover:scale-[1.01] active:scale-[0.99]"
          >
            <span>Proceed to Image Approval</span>
            <ArrowRight className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>
    </div>
  );
}
