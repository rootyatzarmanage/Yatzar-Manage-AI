import React, { useState, useEffect } from 'react';
import { useProducts } from '../../context/ProductContext';
import { 
  CheckCircle, 
  Sparkles, 
  ArrowLeft, 
  ArrowRight, 
  ShieldCheck, 
  Box, 
  Check, 
  Image as ImageIcon,
  Layers,
  Cpu,
  MousePointerClick,
  Filter,
  Eye,
  Info,
  XCircle,
  ChevronDown,
  ChevronUp,
  AlertTriangle,
  Ban
} from 'lucide-react';

export default function ImageApprovalStage() {
  const { activeProduct, updateActiveProduct, setCurrentStage } = useProducts();

  // Curated candidate pool: ONLY candidates that survived the automatic filtering pipeline (plus seed image if provided)
  const candidatePool = React.useMemo(() => {
    const list = [...(activeProduct?.scrapedImages || [])].filter(
      img => img.status !== 'REJECTED' && img.status !== 'MANUALLY_REJECTED'
    );
    
    // If there is a seed/input thumbnail not already present in list and not rejected, include it
    if (activeProduct?.thumbnail && !list.some(img => img.url === activeProduct.thumbnail)) {
      list.unshift({
        id: 'seed-input-0',
        url: activeProduct.thumbnail,
        title: activeProduct.name ? `${activeProduct.name} (Seed Image)` : 'Seed Product Image',
        source: 'User Upload / Seed Input',
        angle: 'Front / Canonical',
        status: 'VERIFIED',
        is_seed: true
      });
    }

    return list;
  }, [activeProduct?.scrapedImages, activeProduct?.thumbnail, activeProduct?.name]);

  // Determine initial selected reference:
  // 1. Explicitly chosen reference in activeProduct (if still in curated pool)
  // 2. Best reference from research pipeline
  // 3. First verified candidate in pool
  // 4. First available candidate
  const getInitialSelection = () => {
    if (activeProduct?.selected_reference) {
      const match = candidatePool.find(
        c => c.url === activeProduct.selected_reference.url || c.id === activeProduct.selected_reference.id
      );
      if (match) return match;
    }
    if (activeProduct?.best_reference) {
      const match = candidatePool.find(
        c => c.url === activeProduct.best_reference.url || c.id === activeProduct.best_reference.id
      );
      if (match) return match;
    }
    const verified = candidatePool.find(c => c.status === 'VERIFIED' || c.is_selected_reference);
    if (verified) return verified;
    return candidatePool[0] || null;
  };

  const [selectedCandidate, setSelectedCandidate] = useState(getInitialSelection);
  const [filterMode, setFilterMode] = useState('all'); // 'all', 'verified'
  const [showRejectedAudit, setShowRejectedAudit] = useState(false);

  // Update selected candidate when active product or candidate pool changes
  useEffect(() => {
    const current = getInitialSelection();
    setSelectedCandidate(current);
  }, [activeProduct?.id, candidatePool.length]);

  const handleSelectCandidate = (candidate) => {
    if (!candidate || candidate.status === 'REJECTED' || candidate.status === 'MANUALLY_REJECTED') return;
    
    setSelectedCandidate(candidate);
    
    // Check if the selection has actually changed
    const prevUrl = activeProduct?.selected_reference?.url;
    const newUrl = candidate?.url;
    const isDifferent = prevUrl !== newUrl;

    // Immediately persist user's manual selection to activeProduct
    updateActiveProduct({
      selected_reference: candidate,
      is_manual_selection: true,
      // If reference changed, invalidate cached model stats to prevent stale results
      ...(isDifferent ? {
        modelUrl: null,
        modelPath: null,
        meshStats: null,
        reconstructionDuration: null,
        reconstruction_duration_sec: null,
        validationResult: null,
        renderedViews: null,
        renderedDimensions: null,
        referenceSheetGeneratedAt: null
      } : {})
    });
  };

  // Manual Candidate Rejection Handler: moves candidate from curated pool to rejected pool with metadata
  const handleRejectCandidate = (candidateToReject, e) => {
    if (e) e.stopPropagation();
    if (!candidateToReject) return;

    const rejectedItem = {
      ...candidateToReject,
      status: 'MANUALLY_REJECTED',
      rejection_reason: 'manual rejection',
      rejected_by: 'user',
      rejected_at: new Date().toISOString()
    };

    // Remove from scrapedImages and add to rejectedImages
    const remainingCurated = (activeProduct?.scrapedImages || []).filter(
      img => img.id !== candidateToReject.id && img.url !== candidateToReject.url
    );
    const updatedRejected = [
      rejectedItem,
      ...(activeProduct?.rejectedImages || []).filter(
        img => img.id !== candidateToReject.id && img.url !== candidateToReject.url
      )
    ];

    // If the rejected candidate was currently selected, pick a new one
    const wasSelected = selectedCandidate?.id === candidateToReject.id || selectedCandidate?.url === candidateToReject.url;
    const nextSelected = wasSelected ? (remainingCurated[0] || null) : selectedCandidate;

    setSelectedCandidate(nextSelected);

    updateActiveProduct({
      scrapedImages: remainingCurated,
      rejectedImages: updatedRejected,
      selected_reference: nextSelected,
      best_reference: nextSelected,
      ...(wasSelected ? {
        modelUrl: null,
        modelPath: null,
        meshStats: null,
        reconstructionDuration: null,
        reconstruction_duration_sec: null,
        validationResult: null,
        renderedViews: null,
        renderedDimensions: null,
        referenceSheetGeneratedAt: null
      } : {})
    });
  };

  const handleProceedTo3D = () => {
    if (!selectedCandidate) return;
    if (selectedCandidate.status === 'REJECTED' || selectedCandidate.status === 'MANUALLY_REJECTED') return;

    const prevUrl = activeProduct?.selected_reference?.url;
    const newUrl = selectedCandidate.url;
    const isDifferent = prevUrl !== newUrl;

    updateActiveProduct({
      currentStage: 3,
      selected_reference: selectedCandidate,
      best_reference: selectedCandidate,
      is_manual_selection: true,
      ...(isDifferent ? {
        modelUrl: null,
        modelPath: null,
        meshStats: null,
        reconstructionDuration: null,
        reconstruction_duration_sec: null,
        validationResult: null,
        renderedViews: null,
        renderedDimensions: null,
        referenceSheetGeneratedAt: null
      } : {})
    });

    setCurrentStage(3); // Go to 3D Generate
  };

  const filteredCandidates = candidatePool.filter(item => {
    if (filterMode === 'verified') {
      return item.status === 'VERIFIED' || item.is_selected_reference || item.id === selectedCandidate?.id;
    }
    return true;
  });

  const rejectedList = activeProduct?.rejectedImages || [];

  return (
    <div className="max-w-6xl mx-auto p-4 md:p-6 space-y-6">
      {/* 1. Header Card */}
      <div className="tailadmin-card p-5 bg-white dark:bg-[#131E3D] border-brand-500/20 shadow-xs">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <div>
            <div className="flex items-center gap-2 mb-1">
              <span className="px-2.5 py-0.5 rounded-full text-xs font-bold uppercase tracking-wider bg-emerald-50 text-emerald-600 dark:bg-emerald-950/60 dark:text-emerald-400 border border-emerald-200 dark:border-emerald-800">
                Phase 3: Image Approval &amp; Reference Selection
              </span>
              <h1 className="text-base font-bold text-[#1C2434] dark:text-white">
                Select Primary 3D Reference Image
              </h1>
            </div>
            <p className="text-xs text-[#64748B] dark:text-[#8D9CB8]">
              Curated candidate pool filtered by DINOv2 visual deduplication and quality triage. Select your authoritative reference for TripoSR.
            </p>
          </div>

          <div className="flex items-center gap-2">
            <span className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-brand-50 dark:bg-brand-950/40 text-brand-700 dark:text-brand-300 text-xs font-semibold border border-brand-200 dark:border-brand-800">
              <MousePointerClick className="w-3.5 h-3.5" /> Interactive Manual Selection Active
            </span>
          </div>
        </div>
      </div>

      {/* 2. Top Split View: Selected Reference Hero & Metadata */}
      {selectedCandidate ? (
        <div className="tailadmin-card p-6 bg-white dark:bg-[#131E3D] border-2 border-brand-500/40 shadow-md">
          <div className="grid grid-cols-1 md:grid-cols-12 gap-6 items-center">
            {/* Primary Reference Image Preview */}
            <div className="md:col-span-5 relative aspect-4/3 rounded-2xl overflow-hidden bg-slate-900 border border-[#E2E8F0] dark:border-[#1E2C52] shadow-sm flex items-center justify-center group">
              <img
                src={selectedCandidate.url}
                alt={selectedCandidate.title || 'Selected Reference'}
                className="w-full h-full object-contain p-2 transition-transform duration-300 group-hover:scale-105"
              />

              <div className="absolute top-3 left-3">
                <span className="px-2.5 py-1 rounded-lg text-xs font-bold bg-brand-500 text-white shadow-xs flex items-center gap-1.5">
                  <Sparkles className="w-3.5 h-3.5" /> Active Primary Reference
                </span>
              </div>

              {selectedCandidate.angle && (
                <div className="absolute bottom-3 right-3">
                  <span className="px-2 py-0.5 rounded-md text-[11px] font-semibold bg-black/80 text-white backdrop-blur-xs">
                    Viewpoint: {selectedCandidate.angle}
                  </span>
                </div>
              )}
            </div>

            {/* Target Product & Selection Status */}
            <div className="md:col-span-7 space-y-4">
              <div>
                <span className="text-[11px] uppercase font-bold text-[#64748B] dark:text-[#8D9CB8] tracking-wider block">
                  Authoritative Input for TripoSR
                </span>
                <h2 className="text-lg font-bold text-[#1C2434] dark:text-white mt-0.5">
                  {selectedCandidate.title || activeProduct?.name || 'Product Asset'}
                </h2>
                <p className="text-xs font-mono text-brand-600 dark:text-brand-400 mt-0.5">
                  SKU / Model: {activeProduct?.modelNumber || activeProduct?.id || 'PROD-01'}
                </p>
              </div>

              {/* Verification Checklist */}
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5 p-4 rounded-xl bg-[#F8FAFC] dark:bg-[#0F1832] border border-[#E2E8F0] dark:border-[#1E2C52] text-xs">
                <div className="flex items-center gap-2 text-[#1C2434] dark:text-white font-medium">
                  <Check className="w-4 h-4 text-emerald-500 flex-shrink-0" />
                  <span>Manual Selection Authoritative</span>
                </div>
                <div className="flex items-center gap-2 text-[#1C2434] dark:text-white font-medium">
                  <Check className="w-4 h-4 text-emerald-500 flex-shrink-0" />
                  <span>Visual Quality Verified</span>
                </div>
                <div className="flex items-center gap-2 text-[#1C2434] dark:text-white font-medium">
                  <Check className="w-4 h-4 text-emerald-500 flex-shrink-0" />
                  <span>Single-View Conditioning Ready</span>
                </div>
                <div className="flex items-center gap-2 text-[#1C2434] dark:text-white font-medium">
                  <Check className="w-4 h-4 text-emerald-500 flex-shrink-0" />
                  <span>TripoSR CUDA Pipeline Linked</span>
                </div>
              </div>

              <div className="flex items-center justify-between text-[11px] text-[#64748B] dark:text-[#8D9CB8] pt-1">
                <span>Provenance: <strong>{selectedCandidate.source || 'Curated Reference Pool'}</strong></span>
                <span className="font-mono text-xs text-brand-600 dark:text-brand-400">ID: {selectedCandidate.id || 'ref-selected'}</span>
              </div>
            </div>
          </div>
        </div>
      ) : (
        <div className="tailadmin-card p-8 bg-white dark:bg-[#131E3D] text-center space-y-2">
          <ImageIcon className="w-10 h-10 text-[#94A3B8] mx-auto" />
          <h2 className="text-sm font-bold text-[#1C2434] dark:text-white">No Reference Image Selected</h2>
          <p className="text-xs text-[#64748B] dark:text-[#8D9CB8]">
            Please select one reference image from the curated pool below to proceed with 3D generation.
          </p>
        </div>
      )}

      {/* 3. Curated Candidate Reference Pool Gallery */}
      <div className="tailadmin-card p-6 bg-white dark:bg-[#131E3D] space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-3 border-b border-[#E2E8F0] dark:border-[#1E2C52]">
          <div>
            <h3 className="text-sm font-bold text-[#1C2434] dark:text-white flex items-center gap-2">
              <Layers className="w-4 h-4 text-brand-500" />
              <span>Curated Reference Pool</span>
              <span className="text-xs font-normal text-[#64748B] dark:text-[#8D9CB8]">
                ({candidatePool.length} curated candidates)
              </span>
            </h3>
            <p className="text-xs text-[#64748B] dark:text-[#8D9CB8]">
              Automatic filters and DINOv2 deduplication applied. Only high-confidence candidates reach this showcase.
            </p>
          </div>

          {/* Filter Controls */}
          <div className="flex items-center gap-2">
            <button
              onClick={() => setFilterMode('all')}
              className={`px-3 py-1 rounded-lg text-xs font-semibold transition-colors ${
                filterMode === 'all'
                  ? 'bg-brand-500 text-white shadow-xs'
                  : 'bg-[#F1F5F9] dark:bg-[#0F1832] text-[#64748B] dark:text-[#8D9CB8] hover:bg-[#E2E8F0] dark:hover:bg-[#172449]'
              }`}
            >
              Curated Pool ({candidatePool.length})
            </button>
            <button
              onClick={() => setFilterMode('verified')}
              className={`px-3 py-1 rounded-lg text-xs font-semibold transition-colors ${
                filterMode === 'verified'
                  ? 'bg-emerald-600 text-white shadow-xs'
                  : 'bg-[#F1F5F9] dark:bg-[#0F1832] text-[#64748B] dark:text-[#8D9CB8] hover:bg-[#E2E8F0] dark:hover:bg-[#172449]'
              }`}
            >
              Verified ({candidatePool.filter(c => c.status === 'VERIFIED' || c.is_selected_reference).length})
            </button>
          </div>
        </div>

        {/* Candidate Grid */}
        {filteredCandidates.length === 0 ? (
          <div className="p-8 text-center border-2 border-dashed border-[#CBD5E1] dark:border-[#1E2C52] rounded-2xl bg-[#F8FAFC]/50 dark:bg-[#0F1832]/40">
            <ImageIcon className="w-8 h-8 text-[#94A3B8] mx-auto mb-2" />
            <p className="text-xs font-semibold text-[#1C2434] dark:text-white">
              No curated reference images available.
            </p>
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4 pt-2">
            {filteredCandidates.map((candidate, idx) => {
              const isSelected = selectedCandidate?.url === candidate.url || selectedCandidate?.id === candidate.id;
              const isVerified = candidate.status === 'VERIFIED' || candidate.is_selected_reference;

              return (
                <div
                  key={candidate.id || idx}
                  onClick={() => handleSelectCandidate(candidate)}
                  className={`group relative rounded-2xl border p-3 flex flex-col justify-between cursor-pointer transition-all duration-200 select-none ${
                    isSelected
                      ? 'border-brand-500 bg-brand-50/30 dark:bg-brand-500/15 ring-2 ring-brand-500 shadow-md transform -translate-y-0.5'
                      : 'border-[#E2E8F0] dark:border-[#1E2C52] bg-white dark:bg-[#0F1832]/60 hover:border-brand-300 dark:hover:border-brand-700/60 hover:shadow-xs'
                  }`}
                >
                  <div>
                    {/* Image Thumbnail Container */}
                    <div className="relative aspect-4/3 rounded-xl overflow-hidden bg-[#F8FAFC] dark:bg-[#0B1120] mb-2.5 flex items-center justify-center border border-[#E2E8F0]/80 dark:border-[#1E2C52]/80">
                      <img
                        src={candidate.url}
                        alt={candidate.title || `Candidate ${idx + 1}`}
                        className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-200"
                        loading="lazy"
                      />

                      {/* Top Selection & Verification Badges */}
                      <div className="absolute top-2 left-2 right-2 flex items-center justify-between pointer-events-none">
                        {isSelected ? (
                          <span className="px-2 py-0.5 rounded-md text-[10px] font-bold bg-brand-500 text-white shadow-xs flex items-center gap-1">
                            <Check className="w-3 h-3" /> Selected
                          </span>
                        ) : (
                          <span className="px-2 py-0.5 rounded-md text-[10px] font-medium bg-black/60 text-white backdrop-blur-xs group-hover:bg-brand-500 transition-colors">
                            Click to Select
                          </span>
                        )}

                        {isVerified && (
                          <span className="px-1.5 py-0.5 rounded-md text-[9px] font-bold bg-emerald-500/90 text-white shadow-xs">
                            Verified
                          </span>
                        )}
                      </div>

                      {/* Viewpoint / Angle Tag */}
                      {candidate.angle && (
                        <div className="absolute bottom-2 left-2 pointer-events-none">
                          <span className="px-2 py-0.5 rounded-md text-[10px] font-semibold bg-black/75 text-white backdrop-blur-xs">
                            {candidate.angle}
                          </span>
                        </div>
                      )}

                      {/* Dismiss/Reject button on card hover */}
                      <button
                        type="button"
                        onClick={(e) => handleRejectCandidate(candidate, e)}
                        className="absolute bottom-2 right-2 p-1 rounded-md bg-rose-600/85 hover:bg-rose-600 text-white text-[10px] opacity-0 group-hover:opacity-100 transition-opacity shadow-xs flex items-center gap-1"
                        title="Reject / Dismiss candidate"
                      >
                        <XCircle className="w-3 h-3" />
                        <span>Reject</span>
                      </button>
                    </div>

                    {/* Metadata & Title */}
                    <h4 className="text-xs font-bold text-[#1C2434] dark:text-white truncate" title={candidate.title}>
                      {candidate.title || `Candidate Image ${idx + 1}`}
                    </h4>
                    <p className="text-[11px] text-[#64748B] dark:text-[#8D9CB8] truncate mt-0.5">
                      {candidate.source || 'Curated Pool'}
                    </p>
                  </div>

                  {/* Footer Selection Radio / Button State */}
                  <div className="pt-3 mt-2 border-t border-[#E2E8F0] dark:border-[#1E2C52] flex items-center justify-between">
                    <span className="text-[10px] font-mono text-[#64748B] dark:text-[#8D9CB8]">
                      {candidate.id ? `ID: ${candidate.id.slice(0, 10)}` : `#${idx + 1}`}
                    </span>

                    <button
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation();
                        handleSelectCandidate(candidate);
                      }}
                      className={`text-[11px] font-semibold px-2.5 py-1 rounded-lg transition-all ${
                        isSelected
                          ? 'bg-brand-500 text-white shadow-xs'
                          : 'bg-[#F1F5F9] dark:bg-[#172449] text-[#64748B] dark:text-[#8D9CB8] group-hover:bg-brand-500 group-hover:text-white'
                      }`}
                    >
                      {isSelected ? 'Selected' : 'Use as Reference'}
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* 4. Collapsible Rejected Candidates Audit Section */}
      {rejectedList.length > 0 && (
        <div className="tailadmin-card p-4 bg-[#F8FAFC] dark:bg-[#0F1832] border border-[#E2E8F0] dark:border-[#1E2C52] rounded-2xl">
          <button
            onClick={() => setShowRejectedAudit(!showRejectedAudit)}
            className="w-full flex items-center justify-between text-xs font-bold text-[#64748B] dark:text-[#8D9CB8] hover:text-[#1C2434] dark:hover:text-white transition-colors"
          >
            <div className="flex items-center gap-2">
              <Ban className="w-4 h-4 text-rose-500" />
              <span>Rejected Candidates Audit ({rejectedList.length} preserved)</span>
              <span className="text-[11px] font-normal text-slate-400">
                (Excluded from initial showcase &amp; 3D generation)
              </span>
            </div>
            <div className="flex items-center gap-1">
              <span>{showRejectedAudit ? 'Hide Audit' : 'Show Audit'}</span>
              {showRejectedAudit ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
            </div>
          </button>

          {showRejectedAudit && (
            <div className="mt-4 pt-3 border-t border-[#E2E8F0] dark:border-[#1E2C52] grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
              {rejectedList.map((rej, idx) => (
                <div
                  key={rej.id || idx}
                  className="p-2.5 rounded-xl bg-white dark:bg-[#131E3D] border border-rose-200/60 dark:border-rose-900/40 flex items-center gap-3 text-xs"
                >
                  <div className="w-12 h-12 rounded-lg bg-slate-900 overflow-hidden flex-shrink-0 border border-slate-200 dark:border-slate-800">
                    <img src={rej.url} alt="Rejected" className="w-full h-full object-cover opacity-60" />
                  </div>
                  <div className="min-w-0 flex-1">
                    <p className="font-semibold text-[#1C2434] dark:text-white truncate" title={rej.title || rej.rejection_reason}>
                      {rej.title || `Rejected Candidate ${idx + 1}`}
                    </p>
                    <span className="inline-block px-1.5 py-0.5 mt-0.5 rounded text-[10px] font-mono bg-rose-50 dark:bg-rose-950/60 text-rose-600 dark:text-rose-400 border border-rose-200 dark:border-rose-900/60">
                      Reason: {rej.rejection_reason || rej.explanation || 'Filtered during quality evaluation'}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* 5. Action Navigation Footer */}
      <div className="tailadmin-card p-4 bg-white dark:bg-[#131E3D] flex items-center justify-between">
        <button
          onClick={() => setCurrentStage(1)}
          className="flex items-center gap-2 px-4 py-2.5 text-xs font-semibold text-[#64748B] dark:text-[#8D9CB8] bg-white dark:bg-[#131E3D] hover:bg-[#F1F5F9] dark:hover:bg-[#172449] border border-[#CBD5E1] dark:border-[#1E2C52] rounded-xl transition-colors"
        >
          <ArrowLeft className="w-3.5 h-3.5" />
          <span>Back to Research</span>
        </button>

        <div className="flex items-center gap-3">
          {!selectedCandidate && (
            <span className="text-xs text-rose-500 dark:text-rose-400 font-medium">
              Please select a reference image before proceeding
            </span>
          )}
          <button
            onClick={handleProceedTo3D}
            disabled={!selectedCandidate || selectedCandidate.status === 'REJECTED' || selectedCandidate.status === 'MANUALLY_REJECTED'}
            className="flex items-center gap-2 px-6 py-2.5 text-xs font-semibold text-white bg-brand-500 hover:bg-brand-600 disabled:bg-slate-400 dark:disabled:bg-slate-700 rounded-xl shadow-md shadow-brand-500/25 transition-all hover:scale-[1.01] active:scale-[0.99]"
          >
            <Box className="w-3.5 h-3.5" />
            <span>Generate 3D Model with TripoSR</span>
            <ArrowRight className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>
    </div>
  );
}

