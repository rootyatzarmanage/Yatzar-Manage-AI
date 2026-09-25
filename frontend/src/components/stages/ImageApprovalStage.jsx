import React, { useState } from 'react';
import { useProducts } from '../../context/ProductContext';
import { 
  CheckCircle, 
  Layers, 
  Sparkles, 
  ArrowLeft, 
  ArrowRight, 
  Sliders, 
  Check, 
  AlertTriangle,
  Info,
  ShieldCheck,
  Cpu,
  Anchor,
  FileCheck
} from 'lucide-react';

export default function ImageApprovalStage() {
  const { activeProduct, updateActiveProduct, setCurrentStage } = useProducts();

  const [mode, setMode] = useState('guided');

  const handleProceedTo3D = () => {
    updateActiveProduct({
      currentStage: 3,
      approvalMode: mode
    });
    setCurrentStage(3); // Go to 3D Generate
  };

  const approvedCards = [
    {
      id: 'hex-1',
      title: 'hex_front_primary.jpg',
      url: 'https://images.unsplash.com/photo-1581092160607-ee22621dd758?w=500&auto=format&fit=crop&q=80',
      angle: '0° Front View',
      match: '96.4%',
      role: 'Base Frame Geometry & Mounting Rails',
      scope: 'Plate Stack Silhouette & Proportions'
    },
    {
      id: 'hex-2',
      title: 'hex_rear_nozzles.jpg',
      url: 'https://images.unsplash.com/photo-1581092580497-e0d23cbdf1dc?w=500&auto=format&fit=crop&q=80',
      angle: '180° Rear Ports',
      match: '87.1%',
      role: 'Fluid Connection Nozzles & Flange Diameters',
      scope: '4x Cylindrical Port Carves & Nozzle Placements'
    },
    {
      id: 'hex-3',
      title: 'hex_side_tightening_bolts.jpg',
      url: 'https://images.unsplash.com/photo-1581092335397-9583fe92d232?w=500&auto=format&fit=crop&q=80',
      angle: '90° Side Profile',
      match: '82.5%',
      role: 'Frame Depth & Compression Bolt Spacing',
      scope: 'Plate Pack Thickness (850mm) & 8x Perimeter Bolts'
    }
  ];

  return (
    <div className="max-w-6xl mx-auto p-4 md:p-6 space-y-5">
      {/* Top Header Card */}
      <div className="tailadmin-card p-5 bg-white dark:bg-[#131E3D]">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div>
            <div className="flex items-center gap-2 mb-1">
              <span className="px-2 py-0.5 rounded-md text-[10px] font-bold bg-brand-50 text-brand-600 dark:bg-brand-500/20 dark:text-brand-400 border border-brand-200 dark:border-brand-500/30">
                Phase 3 Consensus &amp; Dual-Mode Selection
              </span>
              <h1 className="text-base font-bold text-[#1C2434] dark:text-white">
                Reference Approval &amp; Attribute Evidence Matrix
              </h1>
            </div>
            <p className="text-xs text-[#64748B] dark:text-[#8D9CB8]">
              Fusing multi-angle vector anchors into a coherent procedural CAD construction graph.
            </p>
          </div>

          {/* Mode Selector Toggle */}
          <div className="flex items-center bg-[#F1F5F9] dark:bg-[#0F1832] p-1 rounded-xl border border-[#E2E8F0] dark:border-[#1E2C52]">
            <button
              onClick={() => setMode('autonomous')}
              className={`flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg text-xs font-semibold transition-all ${
                mode === 'autonomous'
                  ? 'bg-white dark:bg-[#131E3D] text-brand-600 dark:text-brand-400 shadow-xs border border-[#CBD5E1]/60 dark:border-[#1E2C52]'
                  : 'text-[#64748B] dark:text-[#8D9CB8]'
              }`}
            >
              <Cpu className="w-3.5 h-3.5" />
              <span>Mode A: Autonomous</span>
            </button>
            <button
              onClick={() => setMode('guided')}
              className={`flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg text-xs font-semibold transition-all ${
                mode === 'guided'
                  ? 'bg-white dark:bg-[#131E3D] text-brand-600 dark:text-brand-400 shadow-xs border border-[#CBD5E1]/60 dark:border-[#1E2C52]'
                  : 'text-[#64748B] dark:text-[#8D9CB8]'
              }`}
            >
              <Sliders className="w-3.5 h-3.5" />
              <span>Mode B: Guided Matrix</span>
            </button>
          </div>
        </div>
      </div>

      {/* Mode B Content */}
      {mode === 'guided' ? (
        <div className="space-y-5">
          {/* Approved Reference Cards */}
          <div className="tailadmin-card p-6 bg-white dark:bg-[#131E3D]">
            <div className="flex items-center justify-between mb-4">
              <div>
                <h2 className="text-xs font-bold uppercase tracking-wider text-[#1C2434] dark:text-white">
                  Approved Multi-Reference Anchor Set (3 Selected)
                </h2>
                <p className="text-xs text-[#64748B] dark:text-[#8D9CB8]">
                  Explicitly mapped references preventing false-positive hallucinations on occluded port geometries.
                </p>
              </div>
              <span className="inline-flex items-center gap-1 text-xs font-bold text-emerald-600 dark:text-emerald-400 bg-emerald-50 dark:bg-emerald-950/40 px-2.5 py-1 rounded-xl border border-emerald-200 dark:border-emerald-800">
                <CheckCircle className="w-3.5 h-3.5" /> 3 Angles Verified
              </span>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              {approvedCards.map((card) => (
                <div
                  key={card.id}
                  className="rounded-2xl border border-brand-500/40 bg-brand-50/10 dark:bg-brand-500/10 p-3.5 relative"
                >
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-xs font-bold text-[#1C2434] dark:text-white">
                      {card.angle}
                    </span>
                    <span className="px-1.5 py-0.5 rounded text-[10px] font-bold bg-emerald-500 text-white">
                      {card.match} Match
                    </span>
                  </div>

                  <div className="aspect-4/3 rounded-xl overflow-hidden bg-slate-900 border border-[#E2E8F0] dark:border-[#1E2C52] mb-2.5">
                    <img src={card.url} alt={card.title} className="w-full h-full object-cover" />
                  </div>

                  <div className="space-y-1">
                    <p className="text-[11px] font-mono font-bold text-brand-600 dark:text-brand-400 truncate">
                      {card.title}
                    </p>
                    <p className="text-xs font-semibold text-[#1C2434] dark:text-white leading-snug">
                      {card.role}
                    </p>
                    <p className="text-[10px] text-[#64748B] dark:text-[#8D9CB8]">
                      Scope: {card.scope}
                    </p>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Attribute Evidence Matrix Table */}
          <div className="tailadmin-card p-6 bg-white dark:bg-[#131E3D]">
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-2">
                <FileCheck className="w-4 h-4 text-brand-500" />
                <h2 className="text-xs font-bold uppercase tracking-wider text-[#1C2434] dark:text-white">
                  Attribute Evidence Matrix (Feature Binding)
                </h2>
              </div>
              <span className="text-xs font-semibold text-emerald-600 dark:text-emerald-400">
                100% Parameter Consistency Confirmed
              </span>
            </div>

            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead>
                  <tr className="border-b border-[#E2E8F0] dark:border-[#1E2C52] text-[#64748B] dark:text-[#8D9CB8]">
                    <th className="pb-2.5 font-semibold">Physical Feature</th>
                    <th className="pb-2.5 font-semibold">Authoritative Source</th>
                    <th className="pb-2.5 font-semibold">CAD Synthesis Directive</th>
                    <th className="pb-2.5 font-semibold text-right">Confidence</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[#E2E8F0] dark:divide-[#1E2C52]">
                  <tr>
                    <td className="py-3 font-semibold text-[#1C2434] dark:text-white">Base Frame &amp; Plate Stack</td>
                    <td className="py-3 text-[#64748B] dark:text-[#8D9CB8]">hex_front_primary.jpg (0°)</td>
                    <td className="py-3 font-mono text-[11px] text-brand-600 dark:text-brand-400">
                      Spawn Box(1200 x 1800 x 850) + Top/Bottom Guide Bars
                    </td>
                    <td className="py-3 text-right font-bold text-emerald-500 dark:text-emerald-400">96.4%</td>
                  </tr>
                  <tr>
                    <td className="py-3 font-semibold text-[#1C2434] dark:text-white">Fluid Connection Nozzles</td>
                    <td className="py-3 text-[#64748B] dark:text-[#8D9CB8]">hex_rear_nozzles.jpg (180°)</td>
                    <td className="py-3 font-mono text-[11px] text-brand-600 dark:text-brand-400">
                      CSG Boolean Carve: 4x Cylinders (D=190mm) at corner offsets
                    </td>
                    <td className="py-3 text-right font-bold text-emerald-500 dark:text-emerald-400">91.2%</td>
                  </tr>
                  <tr>
                    <td className="py-3 font-semibold text-[#1C2434] dark:text-white">Tightening Bolts Spacing</td>
                    <td className="py-3 text-[#64748B] dark:text-[#8D9CB8]">hex_side_tightening_bolts.jpg (90°)</td>
                    <td className="py-3 font-mono text-[11px] text-brand-600 dark:text-brand-400">
                      Array 8x Compression Bolts along frame perimeter
                    </td>
                    <td className="py-3 text-right font-bold text-emerald-500 dark:text-emerald-400">89.5%</td>
                  </tr>
                  <tr>
                    <td className="py-3 font-semibold text-[#1C2434] dark:text-white">Industrial Powder Coat Material</td>
                    <td className="py-3 text-[#64748B] dark:text-[#8D9CB8]">hex_front_primary.jpg (0°)</td>
                    <td className="py-3 font-mono text-[11px] text-brand-600 dark:text-brand-400">
                      Alfa Laval Blue (#1A4B8B), Metalness: 0.78, Roughness: 0.28
                    </td>
                    <td className="py-3 text-right font-bold text-emerald-500 dark:text-emerald-400">95.0%</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        </div>
      ) : (
        /* Mode A */
        <div className="tailadmin-card p-8 bg-white dark:bg-[#131E3D] text-center">
          <div className="w-16 h-16 rounded-2xl bg-brand-500/10 dark:bg-brand-500/20 text-brand-600 dark:text-brand-400 flex items-center justify-center mx-auto mb-4">
            <Cpu className="w-8 h-8" />
          </div>
          <h2 className="text-base font-bold text-[#1C2434] dark:text-white mb-1">
            Autonomous Single-Reference Reconstruction (Mode A)
          </h2>
          <p className="text-xs text-[#64748B] dark:text-[#8D9CB8] max-w-lg mx-auto mb-6">
            Leveraging seed reference prior for rapid single-click CAD output.
          </p>
        </div>
      )}

      {/* Footer Navigation */}
      <div className="flex items-center justify-between pt-2">
        <button
          onClick={() => setCurrentStage(1)}
          className="flex items-center gap-2 px-4 py-2 text-xs font-semibold text-[#64748B] dark:text-[#8D9CB8] bg-white dark:bg-[#131E3D] hover:bg-[#F1F5F9] dark:hover:bg-[#172449] border border-[#CBD5E1] dark:border-[#1E2C52] rounded-xl transition-colors"
        >
          <ArrowLeft className="w-3.5 h-3.5" />
          <span>Back to Scraped Data &amp; Vectors</span>
        </button>

        <button
          onClick={handleProceedTo3D}
          className="flex items-center gap-2 px-6 py-2.5 text-xs font-semibold text-white bg-brand-500 hover:bg-brand-600 rounded-xl shadow-md shadow-brand-500/25 transition-all hover:scale-[1.01] active:scale-[0.99]"
        >
          <Sparkles className="w-3.5 h-3.5" />
          <span>Proceed to 3D CAD Generation</span>
          <ArrowRight className="w-3.5 h-3.5" />
        </button>
      </div>
    </div>
  );
}
