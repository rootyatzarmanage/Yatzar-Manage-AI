import React, { useState } from 'react';
import { useProducts } from '../../context/ProductContext';
import ThreeCADViewer from '../viewport/ThreeCADViewer';
import { 
  Box, 
  Layers, 
  Sparkles, 
  CheckCircle, 
  ArrowLeft, 
  ArrowRight, 
  Activity, 
  Cpu, 
  Eye, 
  ShieldCheck,
  Zap,
  Play,
  Pause,
  RotateCcw,
  Sliders
} from 'lucide-react';

export default function Generate3DStage() {
  const { activeProduct, updateActiveProduct, setCurrentStage } = useProducts();

  const [proceduralStep, setProceduralStep] = useState(3);
  const [isInverted, setIsInverted] = useState(false);
  const [isPaused, setIsPaused] = useState(false);

  const handleProceedToQA = () => {
    updateActiveProduct({
      currentStage: 4,
      status: 'APPROVED',
      confidenceScore: 0.938
    });
    setCurrentStage(4); // Go to 3D Approval Stage
  };

  return (
    <div className="max-w-6xl mx-auto p-4 md:p-6 space-y-5">
      {/* Top Header Card */}
      <div className="tailadmin-card p-5 bg-white dark:bg-[#131E3D]">
        <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4">
          <div>
            <div className="flex items-center gap-2 mb-1">
              <span className="px-2 py-0.5 rounded-md text-[10px] font-bold bg-brand-50 text-brand-600 dark:bg-brand-500/20 dark:text-brand-400 border border-brand-200 dark:border-brand-500/30">
                Phase 4 Procedural CAD &amp; CSG Engine
              </span>
              <h1 className="text-base font-bold text-[#1C2434] dark:text-white">
                Interactive CSG White-Box Synthesis
              </h1>
            </div>
            <p className="text-xs text-[#64748B] dark:text-[#8D9CB8]">
              Generating parametric bounding volumes, boolean port cutouts, and industrial PBR materials in real-time.
            </p>
          </div>

          {/* 3-Step Progressive Procedural Stepper */}
          <div className="flex items-center bg-[#F1F5F9] dark:bg-[#0F1832] p-1 rounded-xl border border-[#E2E8F0] dark:border-[#1E2C52]">
            <button
              onClick={() => setProceduralStep(1)}
              className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-all flex items-center gap-1.5 ${
                proceduralStep === 1
                  ? 'bg-white dark:bg-[#131E3D] text-brand-600 dark:text-brand-400 shadow-xs border border-[#CBD5E1]/60 dark:border-[#1E2C52]'
                  : 'text-[#64748B] dark:text-[#8D9CB8]'
              }`}
            >
              <Box className="w-3.5 h-3.5" />
              <span>1. Primitives</span>
            </button>
            <button
              onClick={() => setProceduralStep(2)}
              className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-all flex items-center gap-1.5 ${
                proceduralStep === 2
                  ? 'bg-white dark:bg-[#131E3D] text-brand-600 dark:text-brand-400 shadow-xs border border-[#CBD5E1]/60 dark:border-[#1E2C52]'
                  : 'text-[#64748B] dark:text-[#8D9CB8]'
              }`}
            >
              <Cpu className="w-3.5 h-3.5" />
              <span>2. CSG Booleans</span>
            </button>
            <button
              onClick={() => setProceduralStep(3)}
              className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-all flex items-center gap-1.5 ${
                proceduralStep === 3
                  ? 'bg-white dark:bg-[#131E3D] text-brand-600 dark:text-brand-400 shadow-xs border border-[#CBD5E1]/60 dark:border-[#1E2C52]'
                  : 'text-[#64748B] dark:text-[#8D9CB8]'
              }`}
            >
              <Sparkles className="w-3.5 h-3.5" />
              <span>3. PBR Final</span>
            </button>
          </div>
        </div>
      </div>

      {/* Main 3D CAD Viewport & Interactive Telemetry */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left 2 Cols */}
        <div className="lg:col-span-2 space-y-3">
          <ThreeCADViewer
            proceduralStep={proceduralStep}
            isInverted={isInverted}
            isPaused={isPaused}
            productName={activeProduct?.name}
          />

          {/* Interactive Human-In-The-Loop Action Bar */}
          <div className="tailadmin-card p-3.5 bg-white dark:bg-[#131E3D] flex flex-wrap items-center justify-between gap-3 text-xs">
            <div className="flex items-center gap-2">
              <span className="font-bold text-[#1C2434] dark:text-white">
                HITL Controls:
              </span>
              <button
                onClick={() => setIsPaused(!isPaused)}
                className="px-3 py-1.5 rounded-xl border border-[#CBD5E1] dark:border-[#1E2C52] bg-[#F8FAFC] dark:bg-[#0F1832] hover:bg-[#F1F5F9] dark:hover:bg-[#172449] font-semibold flex items-center gap-1.5 text-[#1C2434] dark:text-white"
              >
                {isPaused ? <Play className="w-3 h-3 text-emerald-500" /> : <Pause className="w-3 h-3 text-amber-500" />}
                <span>{isPaused ? 'Resume Turntable' : 'Pause Turntable'}</span>
              </button>

              <button
                onClick={() => setIsInverted(!isInverted)}
                className={`px-3 py-1.5 rounded-xl border font-semibold flex items-center gap-1.5 transition-all ${
                  isInverted
                    ? 'bg-amber-500 text-black border-amber-600 shadow-xs'
                    : 'bg-brand-50 dark:bg-brand-500/15 text-brand-600 dark:text-brand-300 border-brand-200 dark:border-brand-500/30 hover:bg-brand-100'
                }`}
              >
                <RotateCcw className="w-3 h-3" />
                <span>{isInverted ? 'Reset Port Carve' : 'Pause & Invert Port Cut'}</span>
              </button>
            </div>

            <div className="text-[11px] text-[#64748B] dark:text-[#8D9CB8]">
              White-box parametric control active
            </div>
          </div>
        </div>

        {/* Right Col */}
        <div className="space-y-4">
          <div className="tailadmin-card p-5 bg-white dark:bg-[#131E3D]">
            <h2 className="text-xs font-bold uppercase tracking-wider text-[#1C2434] dark:text-white mb-3 flex items-center gap-1.5">
              <Cpu className="w-3.5 h-3.5 text-brand-500" />
              Progressive CSG Assembly
            </h2>

            <div className="space-y-3 text-xs">
              <div
                onClick={() => setProceduralStep(1)}
                className={`p-3 rounded-xl border cursor-pointer transition-all ${
                  proceduralStep === 1
                    ? 'border-brand-500 bg-brand-50/40 dark:bg-brand-500/15'
                    : 'border-[#E2E8F0] dark:border-[#1E2C52] bg-[#F8FAFC]/50 dark:bg-[#0F1832]/60'
                }`}
              >
                <div className="flex items-center justify-between font-bold text-[#1C2434] dark:text-white mb-0.5">
                  <span>State 1: Bounding Wireframe</span>
                  <span className="text-[10px] text-brand-600 dark:text-brand-400">T = 0s</span>
                </div>
                <p className="text-[11px] text-[#64748B] dark:text-[#8D9CB8]">
                  Rectangular plate stack bounding volume + top/bottom guide bars.
                </p>
              </div>

              <div
                onClick={() => setProceduralStep(2)}
                className={`p-3 rounded-xl border cursor-pointer transition-all ${
                  proceduralStep === 2
                    ? 'border-brand-500 bg-brand-50/40 dark:bg-brand-500/15'
                    : 'border-[#E2E8F0] dark:border-[#1E2C52] bg-[#F8FAFC]/50 dark:bg-[#0F1832]/60'
                }`}
              >
                <div className="flex items-center justify-between font-bold text-[#1C2434] dark:text-white mb-0.5">
                  <span>State 2: CSG Solid Carve</span>
                  <span className="text-[10px] text-brand-600 dark:text-brand-400">T = 2s</span>
                </div>
                <p className="text-[11px] text-[#64748B] dark:text-[#8D9CB8]">
                  4x cylindrical nozzle holes carved into front/rear plates + bolt notches.
                </p>
              </div>

              <div
                onClick={() => setProceduralStep(3)}
                className={`p-3 rounded-xl border cursor-pointer transition-all ${
                  proceduralStep === 3
                    ? 'border-brand-500 bg-brand-50/40 dark:bg-brand-500/15'
                    : 'border-[#E2E8F0] dark:border-[#1E2C52] bg-[#F8FAFC]/50 dark:bg-[#0F1832]/60'
                }`}
              >
                <div className="flex items-center justify-between font-bold text-[#1C2434] dark:text-white mb-0.5">
                  <span>State 3: High-Poly Assembly &amp; PBR</span>
                  <span className="text-[10px] text-brand-600 dark:text-brand-400">T = 4s</span>
                </div>
                <p className="text-[11px] text-[#64748B] dark:text-[#8D9CB8]">
                  Industrial epoxy blue (#1A4B8B), stainless steel flanges, and 8x compression bolts.
                </p>
              </div>
            </div>
          </div>

          <div className="tailadmin-card p-5 bg-white dark:bg-[#131E3D]">
            <h2 className="text-xs font-bold uppercase tracking-wider text-[#1C2434] dark:text-white mb-3 flex items-center gap-1.5">
              <Activity className="w-3.5 h-3.5 text-blue-500" />
              Procedural Mesh Telemetry
            </h2>

            <div className="grid grid-cols-2 gap-2.5 text-xs">
              <div className="p-2.5 rounded-xl bg-[#F8FAFC] dark:bg-[#0F1832] border border-[#E2E8F0] dark:border-[#1E2C52]">
                <span className="text-[#64748B] dark:text-[#8D9CB8] block text-[10px]">Triangles</span>
                <span className="font-bold text-[#1C2434] dark:text-white">14,820</span>
              </div>
              <div className="p-2.5 rounded-xl bg-[#F8FAFC] dark:bg-[#0F1832] border border-[#E2E8F0] dark:border-[#1E2C52]">
                <span className="text-[#64748B] dark:text-[#8D9CB8] block text-[10px]">Vertices</span>
                <span className="font-bold text-[#1C2434] dark:text-white">7,412</span>
              </div>
              <div className="p-2.5 rounded-xl bg-[#F8FAFC] dark:bg-[#0F1832] border border-[#E2E8F0] dark:border-[#1E2C52]">
                <span className="text-[#64748B] dark:text-[#8D9CB8] block text-[10px]">Euler Score</span>
                <span className="font-bold text-emerald-500 dark:text-emerald-400">χ = 2 (Watertight)</span>
              </div>
              <div className="p-2.5 rounded-xl bg-[#F8FAFC] dark:bg-[#0F1832] border border-[#E2E8F0] dark:border-[#1E2C52]">
                <span className="text-[#64748B] dark:text-[#8D9CB8] block text-[10px]">CSG Latency</span>
                <span className="font-bold text-brand-500 dark:text-brand-400">340 ms</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Navigation Footer */}
      <div className="flex items-center justify-between pt-2">
        <button
          onClick={() => setCurrentStage(2)}
          className="flex items-center gap-2 px-4 py-2 text-xs font-semibold text-[#64748B] dark:text-[#8D9CB8] bg-white dark:bg-[#131E3D] hover:bg-[#F1F5F9] dark:hover:bg-[#172449] border border-[#CBD5E1] dark:border-[#1E2C52] rounded-xl transition-colors"
        >
          <ArrowLeft className="w-3.5 h-3.5" />
          <span>Back to Reference Approval</span>
        </button>

        <button
          onClick={handleProceedToQA}
          className="flex items-center gap-2 px-6 py-2.5 text-xs font-semibold text-white bg-emerald-600 hover:bg-emerald-700 rounded-xl shadow-md shadow-emerald-600/25 transition-all hover:scale-[1.01] active:scale-[0.99]"
        >
          <ShieldCheck className="w-4 h-4" />
          <span>Run In-Line QA Audit &amp; Approve</span>
          <ArrowRight className="w-3.5 h-3.5" />
        </button>
      </div>
    </div>
  );
}
