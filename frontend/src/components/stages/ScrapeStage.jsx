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
  ExternalLink
} from 'lucide-react';

export default function ScrapeStage() {
  const { activeProduct, updateActiveProduct, setCurrentStage, isProcessing } = useProducts();

  const [images, setImages] = useState(activeProduct?.scrapedImages || []);
  const [urls, setUrls] = useState(activeProduct?.relatedUrls || []);
  const [activeFilter, setActiveFilter] = useState('all'); // 'all', 'verified', 'rejected'

  useEffect(() => {
    if (activeProduct) {
      setImages(activeProduct.scrapedImages || []);
      setUrls(activeProduct.relatedUrls || []);
    }
  }, [activeProduct?.id, activeProduct?.scrapedImages]);

  const handleProceedToApproval = () => {
    // Select the best verified reference image if not already selected
    let selectedRef = activeProduct?.best_reference;
    if (!selectedRef && images.length > 0) {
      selectedRef = images.find(i => i.is_selected_reference || i.status === 'VERIFIED') || images[0];
    }
    
    updateActiveProduct({
      currentStage: 2,
      best_reference: selectedRef,
      selected_reference: selectedRef
    });
    setCurrentStage(2); // Go to Image Approval Stage
  };

  const researchSummary = activeProduct?.researchSummary || {
    total_retrieved: images.length || 0,
    duplicates_removed: activeProduct?.duplicates_removed || 0,
    rejected_as_irrelevant: images.filter(i => i.status === 'REJECTED').length || 0,
    verified_count: images.filter(i => i.status === 'VERIFIED' || i.is_selected_reference).length || (images.length > 0 ? 1 : 0),
    selected_reference: activeProduct?.best_reference ? 1 : (images.length > 0 ? 1 : 0)
  };

  const filteredImages = images.filter(img => {
    if (activeFilter === 'verified') return img.status === 'VERIFIED' || img.is_selected_reference;
    if (activeFilter === 'rejected') return img.status === 'REJECTED';
    return true;
  });

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
                Automated Reference Discovery &amp; Verification
              </h1>
            </div>
            <p className="text-xs text-[#64748B] dark:text-[#8D9CB8]">
              Product-ID-first retrieval, DINOv2 visual deduplication, and seed-image cross-verification.
            </p>
          </div>

          <div className="flex items-center gap-2 text-xs">
            <div className="flex items-center gap-2 px-3 py-1.5 rounded-xl bg-emerald-50 dark:bg-emerald-950/40 border border-emerald-200 dark:border-emerald-800/60 text-emerald-800 dark:text-emerald-300 font-semibold">
              <Clock className="w-3.5 h-3.5 text-emerald-600 dark:text-emerald-400" />
              <span>{activeProduct?.executionTime ? `Completed in ${activeProduct.executionTime}` : 'Research Ready'}</span>
            </div>
          </div>
        </div>

        {/* 2. Structured Summary Metrics */}
        <div className="pt-4 grid grid-cols-2 sm:grid-cols-5 gap-3">
          <div className="p-3 rounded-xl bg-[#F8FAFC] dark:bg-[#0F1832] border border-[#E2E8F0] dark:border-[#1E2C52]">
            <span className="text-[11px] text-[#64748B] dark:text-[#8D9CB8] block">Total Retrieved</span>
            <span className="text-lg font-bold text-[#1C2434] dark:text-white">{researchSummary.total_retrieved}</span>
          </div>

          <div className="p-3 rounded-xl bg-[#F8FAFC] dark:bg-[#0F1832] border border-[#E2E8F0] dark:border-[#1E2C52]">
            <span className="text-[11px] text-[#64748B] dark:text-[#8D9CB8] block">Duplicates Removed</span>
            <span className="text-lg font-bold text-amber-600 dark:text-amber-400">{researchSummary.duplicates_removed}</span>
          </div>

          <div className="p-3 rounded-xl bg-[#F8FAFC] dark:bg-[#0F1832] border border-[#E2E8F0] dark:border-[#1E2C52]">
            <span className="text-[11px] text-[#64748B] dark:text-[#8D9CB8] block">Rejected as Irrelevant</span>
            <span className="text-lg font-bold text-rose-600 dark:text-rose-400">{researchSummary.rejected_as_irrelevant}</span>
          </div>

          <div className="p-3 rounded-xl bg-[#F8FAFC] dark:bg-[#0F1832] border border-[#E2E8F0] dark:border-[#1E2C52]">
            <span className="text-[11px] text-[#64748B] dark:text-[#8D9CB8] block">Verified Candidates</span>
            <span className="text-lg font-bold text-emerald-600 dark:text-emerald-400">{researchSummary.verified_count}</span>
          </div>

          <div className="p-3 rounded-xl bg-brand-50/60 dark:bg-brand-500/15 border border-brand-200 dark:border-brand-500/30">
            <span className="text-[11px] text-brand-700 dark:text-brand-300 block font-semibold">Selected Reference</span>
            <span className="text-lg font-bold text-brand-600 dark:text-brand-400">{researchSummary.selected_reference}</span>
          </div>
        </div>
      </div>

      {/* 3. Candidate Images Gallery */}
      <div className="tailadmin-card p-6 bg-white dark:bg-[#131E3D]">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-4 mb-5 border-b border-[#E2E8F0] dark:border-[#1E2C52]">
          {/* Filter Tabs */}
          <div className="flex items-center gap-2">
            <button
              onClick={() => setActiveFilter('all')}
              className={`px-3 py-1.5 rounded-xl text-xs font-semibold transition-all ${
                activeFilter === 'all'
                  ? 'bg-brand-500 text-white shadow-xs'
                  : 'bg-[#F1F5F9] dark:bg-[#0F1832] text-[#64748B] dark:text-[#8D9CB8] hover:bg-[#E2E8F0] dark:hover:bg-[#172449]'
              }`}
            >
              All Candidates ({images.length})
            </button>
            <button
              onClick={() => setActiveFilter('verified')}
              className={`px-3 py-1.5 rounded-xl text-xs font-semibold transition-all ${
                activeFilter === 'verified'
                  ? 'bg-emerald-600 text-white shadow-xs'
                  : 'bg-[#F1F5F9] dark:bg-[#0F1832] text-[#64748B] dark:text-[#8D9CB8] hover:bg-[#E2E8F0] dark:hover:bg-[#172449]'
              }`}
            >
              Verified ({images.filter(i => i.status === 'VERIFIED' || i.is_selected_reference).length})
            </button>
            <button
              onClick={() => setActiveFilter('rejected')}
              className={`px-3 py-1.5 rounded-xl text-xs font-semibold transition-all ${
                activeFilter === 'rejected'
                  ? 'bg-rose-600 text-white shadow-xs'
                  : 'bg-[#F1F5F9] dark:bg-[#0F1832] text-[#64748B] dark:text-[#8D9CB8] hover:bg-[#E2E8F0] dark:hover:bg-[#172449]'
              }`}
            >
              Rejected ({images.filter(i => i.status === 'REJECTED').length})
            </button>
          </div>

          <span className="text-xs text-[#64748B] dark:text-[#8D9CB8]">
            Product Identity: <strong className="text-[#1C2434] dark:text-white">{activeProduct?.name || 'Asset'}</strong> ({activeProduct?.modelNumber || activeProduct?.id || 'SKU'})
          </span>
        </div>

        {/* Grid of Clean Candidates */}
        {filteredImages.length === 0 ? (
          <div className="p-8 text-center border-2 border-dashed border-[#CBD5E1] dark:border-[#1E2C52] rounded-2xl mb-6 bg-[#F8FAFC]/50 dark:bg-[#0F1832]/40">
            <ImageIcon className="w-8 h-8 text-[#94A3B8] mx-auto mb-2" />
            <p className="text-xs font-semibold text-[#1C2434] dark:text-white">
              No candidate images match this filter.
            </p>
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4 mb-6">
            {filteredImages.map((img, idx) => {
              const isSelectedRef = img.is_selected_reference || (idx === 0 && img.status !== 'REJECTED');
              const isVerified = img.status === 'VERIFIED' || isSelectedRef;
              const isRejected = img.status === 'REJECTED';

              return (
                <div
                  key={img.id || idx}
                  className={`rounded-2xl border p-3 flex flex-col justify-between transition-all ${
                    isSelectedRef
                      ? 'border-brand-500 bg-brand-50/20 dark:bg-brand-500/10 ring-2 ring-brand-500/20'
                      : isRejected
                      ? 'border-rose-200 dark:border-rose-900/40 bg-rose-50/10 dark:bg-rose-950/20 opacity-70'
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
                        ) : isVerified ? (
                          <span className="px-2 py-0.5 rounded-md text-[10px] font-bold bg-emerald-500 text-white shadow-xs">
                            Verified
                          </span>
                        ) : isRejected ? (
                          <span className="px-2 py-0.5 rounded-md text-[10px] font-bold bg-rose-500 text-white shadow-xs">
                            Rejected
                          </span>
                        ) : (
                          <span className="px-2 py-0.5 rounded-md text-[10px] font-bold bg-slate-700 text-white shadow-xs">
                            Candidate
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

                    {/* Verification Reason */}
                    {img.rejection_reason && (
                      <p className="text-[10px] text-rose-600 dark:text-rose-400 mt-1">
                        Reason: {img.rejection_reason}
                      </p>
                    )}
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
            className="flex items-center gap-2 px-6 py-2.5 text-xs font-semibold text-white bg-brand-500 hover:bg-brand-600 rounded-xl shadow-md shadow-brand-500/25 transition-all hover:scale-[1.01] active:scale-[0.99]"
          >
            <span>Proceed to Image Approval</span>
            <ArrowRight className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>
    </div>
  );
}
