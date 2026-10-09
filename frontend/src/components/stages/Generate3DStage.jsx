import React, { useState, useEffect } from 'react';
import { useProducts } from '../../context/ProductContext';
import ThreeCADViewer from '../viewport/ThreeCADViewer';
import { reconstruct3D } from '../../services/api';
import { 
  Box, 
  Sparkles, 
  CheckCircle, 
  ArrowLeft, 
  ArrowRight, 
  Cpu, 
  ShieldCheck, 
  Clock, 
  AlertCircle,
  Loader2,
  RefreshCw
} from 'lucide-react';

export default function Generate3DStage() {
  const { activeProduct, updateActiveProduct, setCurrentStage } = useProducts();

  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState(null);
  const [generationTime, setGenerationTime] = useState(activeProduct?.reconstructionDuration || null);
  const [meshStats, setMeshStats] = useState(activeProduct?.meshStats || null);

  const selectedRef = activeProduct?.selected_reference || 
    activeProduct?.best_reference ||
    (activeProduct?.scrapedImages && activeProduct.scrapedImages.length > 0 ? activeProduct.scrapedImages[0] : null) ||
    { url: activeProduct?.thumbnail || '', title: activeProduct?.name };

  // Trigger reconstruction automatically if modelUrl is not yet present
  useEffect(() => {
    if (!activeProduct?.modelUrl && !generating && selectedRef?.url) {
      runReconstruction();
    }
  }, [activeProduct?.id, activeProduct?.modelUrl, selectedRef?.url]);

  const runReconstruction = async () => {
    setGenerating(true);
    setError(null);

    const refImage = selectedRef?.url || activeProduct?.thumbnail || '';

    try {
      const payload = {
        reference_image: refImage,
        product_title: activeProduct?.name || 'Product Asset',
        product_sku: activeProduct?.modelNumber || activeProduct?.id || 'PROD-01',
        product_id: activeProduct?.id || 'PROD-01',
        engine: 'TripoSR'
      };

      const result = await reconstruct3D(payload);

      if (result.success && result.model_url) {
        setGenerationTime(result.duration || `${result.generation_time_sec}s`);
        setMeshStats(result.mesh_stats || result.mesh_telemetry);

        const genSec = result.generation_time_sec || (result.duration ? parseFloat(result.duration) : null);
        updateActiveProduct({
          modelUrl: result.model_url,
          modelPath: result.model_path,
          reconstruction_duration_sec: genSec,
          reconstructionDuration: result.duration || `${genSec}s`,
          meshStats: result.mesh_stats || result.mesh_telemetry,
          reconstructionEngine: result.reconstruction_engine || 'TripoSR'
        });

      } else {
        setError(result.error || 'TripoSR engine failed to synthesize 3D mesh.');
      }
    } catch (err) {
      console.error('3D Reconstruction error:', err);
      setError(err.message || 'Error connecting to 3D reconstruction engine.');
    } finally {
      setGenerating(false);
    }
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
                TripoSR Neural 3D Reconstruction
              </h1>
            </div>
            <p className="text-xs text-[#64748B] dark:text-[#8D9CB8]">
              Synthesizing watertight neural 3D asset (.glb) from the verified reference image via TripoSR.
            </p>
          </div>

          <div className="flex items-center gap-2">
            <span className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-blue-50 dark:bg-blue-950/40 text-blue-700 dark:text-blue-300 text-xs font-semibold border border-blue-200 dark:border-blue-800">
              <Cpu className="w-3.5 h-3.5" /> Engine: TripoSR (CUDA)
            </span>
          </div>
        </div>
      </div>

      {/* 2. Main 3D Viewport Layout */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Viewport Canvas (Left 2 cols) */}
        <div className="lg:col-span-2 space-y-3">
          <ThreeCADViewer
            modelUrl={activeProduct?.modelUrl}
            productName={activeProduct?.name || '3D Product Model'}
            meshStats={activeProduct?.meshStats || meshStats}
          />
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
                className="text-[11px] font-semibold text-brand-600 dark:text-brand-400 hover:underline"
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

          {/* Engine Status & Telemetry */}
          <div className="tailadmin-card p-5 bg-white dark:bg-[#131E3D]">
            <div className="flex items-center justify-between mb-3">
              <h2 className="text-xs font-bold uppercase tracking-wider text-[#1C2434] dark:text-white">
                Engine Telemetry
              </h2>
              <button
                onClick={runReconstruction}
                disabled={generating}
                className="text-[11px] font-semibold text-brand-600 dark:text-brand-400 hover:underline flex items-center gap-1"
              >
                <RefreshCw className={`w-3 h-3 ${generating ? 'animate-spin' : ''}`} />
                <span>Re-run</span>
              </button>
            </div>

            {generating ? (
              <div className="p-4 rounded-xl bg-blue-50 dark:bg-blue-950/40 border border-blue-200 dark:border-blue-800 text-center space-y-2">
                <Loader2 className="w-6 h-6 text-brand-500 animate-spin mx-auto" />
                <p className="text-xs font-bold text-blue-900 dark:text-blue-200">
                  Synthesizing 3D Geometry...
                </p>
                <p className="text-[10px] text-blue-700 dark:text-blue-300">
                  TripoSR neural feedforward transformer running on CUDA.
                </p>
              </div>
            ) : error ? (
              <div className="p-4 rounded-xl bg-rose-50 dark:bg-rose-950/40 border border-rose-200 dark:border-rose-800 text-rose-800 dark:text-rose-300 text-xs space-y-1">
                <div className="flex items-center gap-1.5 font-bold">
                  <AlertCircle className="w-4 h-4 text-rose-500" />
                  <span>Generation Error</span>
                </div>
                <p className="text-[11px]">{error}</p>
              </div>
            ) : (
              <div className="space-y-2 text-xs">
                <div className="flex justify-between p-2 rounded-lg bg-[#F8FAFC] dark:bg-[#0F1832] border border-[#E2E8F0] dark:border-[#1E2C52]">
                  <span className="text-[#64748B] dark:text-[#8D9CB8]">Status</span>
                  <span className="font-bold text-emerald-600 dark:text-emerald-400">Complete</span>
                </div>
                <div className="flex justify-between p-2 rounded-lg bg-[#F8FAFC] dark:bg-[#0F1832] border border-[#E2E8F0] dark:border-[#1E2C52]">
                  <span className="text-[#64748B] dark:text-[#8D9CB8]">Engine</span>
                  <span className="font-semibold text-[#1C2434] dark:text-white">TripoSR Neural</span>
                </div>
                <div className="flex justify-between p-2 rounded-lg bg-[#F8FAFC] dark:bg-[#0F1832] border border-[#E2E8F0] dark:border-[#1E2C52]">
                  <span className="text-[#64748B] dark:text-[#8D9CB8]">Output Format</span>
                  <span className="font-mono text-[11px] text-brand-600 dark:text-brand-400">Binary .GLB</span>
                </div>
                {generationTime && (
                  <div className="flex justify-between p-2 rounded-lg bg-[#F8FAFC] dark:bg-[#0F1832] border border-[#E2E8F0] dark:border-[#1E2C52]">
                    <span className="text-[#64748B] dark:text-[#8D9CB8]">Duration</span>
                    <span className="font-mono text-[11px] text-[#1C2434] dark:text-white">{generationTime}</span>
                  </div>
                )}
                {meshStats && (
                  <div className="flex justify-between p-2 rounded-lg bg-[#F8FAFC] dark:bg-[#0F1832] border border-[#E2E8F0] dark:border-[#1E2C52]">
                    <span className="text-[#64748B] dark:text-[#8D9CB8]">Geometry</span>
                    <span className="font-semibold text-[#1C2434] dark:text-white">
                      {(meshStats.vertexCount || meshStats.vertices)?.toLocaleString()} Verts
                    </span>
                  </div>
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
          className="flex items-center gap-2 px-4 py-2 text-xs font-semibold text-[#64748B] dark:text-[#8D9CB8] bg-white dark:bg-[#131E3D] hover:bg-[#F1F5F9] dark:hover:bg-[#172449] border border-[#CBD5E1] dark:border-[#1E2C52] rounded-xl transition-colors"
        >
          <ArrowLeft className="w-3.5 h-3.5" />
          <span>Back to Image Approval</span>
        </button>

        <button
          onClick={handleProceedToApproval}
          disabled={!activeProduct?.modelUrl || generating}
          className="flex items-center gap-2 px-6 py-2.5 text-xs font-semibold text-white bg-emerald-600 hover:bg-emerald-700 disabled:bg-slate-400 rounded-xl shadow-md shadow-emerald-600/25 transition-all hover:scale-[1.01] active:scale-[0.99]"
        >
          <ShieldCheck className="w-4 h-4" />
          <span>Proceed to 3D Approval Validation</span>
          <ArrowRight className="w-3.5 h-3.5" />
        </button>
      </div>
    </div>
  );
}
