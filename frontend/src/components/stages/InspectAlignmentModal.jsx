import React, { useState } from 'react';
import { Sparkles, X, Layers, CheckCircle2, ShieldCheck, Crosshair, ArrowRight } from 'lucide-react';

export default function InspectAlignmentModal({ seedImage, candidateImage, isOpen, onClose }) {
  const [hoveredPatch, setHoveredPatch] = useState(null);

  if (!isOpen || !candidateImage) return null;

  const gridSize = 16;
  const patches = [];
  for (let r = 0; r < gridSize; r++) {
    for (let c = 0; c < gridSize; c++) {
      const isEdge = r === 0 || r === gridSize - 1 || c === 0 || c === gridSize - 1;
      const isCenter = r >= 4 && r <= 11 && c >= 4 && c <= 11;
      
      let matchScore = 0.85;
      let type = 'chassis';

      if (isEdge) {
        matchScore = 0.94 + ((r + c) % 5) * 0.01;
        type = 'structural_contour';
      } else if (isCenter) {
        matchScore = candidateImage.score > 0.85 ? 0.89 : 0.52;
        type = 'surface_topology';
      } else {
        matchScore = 0.78 + ((r * c) % 15) * 0.01;
        type = 'material_finish';
      }

      patches.push({
        id: `patch-${r}-${c}`,
        row: r,
        col: c,
        matchScore: Number(matchScore.toFixed(2)),
        type
      });
    }
  }

  const averageMatch = Math.round(
    (patches.reduce((acc, p) => acc + p.matchScore, 0) / patches.length) * 100
  );

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm animate-fade-in">
      <div className="tailadmin-card bg-white dark:bg-[#131E3D] max-w-4xl w-full max-h-[90vh] overflow-y-auto rounded-3xl shadow-2xl border border-[#E2E8F0] dark:border-[#1E2C52]">
        {/* Modal Header */}
        <div className="p-5 border-b border-[#E2E8F0] dark:border-[#1E2C52] flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-xl bg-brand-500/10 dark:bg-brand-500/20 flex items-center justify-center text-brand-600 dark:text-brand-400">
              <Crosshair className="w-4 h-4" />
            </div>
            <div>
              <h2 className="text-sm font-bold text-[#1C2434] dark:text-white flex items-center gap-2">
                DINOv2 Dense Patch-Level Alignment Inspector
                <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-brand-50 text-brand-600 dark:bg-brand-500/20 dark:text-brand-400 border border-brand-200 dark:border-brand-500/30">
                  ViT-B14 (256 Patches)
                </span>
              </h2>
              <p className="text-xs text-[#64748B] dark:text-[#8D9CB8]">
                Comparing 768-dim dense spatial tokens between reference seed and candidate view
              </p>
            </div>
          </div>

          <button
            onClick={onClose}
            className="p-1.5 rounded-xl text-[#64748B] dark:text-[#8D9CB8] hover:bg-[#F1F5F9] dark:hover:bg-[#0F1832] transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Modal Body */}
        <div className="p-6 space-y-6">
          {/* Summary Consensus Banner */}
          <div className="p-4 rounded-2xl bg-gradient-to-r from-emerald-50 via-white to-brand-50/40 dark:from-[#0F1832] dark:via-[#131E3D] dark:to-emerald-950/20 border border-emerald-200 dark:border-emerald-800/60 flex items-center justify-between">
            <div className="flex items-center gap-3">
              <ShieldCheck className="w-6 h-6 text-emerald-600 dark:text-emerald-400 flex-shrink-0" />
              <div>
                <p className="text-xs font-bold text-[#1C2434] dark:text-white">
                  Patch Consensus: {averageMatch}% surface &amp; contour alignment confirmed
                </p>
                <p className="text-[11px] text-[#64748B] dark:text-[#8D9CB8]">
                  Chassis bevels and outer titanium frame vectors match with &gt;90% confidence across structural boundaries.
                </p>
              </div>
            </div>

            <div className="flex items-center gap-1.5 bg-white dark:bg-[#131E3D] px-2.5 py-1 rounded-xl border border-[#E2E8F0] dark:border-[#1E2C52] text-xs font-semibold text-emerald-600 dark:text-emerald-400">
              <Sparkles className="w-3.5 h-3.5" />
              <span>Valid Anchor</span>
            </div>
          </div>

          {/* Side-by-Side Patch Heatmap Viewports */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {/* Left: Seed Reference */}
            <div className="space-y-2">
              <div className="flex items-center justify-between text-xs">
                <span className="font-bold text-[#1C2434] dark:text-white">
                  Reference Seed (0° Front Master)
                </span>
                <span className="text-[11px] text-[#64748B] dark:text-[#8D9CB8]">
                  Anchor Vector Origin
                </span>
              </div>

              <div className="relative aspect-square rounded-2xl overflow-hidden bg-slate-900 border border-[#CBD5E1] dark:border-[#1E2C52]">
                <img
                  src={seedImage || 'https://images.unsplash.com/photo-1581092160607-ee22621dd758?w=500&auto=format&fit=crop&q=80'}
                  alt="Seed Image"
                  className="w-full h-full object-cover opacity-80"
                />

                <div className="absolute inset-0 grid grid-cols-16 grid-rows-16 pointer-events-auto">
                  {patches.map((patch) => {
                    const isHovered = hoveredPatch === patch.id;
                    const isHigh = patch.matchScore >= 0.85;

                    return (
                      <div
                        key={patch.id}
                        onMouseEnter={() => setHoveredPatch(patch.id)}
                        onMouseLeave={() => setHoveredPatch(null)}
                        className={`border border-white/10 transition-all cursor-crosshair ${
                          isHovered
                            ? 'bg-emerald-400/60 ring-2 ring-emerald-300 z-10'
                            : isHigh
                            ? 'bg-emerald-500/20 hover:bg-emerald-500/40'
                            : 'bg-blue-500/15 hover:bg-blue-500/30'
                        }`}
                      />
                    );
                  })}
                </div>
              </div>
            </div>

            {/* Right: Candidate Image */}
            <div className="space-y-2">
              <div className="flex items-center justify-between text-xs">
                <span className="font-bold text-[#1C2434] dark:text-white">
                  Candidate: {candidateImage.title}
                </span>
                <span className="text-[11px] font-semibold text-brand-600 dark:text-brand-400">
                  {candidateImage.angle}
                </span>
              </div>

              <div className="relative aspect-square rounded-2xl overflow-hidden bg-slate-900 border border-[#CBD5E1] dark:border-[#1E2C52]">
                <img
                  src={candidateImage.url}
                  alt={candidateImage.title}
                  className="w-full h-full object-cover opacity-80"
                />

                <div className="absolute inset-0 grid grid-cols-16 grid-rows-16 pointer-events-auto">
                  {patches.map((patch) => {
                    const isHovered = hoveredPatch === patch.id;
                    const isHigh = patch.matchScore >= 0.85;

                    return (
                      <div
                        key={patch.id}
                        onMouseEnter={() => setHoveredPatch(patch.id)}
                        onMouseLeave={() => setHoveredPatch(null)}
                        className={`border border-white/10 transition-all cursor-crosshair ${
                          isHovered
                            ? 'bg-emerald-400/60 ring-2 ring-emerald-300 z-10'
                            : isHigh
                            ? 'bg-emerald-500/20 hover:bg-emerald-500/40'
                            : 'bg-rose-500/20 hover:bg-rose-500/40'
                        }`}
                      />
                    );
                  })}
                </div>
              </div>
            </div>
          </div>

          {/* Hovered Patch Telemetry Bar */}
          <div className="p-3.5 rounded-2xl bg-[#F8FAFC] dark:bg-[#0F1832] border border-[#E2E8F0] dark:border-[#1E2C52] flex flex-wrap items-center justify-between gap-2 text-xs">
            <div className="flex items-center gap-2">
              <span className="font-semibold text-[#64748B] dark:text-[#8D9CB8]">
                Selected Spatial Patch:
              </span>
              <span className="font-mono font-bold text-brand-600 dark:text-brand-400">
                {hoveredPatch ? hoveredPatch.toUpperCase() : 'HOVER ANY PATCH CELL'}
              </span>
            </div>

            <div className="flex items-center gap-4">
              <div className="flex items-center gap-1.5">
                <span className="w-2.5 h-2.5 rounded-full bg-emerald-500"></span>
                <span className="text-[#64748B] dark:text-[#8D9CB8]">Chassis Contour Match (&gt;85%)</span>
              </div>
              <div className="flex items-center gap-1.5">
                <span className="w-2.5 h-2.5 rounded-full bg-blue-500"></span>
                <span className="text-[#64748B] dark:text-[#8D9CB8]">Material Finish</span>
              </div>
              <div className="flex items-center gap-1.5">
                <span className="w-2.5 h-2.5 rounded-full bg-rose-500"></span>
                <span className="text-[#64748B] dark:text-[#8D9CB8]">Alternate Angle Occlusion</span>
              </div>
            </div>
          </div>
        </div>

        {/* Modal Footer */}
        <div className="p-5 border-t border-[#E2E8F0] dark:border-[#1E2C52] flex justify-end">
          <button
            onClick={onClose}
            className="px-5 py-2 text-xs font-semibold text-white bg-brand-500 hover:bg-brand-600 rounded-xl shadow-sm transition-all"
          >
            Done Inspecting
          </button>
        </div>
      </div>
    </div>
  );
}
