import React, { useState, useEffect, useRef } from 'react';
import confetti from 'canvas-confetti';
import { useProducts } from '../../context/ProductContext';
import ThreeCADViewer from '../viewport/ThreeCADViewer';
import { 
  Box, 
  Sparkles, 
  CheckCircle, 
  CheckCircle2,
  ArrowLeft, 
  ArrowRight, 
  Cpu, 
  ShieldCheck, 
  Clock, 
  AlertCircle,
  Loader2,
  RefreshCw,
  Zap,
  Flame,
  Layers,
  Ban,
  RotateCcw
} from 'lucide-react';

export default function Generate3DStage() {
  const { 
    activeProduct, 
    updateActiveProduct, 
    setCurrentStage, 
    activeReconstructionJob, 
    startReconstruction, 
    cancelReconstruction 
  } = useProducts();

  const getCleanRef = () => {
    if (activeProduct?.model_reference_url) {
      const matchInScraped = (activeProduct?.scrapedImages || []).find(i => i.url === activeProduct.model_reference_url);
      if (matchInScraped) return matchInScraped;
      return { url: activeProduct.model_reference_url, title: activeProduct?.name || 'Reconstruction Reference' };
    }
    const sel = activeProduct?.selected_reference;
    if (sel?.url && sel?.target_evidence !== 'TECHNICAL_DRAWING' && sel?.angle !== 'Technical View') {
      return sel;
    }
    const best = activeProduct?.best_reference;
    if (best?.url && best?.target_evidence !== 'TECHNICAL_DRAWING' && best?.angle !== 'Technical View') {
      return best;
    }
    const photoCandidate = (activeProduct?.scrapedImages || []).find(
      i => i?.url && i?.status === 'VERIFIED' && i?.target_evidence !== 'TECHNICAL_DRAWING' && i?.angle !== 'Technical View'
    );
    if (photoCandidate) return photoCandidate;
    return sel || best || (activeProduct?.scrapedImages && activeProduct.scrapedImages.length > 0 ? activeProduct.scrapedImages[0] : null) ||
      { url: activeProduct?.thumbnail || '', title: activeProduct?.name };
  };

  const selectedRef = getCleanRef();

  const isQueued = activeReconstructionJob?.status === 'QUEUED';
  const isReconstructing = activeReconstructionJob?.status === 'RECONSTRUCTING';
  const isFailed = activeReconstructionJob?.status === 'FAILED';
  const isCancelled = activeReconstructionJob?.status === 'CANCELLED';
  const isBusy = isQueued || isReconstructing;

  // Resilient model URL extraction
  const activeModelUrl = activeProduct?.modelUrl || activeProduct?.model_3d || null;

  const getBaseName = (url) => {
    if (!url) return '';
    try {
      const parts = String(url).split('?')[0].split(/[\\/]/);
      return parts[parts.length - 1] || '';
    } catch {
      return '';
    }
  };

  const isReferenceChanged = Boolean(
    activeModelUrl &&
    activeProduct?.model_reference_url &&
    selectedRef?.url &&
    activeProduct.model_reference_url !== selectedRef.url &&
    getBaseName(activeProduct.model_reference_url) !== getBaseName(selectedRef.url)
  );

  const prevBusyRef = useRef(isBusy);

  // Trigger celebration confetti when reconstruction transitions from busy to complete
  useEffect(() => {
    if (prevBusyRef.current && !isBusy && activeModelUrl) {
      try {
        confetti({
          particleCount: 85,
          spread: 75,
          origin: { y: 0.6 }
        });
      } catch (e) {
        console.debug('Confetti error:', e);
      }
    }
    prevBusyRef.current = isBusy;
  }, [isBusy, activeModelUrl]);

  const handleGenerateClick = () => {
    startReconstruction(activeProduct);
  };

  const handleProceedToApproval = () => {
    updateActiveProduct({
      currentStage: 4
    });
    setCurrentStage(4); // Go to 3D Approval Stage
  };

  return (
    <div className="max-w-6xl mx-auto p-4 md:p-6 space-y-5">
      {/* 1. Top Header Card */}
      <div className="tailadmin-card p-5 bg-white dark:bg-[#131E3D] border-brand-500/20 shadow-xs">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <div>
            <div className="flex items-center gap-2 mb-1">
              <span className="px-2.5 py-0.5 rounded-full text-xs font-bold uppercase tracking-wider bg-brand-50 text-brand-600 dark:bg-brand-500/20 dark:text-brand-400 border border-brand-200 dark:border-brand-500/30">
                Phase 4: 3D Generate
              </span>
              <h1 className="text-base font-bold text-[#1C2434] dark:text-white">
                Pixal3D Pixel-Aligned Neural 3D Reconstruction
              </h1>
            </div>
            <p className="text-xs text-[#64748B] dark:text-[#8D9CB8]">
              Serialized single-slot GPU queue on RTX 4060. 1536 HR Shape Cascade + 1024 Texture Model + 2048px PBR Texture Baking.
            </p>
          </div>

          <div className="flex items-center gap-2">
            <span className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-purple-50 dark:bg-purple-950/40 text-purple-700 dark:text-purple-300 text-xs font-semibold border border-purple-200 dark:border-purple-800">
              <Cpu className="w-3.5 h-3.5" /> Engine: Pixal3D (TencentARC)
            </span>
          </div>
        </div>
      </div>

      {/* 2. Main 3D Viewport Layout */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Viewport Canvas (Left 2 cols) */}
        <div className="lg:col-span-2 space-y-4">
          {/* Active busy reconstruction state takes precedence */}
          {isBusy ? (
            <div className="h-[520px] rounded-2xl border-2 border-dashed border-purple-300 dark:border-purple-800/60 bg-white dark:bg-[#0B1120] flex flex-col items-center justify-center p-8 text-center space-y-4">
              {isQueued ? (
                <div className="space-y-3 max-w-sm">
                  <div className="w-12 h-12 rounded-2xl bg-amber-50 dark:bg-amber-950/50 text-amber-600 border border-amber-200 dark:border-amber-800 flex items-center justify-center mx-auto">
                    <Clock className="w-6 h-6 animate-pulse" />
                  </div>
                  <h3 className="text-sm font-bold text-[#1C2434] dark:text-white">
                    Queued in GPU Slot
                  </h3>
                  <p className="text-xs text-[#64748B] dark:text-[#8D9CB8]">
                    Position #{activeReconstructionJob?.queue_position || 1} in serialized GPU reconstruction queue. Will start automatically when GPU is free.
                  </p>
                  <button
                    onClick={() => cancelReconstruction(activeProduct?.id)}
                    className="flex items-center gap-1.5 px-4 py-2 text-xs font-semibold text-rose-600 bg-rose-50 dark:bg-rose-950/40 hover:bg-rose-100 rounded-xl border border-rose-200 dark:border-rose-800 transition-colors mx-auto cursor-pointer"
                  >
                    <Ban className="w-3.5 h-3.5" />
                    <span>Cancel Queued Request</span>
                  </button>
                </div>
              ) : (
                <div className="space-y-4 max-w-md w-full px-4">
                  <div className="w-14 h-14 rounded-2xl bg-purple-50 dark:bg-purple-950/50 text-purple-600 border border-purple-200 dark:border-purple-800 flex items-center justify-center mx-auto shadow-sm">
                    <Loader2 className="w-7 h-7 animate-spin" />
                  </div>
                  <div>
                    <h3 className="text-base font-bold text-[#1C2434] dark:text-white">
                      {activeReconstructionJob?.current_phase || 'Synthesizing 3D Asset on CUDA...'}
                    </h3>
                    <p className="text-xs text-[#64748B] dark:text-[#8D9CB8] mt-1">
                      Official TencentARC Pixal3D • 1536 HR Shape Cascade + 1024 Texture Model + 2048px PBR
                    </p>
                  </div>
                  {activeReconstructionJob?.progress !== undefined && (
                    <div className="w-full bg-[#E2E8F0] dark:bg-[#1E2C52] h-2.5 rounded-full overflow-hidden">
                      <div
                        className="bg-purple-600 h-full transition-all duration-500 rounded-full"
                        style={{ width: `${Math.min(100, Math.max(8, Math.round((activeReconstructionJob.progress || 0.08) * 100)))}%` }}
                      />
                    </div>
                  )}
                  <p className="text-xs font-mono font-bold text-purple-600 dark:text-purple-400">
                    Stage Progress: {Math.min(100, Math.max(8, Math.round((activeReconstructionJob?.progress || 0.08) * 100)))}%
                  </p>
                </div>
              )}
            </div>
          ) : isFailed ? (
            <div className="h-[520px] rounded-2xl border-2 border-dashed border-rose-300 dark:border-rose-800/60 bg-white dark:bg-[#0B1120] flex flex-col items-center justify-center p-8 text-center space-y-4">
              <div className="w-12 h-12 rounded-2xl bg-rose-50 dark:bg-rose-950/50 text-rose-600 border border-rose-200 dark:border-rose-800 flex items-center justify-center mx-auto">
                <AlertCircle className="w-6 h-6" />
              </div>
              <h3 className="text-sm font-bold text-rose-600 dark:text-rose-400">
                Reconstruction Failed
              </h3>
              <p className="text-xs text-[#64748B] dark:text-[#8D9CB8] max-w-sm">
                {activeReconstructionJob?.error || 'Pixal3D encountered an error during inference.'}
              </p>
              <button
                onClick={handleGenerateClick}
                className="flex items-center gap-1.5 px-5 py-2.5 text-xs font-semibold text-white bg-brand-500 hover:bg-brand-600 rounded-xl shadow-md transition-all mx-auto cursor-pointer"
              >
                <RotateCcw className="w-3.5 h-3.5" />
                <span>Retry 3D Generation</span>
              </button>
            </div>
          ) : activeModelUrl ? (
            /* Model is generated and ready: SUCCESS STATE UI */
            <div className="space-y-4">
              {/* Celebratory Success Banner */}
              <div className="p-4 rounded-2xl bg-gradient-to-r from-emerald-500/15 via-emerald-500/5 to-purple-500/10 border border-emerald-500/30 dark:border-emerald-500/40 shadow-xs flex flex-col sm:flex-row sm:items-center justify-between gap-3 animate-in fade-in duration-300">
                <div className="flex items-center gap-3">
                  <div className="w-11 h-11 rounded-xl bg-emerald-500 text-white flex items-center justify-center shadow-lg shadow-emerald-500/25 flex-shrink-0">
                    <CheckCircle className="w-6 h-6 stroke-[2.5]" />
                  </div>
                  <div>
                    <div className="flex items-center gap-2">
                      <h3 className="text-sm font-bold text-emerald-950 dark:text-emerald-100">
                        3D Reconstruction Complete!
                      </h3>
                      <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-emerald-100 dark:bg-emerald-950 text-emerald-700 dark:text-emerald-300 border border-emerald-300 dark:border-emerald-700">
                        Model Ready
                      </span>
                    </div>
                    <p className="text-xs text-[#475569] dark:text-[#94A3B8] mt-0.5">
                      Synthesized with TencentARC Pixal3D
                      {activeProduct?.reconstructionDuration ? (
                        <>
                          {' in '}
                          <span className="font-semibold text-emerald-700 dark:text-emerald-300">
                            {activeProduct.reconstructionDuration}
                          </span>
                        </>
                      ) : null}
                      {(activeProduct?.meshStats?.vertex_count || activeProduct?.meshStats?.vertices) ? (
                        <>
                          {' • '}
                          <span className="font-semibold text-emerald-700 dark:text-emerald-300">
                            {(activeProduct.meshStats.vertex_count || activeProduct.meshStats.vertices).toLocaleString()} Vertices
                          </span>
                        </>
                      ) : null}
                      {' • 2048px PBR UV Textures'}
                    </p>
                  </div>
                </div>

                <div className="flex items-center gap-2 self-end sm:self-center">
                  <button
                    onClick={handleProceedToApproval}
                    className="flex items-center gap-2 px-4 py-2 text-xs font-bold text-white bg-emerald-600 hover:bg-emerald-500 active:scale-[0.98] rounded-xl shadow-md shadow-emerald-600/25 transition-all cursor-pointer"
                  >
                    <span>Proceed to 3D Approval</span>
                    <ArrowRight className="w-3.5 h-3.5" />
                  </button>
                </div>
              </div>

              {isReferenceChanged && (
                <div className="p-3 rounded-xl bg-amber-50 dark:bg-amber-950/40 border border-amber-200 dark:border-amber-800 text-xs text-amber-800 dark:text-amber-200 flex items-center justify-between">
                  <span>
                    Current model was generated with a prior reference image. Click below to regenerate with the new reference.
                  </span>
                  <button
                    onClick={handleGenerateClick}
                    disabled={isBusy}
                    className="px-3 py-1 rounded-lg bg-amber-200 dark:bg-amber-800 font-semibold text-amber-900 dark:text-amber-100 hover:bg-amber-300 cursor-pointer"
                  >
                    Re-generate
                  </button>
                </div>
              )}

              {/* Three.js CAD Viewport */}
              <div className="rounded-2xl overflow-hidden border border-[#CBD5E1] dark:border-[#1E2C52] shadow-sm">
                <ThreeCADViewer
                  modelUrl={activeModelUrl}
                  productName={activeProduct?.name || '3D Product Model'}
                  meshStats={activeProduct?.meshStats}
                />
              </div>

              {/* Quick Actions Strip */}
              <div className="flex items-center justify-between p-3 rounded-xl bg-white dark:bg-[#131E3D] border border-[#E2E8F0] dark:border-[#1E2C52] text-xs">
                <div className="flex items-center gap-2 text-[#64748B] dark:text-[#8D9CB8]">
                  <Sparkles className="w-4 h-4 text-emerald-500" />
                  <span>Interactive 3D viewport: click & drag to rotate, right-click to pan, scroll to zoom.</span>
                </div>
                <div className="flex items-center gap-2">
                  <button
                    onClick={handleGenerateClick}
                    disabled={isBusy}
                    className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-[#CBD5E1] dark:border-[#1E2C52] text-[#64748B] dark:text-[#8D9CB8] hover:text-[#1C2434] dark:hover:text-white hover:bg-slate-50 dark:hover:bg-slate-800 transition-colors cursor-pointer"
                  >
                    <RefreshCw className="w-3 h-3" />
                    <span>Re-run Generation</span>
                  </button>
                  <button
                    onClick={handleProceedToApproval}
                    className="flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 font-semibold text-white shadow-xs transition-colors cursor-pointer"
                  >
                    <ShieldCheck className="w-3.5 h-3.5" />
                    <span>Validate in Phase 5</span>
                    <ArrowRight className="w-3 h-3" />
                  </button>
                </div>
              </div>
            </div>
          ) : (
            /* Un-generated state */
            <div className="h-[520px] rounded-2xl border-2 border-dashed border-[#CBD5E1] dark:border-[#1E2C52] bg-white dark:bg-[#0B1120] flex flex-col items-center justify-center p-8 text-center space-y-4">
              <div className="space-y-3 max-w-sm">
                <div className="w-12 h-12 rounded-2xl bg-brand-50 dark:bg-brand-950/50 text-brand-600 border border-brand-200 dark:border-brand-800 flex items-center justify-center mx-auto">
                  <Box className="w-6 h-6 stroke-[2.2]" />
                </div>
                <h3 className="text-sm font-bold text-[#1C2434] dark:text-white">
                  Ready for 3D Reconstruction
                </h3>
                <p className="text-xs text-[#64748B] dark:text-[#8D9CB8]">
                  Primary reference approved. Click below to enqueue into the Pixal3D GPU pipeline.
                </p>
                <button
                  onClick={handleGenerateClick}
                  className="flex items-center gap-2 px-6 py-2.5 text-xs font-semibold text-white bg-brand-500 hover:bg-brand-600 rounded-xl shadow-md shadow-brand-500/25 transition-all hover:scale-[1.02] active:scale-[0.98] mx-auto cursor-pointer"
                >
                  <Sparkles className="w-3.5 h-3.5" />
                  <span>Generate 3D with Pixal3D</span>
                </button>
              </div>
            </div>
          )}
        </div>

        {/* Sidebar Controls & Telemetry (Right col) */}
        <div className="space-y-4">
          {/* Reference Card */}
          <div className="tailadmin-card p-5 bg-white dark:bg-[#131E3D]">
            <div className="flex items-center justify-between mb-3">
              <h2 className="text-xs font-bold uppercase tracking-wider text-[#1C2434] dark:text-white">
                Reconstruction Input
              </h2>
              <button
                onClick={() => setCurrentStage(2)}
                className="text-[11px] font-semibold text-brand-600 dark:text-brand-400 hover:underline cursor-pointer"
              >
                Change Reference
              </button>
            </div>

            <div className="flex items-center gap-3 p-3 rounded-xl bg-[#F8FAFC] dark:bg-[#0F1832] border border-[#E2E8F0] dark:border-[#1E2C52]">
              <div className="w-14 h-14 rounded-lg overflow-hidden bg-slate-900 flex-shrink-0 border border-[#CBD5E1] dark:border-[#1E2C52]">
                {selectedRef?.url ? (
                  <img src={selectedRef.url} alt="Reference" className="w-full h-full object-cover" />
                ) : (
                  <Box className="w-6 h-6 text-slate-500 m-auto mt-4" />
                )}
              </div>
              <div className="min-w-0 flex-1">
                <p className="text-xs font-semibold text-[#1C2434] dark:text-white truncate" title={selectedRef?.title || activeProduct?.name}>
                  {selectedRef?.title || activeProduct?.name || 'Product Reference'}
                </p>
                <div className="flex items-center gap-1.5 mt-1">
                  {selectedRef?.angle && (
                    <span className="inline-block px-1.5 py-0.5 text-[9px] font-bold rounded bg-slate-200 dark:bg-slate-800 text-slate-700 dark:text-slate-300">
                      {selectedRef.angle}
                    </span>
                  )}
                  <span className="inline-block px-1.5 py-0.5 text-[9px] font-bold rounded bg-emerald-100 dark:bg-emerald-950 text-emerald-700 dark:text-emerald-400">
                    Selected Ref
                  </span>
                </div>
              </div>
            </div>
          </div>

          {/* Engine Status & High-Resolution Telemetry */}
          <div className="tailadmin-card p-5 bg-white dark:bg-[#131E3D]">
            <div className="flex items-center justify-between mb-3">
              <h2 className="text-xs font-bold uppercase tracking-wider text-[#1C2434] dark:text-white">
                Pixal3D Telemetry
              </h2>
              {activeModelUrl && (
                <button
                  onClick={handleGenerateClick}
                  disabled={isBusy}
                  className="text-[11px] font-semibold text-brand-600 dark:text-brand-400 hover:underline flex items-center gap-1 cursor-pointer"
                >
                  <RefreshCw className={`w-3 h-3 ${isBusy ? 'animate-spin' : ''}`} />
                  <span>Re-run</span>
                </button>
              )}
            </div>

            {isBusy ? (
              <div className="p-4 rounded-xl bg-purple-50 dark:bg-purple-950/40 border border-purple-200 dark:border-purple-800 text-center space-y-2">
                <Loader2 className="w-6 h-6 text-purple-600 animate-spin mx-auto" />
                <p className="text-xs font-bold text-purple-900 dark:text-purple-200">
                  {isQueued ? `Queued (Slot #${activeReconstructionJob?.queue_position || 1})` : (activeReconstructionJob?.current_phase || 'Synthesizing 1536 Cascade...')}
                </p>
                <p className="text-[10px] text-purple-700 dark:text-purple-300">
                  Serialized RTX 4060 GPU queue. Low-VRAM 1536 cascade synthesis.
                </p>
              </div>
            ) : (
              <div className="space-y-3">
                {activeModelUrl && (
                  <div className="p-2.5 rounded-xl bg-emerald-50 dark:bg-emerald-950/40 border border-emerald-200 dark:border-emerald-800/80 flex items-center justify-between">
                    <span className="flex items-center gap-1.5 text-xs font-bold text-emerald-800 dark:text-emerald-300">
                      <CheckCircle2 className="w-4 h-4 text-emerald-600" />
                      3D Asset Generated
                    </span>
                    <span className="text-[10px] font-bold px-2 py-0.5 rounded-md bg-emerald-200/80 dark:bg-emerald-800 text-emerald-900 dark:text-emerald-100">
                      Phase 4 Done
                    </span>
                  </div>
                )}

                <div className="space-y-2 text-xs">
                  <div className="flex justify-between p-2 rounded-lg bg-[#F8FAFC] dark:bg-[#0F1832] border border-[#E2E8F0] dark:border-[#1E2C52]">
                    <span className="text-[#64748B] dark:text-[#8D9CB8]">Execution Slot</span>
                    <span className="inline-flex items-center gap-1 font-bold text-purple-600 dark:text-purple-400">
                      <Zap className="w-3 h-3 text-emerald-500" /> Serialized Queue (Slot 1/1)
                    </span>
                  </div>
                  <div className="flex justify-between p-2 rounded-lg bg-[#F8FAFC] dark:bg-[#0F1832] border border-[#E2E8F0] dark:border-[#1E2C52]">
                    <span className="text-[#64748B] dark:text-[#8D9CB8]">Engine</span>
                    <span className="font-semibold text-[#1C2434] dark:text-white">TencentARC/Pixal3D (1536 HR Shape + 1024 Tex)</span>
                  </div>
                  <div className="flex justify-between p-2 rounded-lg bg-[#F8FAFC] dark:bg-[#0F1832] border border-[#E2E8F0] dark:border-[#1E2C52]">
                    <span className="text-[#64748B] dark:text-[#8D9CB8]">Output Format</span>
                    <span className="font-mono text-[11px] text-brand-600 dark:text-brand-400">2048px PBR WebP .GLB</span>
                  </div>
                  <div className="flex justify-between p-2 rounded-lg bg-[#F8FAFC] dark:bg-[#0F1832] border border-[#E2E8F0] dark:border-[#1E2C52]">
                    <span className="text-[#64748B] dark:text-[#8D9CB8]">Duration</span>
                    <span className="font-mono text-[11px] text-[#1C2434] dark:text-white">
                      {activeProduct?.reconstructionDuration || '—'}
                    </span>
                  </div>
                  <div className="flex justify-between p-2 rounded-lg bg-[#F8FAFC] dark:bg-[#0F1832] border border-[#E2E8F0] dark:border-[#1E2C52]">
                    <span className="text-[#64748B] dark:text-[#8D9CB8]">Geometry</span>
                    <span className="font-semibold text-[#1C2434] dark:text-white">
                      {(activeProduct?.meshStats?.vertex_count || activeProduct?.meshStats?.vertices)
                        ? `${(activeProduct.meshStats.vertex_count || activeProduct.meshStats.vertices).toLocaleString()} Verts`
                        : '—'}
                    </span>
                  </div>
                </div>

                {activeModelUrl && (
                  <button
                    onClick={handleProceedToApproval}
                    className="w-full flex items-center justify-center gap-2 p-2.5 rounded-xl font-bold text-xs text-white bg-emerald-600 hover:bg-emerald-500 shadow-md shadow-emerald-600/25 transition-all cursor-pointer mt-2"
                  >
                    <ShieldCheck className="w-4 h-4" />
                    <span>Proceed to 3D Approval</span>
                    <ArrowRight className="w-3.5 h-3.5" />
                  </button>
                )}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* 3. Footer Navigation */}
      <div className="flex items-center justify-between pt-4 border-t border-[#E2E8F0] dark:border-[#1E2C52]">
        <button
          onClick={() => setCurrentStage(2)}
          className="flex items-center gap-2 px-4 py-2 text-xs font-semibold text-[#64748B] dark:text-[#8D9CB8] bg-white dark:bg-[#131E3D] hover:bg-[#F1F5F9] dark:hover:bg-[#172449] border border-[#CBD5E1] dark:border-[#1E2C52] rounded-xl transition-colors cursor-pointer"
        >
          <ArrowLeft className="w-3.5 h-3.5" />
          <span>Back to Image Approval</span>
        </button>

        <button
          onClick={handleProceedToApproval}
          disabled={!activeModelUrl || isBusy}
          className={`flex items-center gap-2 px-6 py-2.5 text-xs font-bold rounded-xl shadow-md transition-all ${
            activeModelUrl && !isBusy
              ? 'text-white bg-emerald-600 hover:bg-emerald-500 shadow-emerald-600/30 hover:scale-[1.02] active:scale-[0.98] ring-2 ring-emerald-400/30 cursor-pointer'
              : 'text-[#94A3B8] dark:text-[#475569] bg-[#E2E8F0] dark:bg-[#1E2C52] cursor-not-allowed shadow-none'
          }`}
        >
          <ShieldCheck className="w-4 h-4" />
          <span>Proceed to 3D Approval Validation</span>
          <ArrowRight className="w-3.5 h-3.5" />
        </button>
      </div>
    </div>
  );
}
