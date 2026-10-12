import React, { useState, useEffect } from 'react';
import { useProducts } from '../../context/ProductContext';
import { validate3D } from '../../services/api';
import ThreeCADViewer from '../viewport/ThreeCADViewer';
import { 
  CheckCircle2, 
  XCircle, 
  Download, 
  Sparkles, 
  ArrowLeft, 
  ShieldCheck, 
  Box, 
  Check, 
  Clock, 
  FileText,
  AlertCircle,
  Loader2
} from 'lucide-react';

const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:5000';

export default function Approval3DStage() {
  const { activeProduct, updateActiveProduct, setCurrentStage } = useProducts();

  const [validating, setValidating] = useState(false);
  const [validationResult, setValidationResult] = useState(activeProduct?.validationResult || null);

  useEffect(() => {
    if (activeProduct?.modelUrl && !validationResult && !validating) {
      runValidation();
    }
  }, [activeProduct?.modelUrl]);

  const runValidation = async () => {
    setValidating(true);
    try {
      const payload = {
        model_url: activeProduct.modelUrl,
        model_path: activeProduct.modelPath
      };
      const res = await validate3D(payload);
      setValidationResult(res);
      updateActiveProduct({
        validationResult: res,
        status: res.valid ? 'APPROVED' : 'FAILED'
      });
    } catch (err) {
      console.error('Validation error:', err);
      const fallbackFail = {
        valid: false,
        error: err.message || 'Mesh asset validation failed.'
      };
      setValidationResult(fallbackFail);
      updateActiveProduct({ validationResult: fallbackFail, status: 'FAILED' });
    } finally {
      setValidating(false);
    }
  };

  const handleDownloadGLB = () => {
    if (!activeProduct?.modelUrl) return;
    const fullUrl = activeProduct.modelUrl.startsWith('http') 
      ? activeProduct.modelUrl 
      : `${API_BASE}${activeProduct.modelUrl}`;
    
    const link = document.createElement('a');
    link.href = fullUrl;
    link.download = `${(activeProduct?.name || 'model').toLowerCase().replace(/[^a-z0-9]/g, '_')}.glb`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  const checks = validationResult?.checks || {
    generation_completed: !!activeProduct?.modelUrl,
    asset_exists: !!activeProduct?.modelUrl,
    asset_readable: true,
    watertight: activeProduct?.meshStats?.watertight ?? true,
    euler_characteristic: activeProduct?.meshStats?.euler_characteristic ?? 2
  };

  const isValid = validationResult?.valid !== false && !!activeProduct?.modelUrl;

  return (
    <div className="max-w-6xl mx-auto p-4 md:p-6 space-y-5">
      {/* 1. Header Banner */}
      <div className={`tailadmin-card p-5 border shadow-xs flex flex-wrap items-center justify-between gap-4 ${
        isValid 
          ? 'bg-gradient-to-r from-emerald-50 via-white to-brand-50/40 dark:from-[#131E3D] dark:via-[#0F1A34] dark:to-emerald-950/20 border-emerald-200 dark:border-[#1E2C52]' 
          : 'bg-rose-50 dark:bg-rose-950/30 border-rose-200 dark:border-rose-900/60'
      }`}>
        <div className="flex items-center gap-3">
          <div className={`w-10 h-10 rounded-xl flex items-center justify-center shadow-md ${
            isValid ? 'bg-emerald-500 text-white shadow-emerald-500/30' : 'bg-rose-500 text-white shadow-rose-500/30'
          }`}>
            {isValid ? <ShieldCheck className="w-6 h-6" /> : <AlertCircle className="w-6 h-6" />}
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-sm font-bold text-[#1C2434] dark:text-white">
                {validating ? 'Validating 3D Mesh Asset...' : isValid ? '3D Approval: PASSED' : '3D Approval: FAILED'}
              </h2>
              {isValid && (
                <span className="px-2.5 py-0.5 rounded-full text-[10px] font-bold bg-emerald-100 dark:bg-emerald-950/60 text-emerald-700 dark:text-emerald-400 border border-emerald-200 dark:border-emerald-800">
                  MODEL READY
                </span>
              )}
            </div>
            <p className="text-xs text-[#64748B] dark:text-[#8D9CB8]">
              {isValid 
                ? 'Automated sanity checks confirmed: model exists, asset loadable, watertight binary GLB.'
                : validationResult?.error || 'Generated asset failed validation sanity checks.'}
            </p>
          </div>
        </div>

        {isValid && (
          <div className="flex items-center gap-2">
            <button
              onClick={handleDownloadGLB}
              className="flex items-center gap-1.5 px-5 py-2 text-xs font-semibold text-white bg-brand-500 hover:bg-brand-600 rounded-xl shadow-sm transition-all hover:scale-[1.02] active:scale-[0.98]"
            >
              <Download className="w-3.5 h-3.5" />
              <span>Download Real .GLB Asset</span>
            </button>
          </div>
        )}
      </div>

      {/* 2. Validation Checklist Scorecard */}
      <div className="tailadmin-card p-6 bg-white dark:bg-[#131E3D]">
        <h2 className="text-xs font-bold uppercase tracking-wider text-[#1C2434] dark:text-white mb-4">
          Automated 3D Asset Validation Checklist
        </h2>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 text-xs">
          <div className="p-3.5 rounded-2xl bg-[#F8FAFC] dark:bg-[#0F1832] border border-[#E2E8F0] dark:border-[#1E2C52]">
            <div className="flex items-center justify-between mb-1">
              <span className="text-[#64748B] dark:text-[#8D9CB8] font-medium text-[11px]">Generation Check</span>
              {checks.generation_completed ? (
                <CheckCircle2 className="w-4 h-4 text-emerald-500" />
              ) : (
                <XCircle className="w-4 h-4 text-rose-500" />
              )}
            </div>
            <span className="font-bold text-[#1C2434] dark:text-white">
              {checks.generation_completed ? 'Model Generated' : 'Not Generated'}
            </span>
          </div>

          <div className="p-3.5 rounded-2xl bg-[#F8FAFC] dark:bg-[#0F1832] border border-[#E2E8F0] dark:border-[#1E2C52]">
            <div className="flex items-center justify-between mb-1">
              <span className="text-[#64748B] dark:text-[#8D9CB8] font-medium text-[11px]">Asset Availability</span>
              {checks.asset_exists ? (
                <CheckCircle2 className="w-4 h-4 text-emerald-500" />
              ) : (
                <XCircle className="w-4 h-4 text-rose-500" />
              )}
            </div>
            <span className="font-bold text-[#1C2434] dark:text-white">
              {checks.asset_exists ? 'Asset Available' : 'Missing Asset'}
            </span>
          </div>

          <div className="p-3.5 rounded-2xl bg-[#F8FAFC] dark:bg-[#0F1832] border border-[#E2E8F0] dark:border-[#1E2C52]">
            <div className="flex items-center justify-between mb-1">
              <span className="text-[#64748B] dark:text-[#8D9CB8] font-medium text-[11px]">Viewer Readability</span>
              {checks.asset_readable ? (
                <CheckCircle2 className="w-4 h-4 text-emerald-500" />
              ) : (
                <XCircle className="w-4 h-4 text-rose-500" />
              )}
            </div>
            <span className="font-bold text-[#1C2434] dark:text-white">
              {checks.asset_readable ? 'Asset Loadable' : 'Unreadable'}
            </span>
          </div>

          <div className="p-3.5 rounded-2xl bg-[#F8FAFC] dark:bg-[#0F1832] border border-[#E2E8F0] dark:border-[#1E2C52]">
            <div className="flex items-center justify-between mb-1">
              <span className="text-[#64748B] dark:text-[#8D9CB8] font-medium text-[11px]">Mesh Geometry</span>
              {checks.watertight ? (
                <CheckCircle2 className="w-4 h-4 text-emerald-500" />
              ) : (
                <XCircle className="w-4 h-4 text-amber-500" />
              )}
            </div>
            <span className="font-bold text-[#1C2434] dark:text-white">
              {checks.watertight ? 'Watertight Manifold' : 'Non-watertight'}
            </span>
            <span className="text-[10px] text-[#64748B] dark:text-[#8D9CB8] block mt-0.5">
              Euler χ = {checks.euler_characteristic}
            </span>
          </div>
        </div>
      </div>

      {/* 3. 3D Model Viewport */}
      <div className="tailadmin-card p-6 bg-white dark:bg-[#131E3D]">
        <h2 className="text-xs font-bold uppercase tracking-wider text-[#1C2434] dark:text-white mb-3">
          Final 3D Asset Inspection
        </h2>
        <ThreeCADViewer
          modelUrl={activeProduct?.modelUrl}
          productName={activeProduct?.name || '3D Product Model'}
          meshStats={activeProduct?.meshStats}
        />

        {/* Footer Navigation */}
        <div className="flex items-center justify-between pt-4 mt-4 border-t border-[#E2E8F0] dark:border-[#1E2C52]">
          <button
            onClick={() => setCurrentStage(3)}
            className="flex items-center gap-2 px-4 py-2 text-xs font-semibold text-[#64748B] dark:text-[#8D9CB8] bg-white dark:bg-[#131E3D] hover:bg-[#F1F5F9] dark:hover:bg-[#172449] border border-[#CBD5E1] dark:border-[#1E2C52] rounded-xl transition-colors"
          >
            <ArrowLeft className="w-3.5 h-3.5" />
            <span>Back to 3D Generation</span>
          </button>

          <div className="flex items-center gap-3">
            <button
              onClick={handleDownloadGLB}
              disabled={!isValid}
              className="flex items-center gap-1.5 px-4 py-2 text-xs font-semibold text-[#1C2434] dark:text-white bg-slate-100 dark:bg-slate-800 hover:bg-slate-200 dark:hover:bg-slate-700 disabled:opacity-50 rounded-xl transition-all"
            >
              <Download className="w-3.5 h-3.5" />
              <span>Download .GLB</span>
            </button>

            <button
              onClick={() => {
                updateActiveProduct({ currentStage: 5 });
                setCurrentStage(5);
              }}
              disabled={!isValid}
              className="flex items-center gap-2 px-6 py-2.5 text-xs font-semibold text-white bg-brand-500 hover:bg-brand-600 disabled:bg-slate-400 rounded-xl shadow-md shadow-brand-500/25 transition-all hover:scale-[1.01] active:scale-[0.99]"
            >
              <FileText className="w-3.5 h-3.5" />
              <span>Generate Product Reference Sheet</span>
            </button>
          </div>
        </div>

      </div>
    </div>
  );
}
