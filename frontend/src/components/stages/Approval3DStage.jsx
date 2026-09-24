import React, { useEffect } from 'react';
import { useProducts } from '../../context/ProductContext';
import confetti from 'canvas-confetti';
import { 
  CheckCircle2, 
  Download, 
  FileText, 
  Sparkles, 
  ArrowLeft, 
  ShieldCheck, 
  Layers, 
  ExternalLink,
  Printer,
  Box,
  Check
} from 'lucide-react';

export default function Approval3DStage() {
  const { activeProduct, setCurrentStage } = useProducts();

  const qaAudit = activeProduct?.qaAudit || {
    overallIntegrity: 0.938,
    isWatertight: true,
    eulerCharacteristic: 2,
    nonManifoldEdges: 0,
    portDiameterAlignment: 0.912,
    colorDeltaE: 1.2,
    orthogonalViews: [
      { label: 'Rendered Image 01 (0° Front Master)', view: '0° Front Orthogonal', score: 0.964, img: 'https://images.unsplash.com/photo-1581092160607-ee22621dd758?w=400&auto=format&fit=crop&q=80' },
      { label: 'Rendered Image 02 (90° Side Profile)', view: '90° Profile Left', score: 0.925, img: 'https://images.unsplash.com/photo-1581092335397-9583fe92d232?w=400&auto=format&fit=crop&q=80' },
      { label: 'Rendered Image 03 (180° Rear Nozzles)', view: '180° Rear Ports', score: 0.912, img: 'https://images.unsplash.com/photo-1581092580497-e0d23cbdf1dc?w=400&auto=format&fit=crop&q=80' },
      { label: 'Rendered Image 04 (270° Port Flange Detail)', view: '270° Flange Cavities', score: 0.941, img: 'https://images.unsplash.com/photo-1581091226825-a6a2a5aee158?w=400&auto=format&fit=crop&q=80' },
      { label: 'Rendered Image 05 (Isometric Studio Master)', view: 'Isometric Studio', score: 0.958, img: 'https://images.unsplash.com/photo-1581092795360-fd1ca04f0952?w=400&auto=format&fit=crop&q=80' },
      { label: 'Rendered Image 06 (CSG Watertight Topology)', view: 'Solid CSG Manifold', score: 0.982, img: 'https://images.unsplash.com/photo-1581093458791-9f3c3900df4b?w=400&auto=format&fit=crop&q=80' }
    ]
  };

  useEffect(() => {
    try {
      confetti({
        particleCount: 80,
        spread: 70,
        origin: { y: 0.6 }
      });
    } catch (e) {
      // ignore
    }
  }, []);

  const handleDownloadAsset = (filename, content, type = 'application/octet-stream') => {
    const blob = new Blob([content], { type });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  };

  const handleDownloadGLB = () => {
    const glbHeader = new Uint8Array([
      0x67, 0x6c, 0x54, 0x46,
      0x02, 0x00, 0x00, 0x00,
      0x48, 0x00, 0x00, 0x00,
      0x1c, 0x00, 0x00, 0x00,
      0x4a, 0x53, 0x4f, 0x4e,
      0x7b, 0x22, 0x61, 0x73, 0x73, 0x65, 0x74, 0x22, 0x3a, 0x7b, 0x22, 0x76, 0x65, 0x72, 0x73, 0x69, 0x6f, 0x6e, 0x22, 0x3a, 0x22, 0x32, 0x2e, 0x30, 0x22, 0x7d, 0x7d, 0x20
    ]);
    handleDownloadAsset(`alfa_laval_heat_exchanger_watertight.glb`, glbHeader, 'model/gltf-binary');
  };

  const handleDownloadUSDZ = () => {
    handleDownloadAsset(`alfa_laval_heat_exchanger.usdz`, 'Mock USDZ Container Package for Apple AR');
  };

  return (
    <div className="max-w-6xl mx-auto p-4 md:p-6 space-y-5">
      {/* Top Banner */}
      <div className="tailadmin-card p-4 md:p-5 bg-gradient-to-r from-emerald-50 via-white to-brand-50/40 dark:from-[#131E3D] dark:via-[#0F1A34] dark:to-emerald-950/20 border-emerald-200 dark:border-[#1E2C52] shadow-xs flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-emerald-500 text-white flex items-center justify-center shadow-md shadow-emerald-500/30">
            <ShieldCheck className="w-6 h-6" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-sm font-bold text-[#1C2434] dark:text-white">
                Two-Tier QA Audit Passed
              </h2>
              <span className="px-2.5 py-0.5 rounded-full text-[10px] font-bold bg-emerald-100 dark:bg-emerald-950/60 text-emerald-700 dark:text-emerald-400 border border-emerald-200 dark:border-emerald-800">
                100% Watertight • 93.8% Overall Integrity
              </span>
            </div>
            <p className="text-xs text-[#64748B] dark:text-[#8D9CB8]">
              Model certified by Level 1 (Euler $\chi=2$, 0 non-manifold edges) &amp; Level 2 (6-axis virtual camera rig).
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={handleDownloadGLB}
            className="flex items-center gap-1.5 px-4 py-2 text-xs font-semibold text-white bg-brand-500 hover:bg-brand-600 rounded-xl shadow-sm transition-all hover:scale-[1.02] active:scale-[0.98]"
          >
            <Download className="w-3.5 h-3.5" />
            <span>Download .GLB</span>
          </button>
          <button
            onClick={handleDownloadUSDZ}
            className="flex items-center gap-1.5 px-4 py-2 text-xs font-semibold text-[#1C2434] dark:text-white bg-white dark:bg-[#0F1832] border border-[#CBD5E1] dark:border-[#1E2C52] hover:bg-[#F8FAFC] dark:hover:bg-[#131E3D] rounded-xl transition-colors shadow-2xs"
          >
            <Download className="w-3.5 h-3.5" />
            <span>Download .USDZ</span>
          </button>
        </div>
      </div>

      {/* Reconstruction QA Scorecard */}
      <div className="tailadmin-card p-6 bg-white dark:bg-[#131E3D]">
        <h2 className="text-xs font-bold uppercase tracking-wider text-[#1C2434] dark:text-white mb-4">
          Reconstruction QA Scorecard
        </h2>

        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 text-xs">
          <div className="p-3.5 rounded-2xl bg-emerald-50/50 dark:bg-emerald-950/30 border border-emerald-200 dark:border-emerald-800/60">
            <span className="text-[#64748B] dark:text-[#8D9CB8] text-[10px] block font-medium">Overall Integrity</span>
            <span className="text-base font-bold text-emerald-600 dark:text-emerald-400">93.8% (PASS)</span>
          </div>

          <div className="p-3.5 rounded-2xl bg-emerald-50/50 dark:bg-emerald-950/30 border border-emerald-200 dark:border-emerald-800/60">
            <span className="text-[#64748B] dark:text-[#8D9CB8] text-[10px] block font-medium">Manifold Integrity</span>
            <span className="text-base font-bold text-emerald-600 dark:text-emerald-400">100% Watertight</span>
            <span className="text-[10px] text-[#64748B] dark:text-[#8D9CB8] block">0 non-manifold edges</span>
          </div>

          <div className="p-3.5 rounded-2xl bg-blue-50/50 dark:bg-blue-950/30 border border-blue-200 dark:border-blue-800/60">
            <span className="text-[#64748B] dark:text-[#8D9CB8] text-[10px] block font-medium">Port Layout Alignment</span>
            <span className="text-base font-bold text-blue-600 dark:text-blue-400">91.2% Match</span>
            <span className="text-[10px] text-[#64748B] dark:text-[#8D9CB8] block">vs Card 2 (hex_rear_nozzles)</span>
          </div>

          <div className="p-3.5 rounded-2xl bg-purple-50/50 dark:bg-purple-950/30 border border-purple-200 dark:border-purple-800/60">
            <span className="text-[#64748B] dark:text-[#8D9CB8] text-[10px] block font-medium">Chassis Color Delta (ΔE)</span>
            <span className="text-base font-bold text-purple-600 dark:text-purple-400">1.2 ΔE</span>
            <span className="text-[10px] text-[#64748B] dark:text-[#8D9CB8] block">Within industrial spec</span>
          </div>
        </div>
      </div>

      {/* Engineering 6-Axis Orthogonal Render View Matrix */}
      <div className="tailadmin-card p-6 md:p-8 bg-white dark:bg-[#131E3D] shadow-tailadmin">
        {/* Document Header */}
        <div className="flex items-center justify-between pb-4 mb-6 border-b-2 border-[#1C2434] dark:border-[#1E2C52]">
          <div>
            <span className="text-[10px] uppercase font-bold tracking-widest text-[#64748B] dark:text-[#8D9CB8] block">
              PRODUCTION 3D ASSET AUDIT SHEET
            </span>
            <h1 className="text-xl font-black text-[#1C2434] dark:text-white tracking-tight">
              06_{activeProduct?.name || 'Alfa Laval Industrial Plate Heat Exchanger'}
            </h1>
          </div>
          <div className="text-right text-xs">
            <span className="font-semibold text-emerald-600 dark:text-emerald-400 block flex items-center justify-end gap-1">
              <CheckCircle2 className="w-3.5 h-3.5" /> APPROVED
            </span>
            <span className="text-[#64748B] dark:text-[#8D9CB8] text-[11px]">
              SKU: {activeProduct?.id || 'AL-HEX-TL10-P'}
            </span>
          </div>
        </div>

        {/* 6-Axis Orthogonal Render View Matrix */}
        <div className="grid grid-cols-2 md:grid-cols-3 gap-6 mb-8">
          {qaAudit.orthogonalViews.map((item, idx) => (
            <div
              key={idx}
              className="border border-[#CBD5E1] dark:border-[#1E2C52] rounded-2xl p-3 bg-[#F8FAFC]/50 dark:bg-[#0F1832]/60 flex flex-col justify-between"
            >
              {/* Image Viewport */}
              <div className="aspect-4/3 rounded-xl overflow-hidden bg-white dark:bg-[#0B1120] border border-[#E2E8F0] dark:border-[#1E2C52] mb-2 relative group">
                <img
                  src={item.img}
                  alt={item.label}
                  className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-300"
                />
                <span className="absolute bottom-1.5 left-1.5 px-1.5 py-0.5 rounded-md bg-black/80 text-white text-[10px] font-semibold backdrop-blur-xs">
                  {item.view}
                </span>
                <span className="absolute top-1.5 right-1.5 px-1.5 py-0.5 rounded-md bg-emerald-500 text-white text-[10px] font-bold shadow-2xs">
                  {(item.score * 100).toFixed(1)}% Sim
                </span>
              </div>

              {/* Caption */}
              <div className="text-center pt-1 border-t border-[#E2E8F0] dark:border-[#1E2C52]">
                <p className="text-[11px] font-bold text-[#1C2434] dark:text-white">
                  {item.label}
                </p>
              </div>
            </div>
          ))}
        </div>

        {/* Action Footer */}
        <div className="flex items-center justify-between pt-4 border-t border-[#E2E8F0] dark:border-[#1E2C52]">
          <button
            onClick={() => setCurrentStage(3)}
            className="flex items-center gap-2 px-4 py-2 text-xs font-semibold text-[#64748B] dark:text-[#8D9CB8] bg-white dark:bg-[#131E3D] hover:bg-[#F1F5F9] dark:hover:bg-[#172449] border border-[#CBD5E1] dark:border-[#1E2C52] rounded-xl transition-colors"
          >
            <ArrowLeft className="w-3.5 h-3.5" />
            <span>Back to 3D Viewport</span>
          </button>

          <div className="flex items-center gap-2">
            <button
              onClick={() => window.print()}
              className="flex items-center gap-1.5 px-4 py-2 text-xs font-semibold text-[#1C2434] dark:text-white bg-white dark:bg-[#0F1832] border border-[#CBD5E1] dark:border-[#1E2C52] hover:bg-[#F8FAFC] dark:hover:bg-[#131E3D] rounded-xl transition-colors shadow-2xs"
            >
              <Printer className="w-3.5 h-3.5 text-[#64748B] dark:text-[#8D9CB8]" />
              <span>Print Audit Sheet</span>
            </button>

            <button
              onClick={handleDownloadGLB}
              className="flex items-center gap-1.5 px-6 py-2 text-xs font-semibold text-white bg-brand-500 hover:bg-brand-600 rounded-xl shadow-md shadow-brand-500/25 transition-all hover:scale-[1.01] active:scale-[0.99]"
            >
              <Download className="w-3.5 h-3.5" />
              <span>Download Production Package (.GLB)</span>
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
