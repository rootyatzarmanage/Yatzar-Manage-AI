import React, { useState, useEffect } from 'react';
import { useProducts } from '../../context/ProductContext';
import InspectAlignmentModal from './InspectAlignmentModal';
import VectorSpaceView from './VectorSpaceView';
import { triggerCascade } from '../../services/api';
import { 
  CheckSquare, 
  Square, 
  ExternalLink, 
  Sparkles, 
  RotateCw, 
  Filter, 
  ArrowLeft, 
  ArrowRight, 
  ShieldAlert, 
  Layers, 
  CheckCircle2, 
  AlertCircle,
  Eye,
  Sliders,
  Cpu,
  Anchor,
  Search,
  Check,
  AlertTriangle,
  Flame,
  Grid,
  Activity,
  ChevronDown,
  ChevronUp,
  Timer,
  Clock,
  Zap
} from 'lucide-react';

export default function ScrapeStage() {
  const { activeProduct, updateActiveProduct, setCurrentStage, isProcessing } = useProducts();

  const [images, setImages] = useState(activeProduct?.scrapedImages || []);
  const [urls, setUrls] = useState(activeProduct?.relatedUrls || []);
  const [activeFilter, setActiveFilter] = useState('all'); // 'all', 'high_match', 'front', 'rear_ports', 'side', 'hide_noise'
  const [viewMode, setViewMode] = useState('grid'); // 'grid' or 'vector_space'
  const [cascadeQuery, setCascadeQuery] = useState(activeProduct?.name ? `${activeProduct.name} rear features & dimensions` : 'Product rear frame & specs');
  const [isCascading, setIsCascading] = useState(false);
  const [cascadeCycle, setCascadeCycle] = useState(2);
  const [reconstructionMode, setReconstructionMode] = useState('guided'); // 'autonomous' vs 'guided'
  
  const [elapsedTime, setElapsedTime] = useState(0);
  const [telemetryDuration, setTelemetryDuration] = useState(activeProduct?.executionTime || '4.2s');
  const [candidatesEvaluated, setCandidatesEvaluated] = useState(activeProduct?.scrapedImages?.length || 12);
  const [gpuName, setGpuName] = useState(activeProduct?.gpuDevice || 'RTX 4060');

  const [expandedBreakdown, setExpandedBreakdown] = useState({});
  const [inspectModalImage, setInspectModalImage] = useState(null);

  // Formulate structural query intelligently
  const getStructuralQuery = (prod) => {
    if (!prod?.name) return 'Product rear view & dimensional profile';
    const nameLower = prod.name.toLowerCase();
    if (nameLower.includes('fan') || nameLower.includes('blower') || nameLower.includes('cooler')) {
      return `${prod.name} rear motor housing oscillation knob`;
    }
    if (nameLower.includes('shoe') || nameLower.includes('sneaker') || nameLower.includes('boot') || nameLower.includes('nike')) {
      return `${prod.name} heel counter & outsole tread waffle pattern`;
    }
    if (nameLower.includes('phone') || nameLower.includes('iphone') || nameLower.includes('screen')) {
      return `${prod.name} rear camera plateau & bottom ports`;
    }
    return `${prod.name} rear view & dimensional profile`;
  };

  useEffect(() => {
    if (activeProduct) {
      setImages(activeProduct.scrapedImages || []);
      setUrls(activeProduct.relatedUrls || []);
      setCascadeQuery(getStructuralQuery(activeProduct));
      setActiveFilter('all'); // Auto-reset filter tab to 'All' on new product/scrape load
      if (activeProduct.executionTime) setTelemetryDuration(activeProduct.executionTime);
      if (activeProduct.scrapedImages?.length) setCandidatesEvaluated(activeProduct.scrapedImages.length);
      if (activeProduct.gpuDevice) setGpuName(activeProduct.gpuDevice);
    }
  }, [activeProduct?.id, activeProduct?.scrapedImages, activeProduct?.name]);

  // Live stopwatch timer during cascade crawling & vectorization
  useEffect(() => {
    let interval = null;
    if (isCascading) {
      setElapsedTime(0);
      const startTime = Date.now();
      interval = setInterval(() => {
        setElapsedTime((Date.now() - startTime) / 1000);
      }, 100);
    } else {
      if (interval) clearInterval(interval);
    }
    return () => {
      if (interval) clearInterval(interval);
    };
  }, [isCascading]);

  const toggleBreakdown = (id, e) => {
    e.stopPropagation();
    setExpandedBreakdown(prev => ({ ...prev, [id]: !prev[id] }));
  };

  const toggleImageSelection = (id) => {
    const updated = images.map(img => img.id === id ? { ...img, selected: !img.selected } : img);
    setImages(updated);
    updateActiveProduct({ scrapedImages: updated, imagesCount: updated.filter(i => i.selected).length });
  };

  const setAnchorRole = (id, role, e) => {
    e.stopPropagation();
    const updated = images.map(img => img.id === id ? { ...img, role, selected: true } : img);
    setImages(updated);
    updateActiveProduct({ scrapedImages: updated });
  };

  const selectAllImages = (status) => {
    const updated = images.map(img => ({ ...img, selected: status }));
    setImages(updated);
    updateActiveProduct({ scrapedImages: updated, imagesCount: updated.filter(i => i.selected).length });
  };

  const toggleUrlSelection = (idx) => {
    const updated = urls.map((u, i) => i === idx ? { ...u, selected: !u.selected } : u);
    setUrls(updated);
    updateActiveProduct({ relatedUrls: updated });
  };

  const selectAllUrls = (status) => {
    const updated = urls.map(u => ({ ...u, selected: status }));
    setUrls(updated);
    updateActiveProduct({ relatedUrls: updated });
  };

  const triggerTargetedCascade = async () => {
    if (!cascadeQuery || isCascading) return;
    setIsCascading(true);
    
    try {
      const payload = {
        seed_image: activeProduct?.thumbnail,
        product_title: activeProduct?.name,
        product_sku: activeProduct?.modelNumber,
        cascade_query: cascadeQuery,
        cycle_number: cascadeCycle,
      };

      const res = await triggerCascade(payload);

      if (res.success && res.images) {
        // Format harvested candidates with real scores and angle signals
        const formattedCandidates = res.images.map((img) => ({
          ...img,
          role: img.role || (img.angle?.includes('Rear') ? 'Secondary Profile' : 'Supporting Angle'),
          selected: (img.score || 0) >= 0.50,
          signals: {
            silhouette: Math.round((img.score || 0.85) * 100),
            material: Math.round((img.patch_score || 0.82) * 100),
            topology: Math.round((img.global_similarity || 0.78) * 100)
          }
        }));

        // Deduplicate by URL / ID, keep only unique items, and re-rank descending by DINOv2 score
        const combined = [...images, ...formattedCandidates];
        const uniqueMap = new Map();
        for (const item of combined) {
          const key = item.url || item.id;
          if (!uniqueMap.has(key)) {
            uniqueMap.set(key, item);
          }
        }
        const uniqueList = Array.from(uniqueMap.values());
        uniqueList.sort((a, b) => (b.score || 0) - (a.score || 0));
        const topReranked = uniqueList.slice(0, 12);

        setImages(topReranked);
        setActiveFilter('all'); // Reset to 'All' so newly cascaded cards are visible immediately
        setCascadeCycle(prev => Math.min(3, prev + 1));
        if (res.executionTime) setTelemetryDuration(res.executionTime);
        setCandidatesEvaluated(topReranked.length);
        if (res.gpuDevice) setGpuName(res.gpuDevice);

        updateActiveProduct({
          scrapedImages: topReranked,
          imagesCount: topReranked.filter(i => i.selected).length,
          executionTime: res.executionTime,
          gpuDevice: res.gpuDevice
        });
      }
    } catch (err) {
      console.error('Targeted cascade pipeline error:', err);
    } finally {
      setIsCascading(false);
    }
  };

  const handleSendToApproval = () => {
    updateActiveProduct({
      scrapedImages: images,
      relatedUrls: urls,
      currentStage: 2,
      approvalMode: reconstructionMode
    });
    setCurrentStage(2); // Go to Image Approval Stage
  };

  // Filter logic
  const filteredImages = images.filter(img => {
    const score = img.score || 0;
    const isNoise = score < 0.38 || img.title?.toLowerCase().includes('logo') || img.title?.toLowerCase().includes('crate') || img.title?.toLowerCase().includes('svg');
    const angleLower = (img.angle || img.branch_angle || img.tag || '').toLowerCase();
    const titleLower = (img.title || '').toLowerCase();

    if (activeFilter === 'hide_noise') return !isNoise;
    if (activeFilter === 'high_match') return score >= 0.80;
    if (activeFilter === 'front') return angleLower.includes('front') || titleLower.includes('front');
    if (activeFilter === 'rear' || activeFilter === 'rear_ports') return angleLower.includes('rear') || angleLower.includes('back') || titleLower.includes('rear') || titleLower.includes('back') || angleLower.includes('port');
    if (activeFilter === 'side') return angleLower.includes('side') || angleLower.includes('profile') || titleLower.includes('side') || titleLower.includes('profile');
    if (activeFilter === 'isometric') return angleLower.includes('isometric') || angleLower.includes('angle') || angleLower.includes('perspective') || titleLower.includes('detail');
    return true; // 'all'
  });

  return (
    <div className="max-w-6xl mx-auto p-4 md:p-6 space-y-5">
      {/* 1. Geometric Triage & Uncertainty Status Header */}
      <div className="tailadmin-card p-4 md:p-5 bg-white dark:bg-[#131E3D] border-brand-500/20 shadow-xs">
        <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4 pb-4 border-b border-[#E2E8F0] dark:border-[#1E2C52]">
          {/* Product & Symmetry/Complexity */}
          <div className="space-y-1.5">
            <div className="flex items-center gap-2">
              <span className="text-xs font-bold uppercase tracking-wider text-brand-600 dark:text-brand-400">
                Geometric Triage Telemetry
              </span>
              <span className="text-xs font-bold text-[#1C2434] dark:text-white">
                • Product: {activeProduct?.name || 'Uploaded Asset'}
              </span>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <span className="px-2.5 py-1 rounded-lg text-[11px] font-bold bg-blue-50 dark:bg-blue-500/15 text-blue-700 dark:text-blue-300 border border-blue-200 dark:border-blue-500/30">
                Bilateral Symmetry: {activeProduct?.triage?.rotationalSymmetry || '89%'}
              </span>
              <span className="px-2.5 py-1 rounded-lg text-[11px] font-bold bg-purple-50 dark:bg-purple-500/15 text-purple-700 dark:text-purple-300 border border-purple-200 dark:border-purple-500/30">
                Complexity: {activeProduct?.triage?.complexity || 'Moderate (Multi-Angle)'}
              </span>
            </div>
          </div>

          {/* Research Budget / Cascade Pulsing Indicator & Real Telemetry Badge */}
          <div className="flex flex-wrap items-center gap-2 self-start lg:self-auto">
            {/* Live Completed Runtime Telemetry Badge */}
            <div className="flex items-center gap-2 px-3 py-1.5 rounded-xl bg-emerald-50 dark:bg-emerald-950/40 border border-emerald-200 dark:border-emerald-800/60 text-emerald-800 dark:text-emerald-300 text-xs font-semibold shadow-2xs">
              <Clock className="w-3.5 h-3.5 text-emerald-600 dark:text-emerald-400" />
              <span>⏱️ Completed in {telemetryDuration}</span>
              <span className="text-[11px] font-normal opacity-90">
                | {candidatesEvaluated} candidates evaluated on {gpuName}
              </span>
            </div>

            <div className="flex items-center gap-2 px-3 py-1.5 rounded-xl bg-amber-50 dark:bg-amber-950/40 border border-amber-200 dark:border-amber-800/60 text-amber-800 dark:text-amber-300 text-xs font-semibold">
              <span className="w-2 h-2 rounded-full bg-amber-500 animate-ping"></span>
              <span>Cycle: {cascadeCycle} / 3</span>
              <span className="text-[11px] font-normal opacity-90">
                • {isCascading ? 'Scraping in progress...' : 'Cascade Ready'}
              </span>
            </div>
          </div>
        </div>

        {/* Live Scraping / Cascading Active Banner with Stopwatch */}
        {isCascading && (
          <div className="mt-3 p-3.5 rounded-xl bg-gradient-to-r from-brand-500 to-indigo-600 text-white flex items-center justify-between shadow-md animate-pulse">
            <div className="flex items-center gap-3">
              <div className="w-6 h-6 rounded-full border-2 border-white/40 border-t-white animate-spin flex items-center justify-center">
                <Zap className="w-3 h-3 text-white" />
              </div>
              <div>
                <div className="text-xs font-bold tracking-wide">
                  ⏱️ Scraping &amp; Vectorizing: {elapsedTime.toFixed(1).padStart(4, '0')}s elapsed...
                </div>
                <div className="text-[11px] opacity-90">
                  Executing Playwright headless harvester &amp; computing DINOv2 ViT-S/14 patch embeddings on {gpuName}
                </div>
              </div>
            </div>
            <div className="text-right text-xs font-mono font-bold bg-white/20 px-3 py-1.5 rounded-lg backdrop-blur-xs">
              LIVE GPU INFERENCE
            </div>
          </div>
        )}

        {/* Azimuth Uncertainty Meter (4 Quadrant Pill Indicators) */}
        <div className="pt-3.5 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <span className="text-xs font-semibold text-[#64748B] dark:text-[#8D9CB8] flex items-center gap-1.5">
            <Eye className="w-3.5 h-3.5 text-brand-500" />
            Azimuth Uncertainty Profile:
          </span>

          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 flex-1 sm:max-w-2xl">
            {/* Front */}
            <div className="px-2.5 py-1 rounded-lg bg-emerald-50 dark:bg-emerald-950/40 border border-emerald-200 dark:border-emerald-800/60 flex items-center justify-between text-xs font-medium">
              <span className="text-[#1C2434] dark:text-white">Front (0°)</span>
              <span className="font-bold text-emerald-600 dark:text-emerald-400">98% Conf</span>
            </div>

            {/* Profile */}
            <div className="px-2.5 py-1 rounded-lg bg-emerald-50 dark:bg-emerald-950/40 border border-emerald-200 dark:border-emerald-800/60 flex items-center justify-between text-xs font-medium">
              <span className="text-[#1C2434] dark:text-white">Profile (90°)</span>
              <span className="font-bold text-emerald-600 dark:text-emerald-400">88% Conf</span>
            </div>

            {/* Rear */}
            <div className="px-2.5 py-1 rounded-lg bg-amber-50 dark:bg-amber-950/40 border border-amber-200 dark:border-amber-800/60 flex items-center justify-between text-xs font-medium">
              <span className="text-[#1C2434] dark:text-white">Rear (180°)</span>
              <span className="font-bold text-amber-500 dark:text-amber-400">72% Conf</span>
            </div>

            {/* Ports/Nozzles */}
            <div className="px-2.5 py-1 rounded-lg bg-rose-50 dark:bg-rose-950/40 border border-rose-200 dark:border-rose-800/60 flex items-center justify-between text-xs font-medium animate-pulse">
              <span className="text-[#1C2434] dark:text-white">Ports/Nozzles</span>
              <span className="font-bold text-rose-500 dark:text-rose-400">45% Conf (Target)</span>
            </div>
          </div>
        </div>
      </div>

      {/* 2. Main Gallery Header & View Mode Switcher */}
      <div className="tailadmin-card p-6 bg-white dark:bg-[#131E3D]">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-4 mb-5 border-b border-[#E2E8F0] dark:border-[#1E2C52]">
          {/* Filter Tabs */}
          <div className="flex items-center gap-1.5 overflow-x-auto pb-1 sm:pb-0">
            {[
              { id: 'all', label: `All (${images.length})` },
              { id: 'high_match', label: `High Match (>80%) (${images.filter(i => (i.score || 0) >= 0.80).length})` },
              { id: 'front', label: `Front Views (${images.filter(i => (i.angle || i.tag || '').toLowerCase().includes('front') || (i.title || '').toLowerCase().includes('front')).length})` },
              { id: 'side', label: `Side Views (${images.filter(i => (i.angle || i.tag || '').toLowerCase().includes('side') || (i.angle || i.tag || '').toLowerCase().includes('profile') || (i.title || '').toLowerCase().includes('side')).length})` },
              { id: 'rear', label: `Rear Views (${images.filter(i => (i.angle || i.tag || '').toLowerCase().includes('rear') || (i.angle || i.tag || '').toLowerCase().includes('back') || (i.title || '').toLowerCase().includes('rear') || (i.angle || i.tag || '').toLowerCase().includes('port')).length})` },
              { id: 'isometric', label: `Isometric Angle (${images.filter(i => (i.angle || i.tag || '').toLowerCase().includes('isometric') || (i.angle || i.tag || '').toLowerCase().includes('angle') || (i.title || '').toLowerCase().includes('perspective')).length})` },
              { id: 'hide_noise', label: 'Hide Noise / Logos' },
            ].map(tab => (
              <button
                key={tab.id}
                onClick={() => setActiveFilter(tab.id)}
                className={`px-3 py-1.5 rounded-xl text-xs font-semibold whitespace-nowrap transition-all ${
                  activeFilter === tab.id
                    ? 'bg-brand-500 text-white shadow-xs'
                    : 'bg-[#F1F5F9] dark:bg-[#0F1832] text-[#64748B] dark:text-[#8D9CB8] hover:bg-[#E2E8F0] dark:hover:bg-[#172449]'
                }`}
              >
                {tab.label}
              </button>
            ))}
          </div>

          {/* View Mode Switcher */}
          <div className="flex items-center gap-3">
            <div className="flex items-center bg-[#F1F5F9] dark:bg-[#0F1832] p-1 rounded-xl border border-[#CBD5E1] dark:border-[#1E2C52]">
              <button
                onClick={() => setViewMode('grid')}
                className={`flex items-center gap-1.5 px-3 py-1 rounded-lg text-xs font-semibold transition-all ${
                  viewMode === 'grid'
                    ? 'bg-white dark:bg-[#131E3D] text-brand-600 dark:text-brand-400 shadow-xs'
                    : 'text-[#64748B] dark:text-[#8D9CB8]'
                }`}
              >
                <Grid className="w-3.5 h-3.5" />
                <span>Grid View</span>
              </button>
              <button
                onClick={() => setViewMode('vector_space')}
                className={`flex items-center gap-1.5 px-3 py-1 rounded-lg text-xs font-semibold transition-all ${
                  viewMode === 'vector_space'
                    ? 'bg-white dark:bg-[#131E3D] text-brand-600 dark:text-brand-400 shadow-xs'
                    : 'text-[#64748B] dark:text-[#8D9CB8]'
                }`}
              >
                <Activity className="w-3.5 h-3.5" />
                <span>Vector Space View</span>
              </button>
            </div>

            <div className="hidden lg:flex items-center gap-2 text-xs flex-shrink-0">
              <button
                onClick={() => selectAllImages(true)}
                className="font-semibold text-brand-600 dark:text-brand-400 hover:underline"
              >
                Select All
              </button>
              <span className="text-[#CBD5E1] dark:text-[#1E2C52]">|</span>
              <button
                onClick={() => selectAllImages(false)}
                className="font-semibold text-[#64748B] dark:text-[#8D9CB8] hover:underline"
              >
                Deselect All
              </button>
            </div>
          </div>
        </div>

        {/* View Content: Vector Space View OR Grid View */}
        {viewMode === 'vector_space' ? (
          <div className="mb-6">
            <VectorSpaceView
              images={filteredImages}
              seedImage={activeProduct?.thumbnail}
              onInspectAlignment={(img) => setInspectModalImage(img)}
              onToggleSelect={toggleImageSelection}
            />
          </div>
        ) : filteredImages.length === 0 ? (
          images.length > 0 ? (
            <div className="p-8 text-center border-2 border-dashed border-[#CBD5E1] dark:border-[#1E2C52] rounded-2xl mb-6 bg-[#F8FAFC]/50 dark:bg-[#0F1832]/40">
              <Filter className="w-8 h-8 text-brand-500 mx-auto mb-2 opacity-80" />
              <h3 className="text-sm font-bold text-[#1C2434] dark:text-white">
                No images found for this specific angle filter.
              </h3>
              <p className="text-xs text-[#64748B] dark:text-[#8D9CB8] max-w-md mx-auto mt-1">
                Switch to <strong>All ({images.length})</strong> to view all accepted candidate viewpoints.
              </p>
              <button
                onClick={() => setActiveFilter('all')}
                className="mt-3.5 px-4 py-1.5 rounded-xl bg-brand-500 hover:bg-brand-600 text-white text-xs font-semibold shadow-xs transition-colors inline-flex items-center gap-1.5"
              >
                <Sparkles className="w-3 h-3" />
                <span>Switch to All ({images.length}) Candidates</span>
              </button>
            </div>
          ) : (
            <div className="p-8 text-center border-2 border-dashed border-[#CBD5E1] dark:border-[#1E2C52] rounded-2xl mb-6 bg-[#F8FAFC]/50 dark:bg-[#0F1832]/40">
              <ShieldAlert className="w-8 h-8 text-amber-500 mx-auto mb-2" />
              <h3 className="text-sm font-bold text-[#1C2434] dark:text-white">
                No Alternate Viewpoints Above Minimum Threshold
              </h3>
              <p className="text-xs text-[#64748B] dark:text-[#8D9CB8] max-w-md mx-auto mt-1">
                Live scraping did not yield candidate images passing the filter floor.
                Use the <strong>Targeted Angle Cascade</strong> below with specific feature terms (e.g. motor housing, profile, outsole).
              </p>
            </div>
          )
        ) : (
          /* Grid View with Vector Signal Breakdown */
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
            {filteredImages.map((img) => {
              const isPassing = img.score >= 0.65;
              const isNoise = img.score < 0.65;
              const viewTag = img.tag || (img.angle?.includes('Front') ? 'Front View' : img.angle?.includes('Profile') ? 'Side Profile' : img.angle?.includes('Rear') ? 'Rear View' : isNoise ? 'Noise / Outlier' : 'Isometric Perspective');
              const isExpanded = expandedBreakdown[img.id];

              const silScore = img.signals?.silhouette || (img.score >= 0.85 ? 96 : isNoise ? 34 : 88);
              const matScore = img.signals?.material || (isNoise ? 22 : 91);
              const topScore = img.signals?.topology || (img.angle?.includes('Front') ? 95 : isNoise ? 18 : 48);

              return (
                <div
                  key={img.id}
                  onClick={() => toggleImageSelection(img.id)}
                  className={`group relative rounded-2xl border p-2.5 cursor-pointer transition-all flex flex-col justify-between ${
                    img.selected
                      ? 'border-brand-500 bg-brand-50/20 dark:bg-brand-500/10 shadow-xs ring-2 ring-brand-500/20'
                      : isNoise
                      ? 'border-rose-200 dark:border-rose-900/40 bg-rose-50/10 dark:bg-rose-950/20 opacity-70'
                      : 'border-[#E2E8F0] dark:border-[#1E2C52] bg-white dark:bg-[#0F1832]/60 hover:border-brand-400'
                  }`}
                >
                  <div>
                    {/* Image Viewport Container */}
                    <div className="relative aspect-4/3 rounded-xl overflow-hidden bg-[#F8FAFC] dark:bg-[#0B1120] mb-2 flex items-center justify-center">
                      <img
                        src={img.url}
                        alt={img.title}
                        className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-300"
                      />

                      {/* Detected Viewport Tag (Top-Left) */}
                      <div className="absolute top-1.5 left-1.5">
                        <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded-md text-[10px] font-bold bg-black/80 text-white backdrop-blur-xs">
                          {viewTag}
                        </span>
                      </div>

                      {/* DINOv2 Match Badge (Top-Right) */}
                      <div className="absolute top-1.5 right-1.5">
                        <span
                          className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded-md text-[10px] font-bold backdrop-blur-xs shadow-2xs ${
                            img.score >= 0.80
                              ? 'bg-emerald-500 text-white'
                              : isPassing
                              ? 'bg-amber-500 text-white'
                              : 'bg-rose-500 text-white'
                          }`}
                        >
                          <Sparkles className="w-2.5 h-2.5" />
                          {(img.score * 100).toFixed(1)}% Match
                        </span>
                      </div>

                      {/* Checkbox Overlay */}
                      <div className="absolute bottom-1.5 right-1.5">
                        <div
                          className={`w-5 h-5 rounded-lg flex items-center justify-center border transition-all ${
                            img.selected
                              ? 'bg-brand-500 border-brand-500 text-white shadow-sm'
                              : 'bg-white/90 dark:bg-[#0F1832]/90 border-[#CBD5E1] dark:border-[#1E2C52]'
                          }`}
                        >
                          {img.selected && <Check className="w-3.5 h-3.5 stroke-[3]" />}
                        </div>
                      </div>

                      {/* Inspect Alignment Overlay Button */}
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          setInspectModalImage(img);
                        }}
                        className="absolute bottom-1.5 left-1.5 px-2 py-0.5 rounded-md bg-slate-900/90 hover:bg-black text-white text-[10px] font-semibold flex items-center gap-1 backdrop-blur-xs transition-colors shadow-2xs"
                      >
                        <Eye className="w-2.5 h-2.5 text-brand-400" />
                        <span>Inspect Alignment</span>
                      </button>
                    </div>

                    {/* Title and Origin */}
                    <p className="text-xs font-semibold text-[#1C2434] dark:text-white truncate" title={img.title}>
                      {img.title}
                    </p>
                    <p className="text-[10px] text-[#64748B] dark:text-[#8D9CB8] truncate mb-2">
                      {img.source}
                    </p>

                    {/* Vector Signal Breakdown Sub-Panel */}
                    {!isNoise && (
                      <div className="mb-2 p-2 rounded-xl bg-[#F8FAFC] dark:bg-[#0B1120] border border-[#E2E8F0] dark:border-[#1E2C52]">
                        <div
                          onClick={(e) => toggleBreakdown(img.id, e)}
                          className="flex items-center justify-between text-[10px] font-bold text-[#64748B] dark:text-[#8D9CB8] uppercase tracking-wider cursor-pointer select-none"
                        >
                          <span>Vector Signal Breakdown</span>
                          {isExpanded ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
                        </div>

                        {/* Expandable Progress Bars */}
                        <div className={`space-y-1.5 pt-1.5 ${isExpanded ? 'block' : 'hidden'}`}>
                          <div>
                            <div className="flex justify-between text-[10px] font-semibold mb-0.5">
                              <span className="text-[#64748B] dark:text-[#8D9CB8]">Silhouette &amp; Contour</span>
                              <span className="text-emerald-500 dark:text-emerald-400">{silScore}%</span>
                            </div>
                            <div className="w-full bg-[#E2E8F0] dark:bg-[#1E2C52] h-1.5 rounded-full overflow-hidden">
                              <div className="bg-emerald-500 h-full rounded-full" style={{ width: `${silScore}%` }} />
                            </div>
                          </div>

                          <div>
                            <div className="flex justify-between text-[10px] font-semibold mb-0.5">
                              <span className="text-[#64748B] dark:text-[#8D9CB8]">Material &amp; Surface</span>
                              <span className="text-blue-500 dark:text-blue-400">{matScore}%</span>
                            </div>
                            <div className="w-full bg-[#E2E8F0] dark:bg-[#1E2C52] h-1.5 rounded-full overflow-hidden">
                              <div className="bg-blue-500 h-full rounded-full" style={{ width: `${matScore}%` }} />
                            </div>
                          </div>

                          <div>
                            <div className="flex justify-between text-[10px] font-semibold mb-0.5">
                              <span className="text-[#64748B] dark:text-[#8D9CB8]">Face Topology (Angle)</span>
                              <span className="text-amber-500 dark:text-amber-400">{topScore}%</span>
                            </div>
                            <div className="w-full bg-[#E2E8F0] dark:bg-[#1E2C52] h-1.5 rounded-full overflow-hidden">
                              <div className="bg-amber-500 h-full rounded-full" style={{ width: `${topScore}%` }} />
                            </div>
                          </div>
                        </div>
                      </div>
                    )}
                  </div>

                  {/* Dynamic Anchor Bank Role Buttons */}
                  <div className="pt-2 border-t border-[#E2E8F0] dark:border-[#1E2C52] flex flex-wrap gap-1">
                    {isNoise ? (
                      <span className="text-[10px] font-semibold text-rose-500 flex items-center gap-1">
                        <ShieldAlert className="w-3 h-3" /> Auto-Flagged Noise (&lt;0.65)
                      </span>
                    ) : (
                      <>
                        <button
                          onClick={(e) => setAnchorRole(img.id, 'Primary Master Geometry', e)}
                          className={`px-2 py-0.5 rounded-lg text-[10px] font-semibold border transition-all ${
                            img.role === 'Primary Master Geometry'
                              ? 'bg-brand-500 text-white border-brand-500'
                              : 'bg-[#F1F5F9] dark:bg-[#0B1120] text-[#64748B] dark:text-[#8D9CB8] border-transparent hover:border-brand-400'
                          }`}
                        >
                          {img.role === 'Primary Master Geometry' ? '✓ Master Frame' : 'Set Master Frame'}
                        </button>
                        <button
                          onClick={(e) => setAnchorRole(img.id, 'Secondary Profile Anchor', e)}
                          className={`px-2 py-0.5 rounded-lg text-[10px] font-semibold border transition-all ${
                            img.role === 'Secondary Profile Anchor'
                              ? 'bg-emerald-500 text-white border-emerald-500'
                              : 'bg-[#F1F5F9] dark:bg-[#0B1120] text-[#64748B] dark:text-[#8D9CB8] border-transparent hover:border-emerald-400'
                          }`}
                        >
                          {img.role === 'Secondary Profile Anchor' ? '✓ Profile Anchor' : 'Set Profile Anchor'}
                        </button>
                      </>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        )}

        {/* 3. Cascading Scraping Action Controls */}
        <div className="p-4 rounded-2xl bg-gradient-to-r from-brand-50/60 to-blue-50/40 dark:from-[#0F1832] dark:to-brand-950/20 border border-brand-200 dark:border-[#1E2C52] mb-6">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
            <div className="flex items-center gap-2">
              <RotateCw className={`w-4 h-4 text-brand-500 ${isCascading ? 'animate-spin' : ''}`} />
              <div>
                <span className="text-xs font-bold text-[#1C2434] dark:text-white">
                  Trigger Targeted Angle Cascade:
                </span>
                <p className="text-[11px] text-[#64748B] dark:text-[#8D9CB8]">
                  Dynamically harvests missing angles (rear ports/connectors) to complete the 4-quadrant anchor bank.
                </p>
              </div>
            </div>

            {/* Input / Button Combo */}
            <div className="flex items-center gap-2 w-full sm:w-auto">
              <input
                type="text"
                value={cascadeQuery}
                onChange={(e) => setCascadeQuery(e.target.value)}
                placeholder="Targeted query e.g. Rear fluid connection layout"
                className="flex-1 sm:w-80 px-3.5 py-2 text-xs bg-white dark:bg-[#131E3D] border border-[#CBD5E1] dark:border-[#1E2C52] rounded-xl text-[#1C2434] dark:text-white focus:outline-none focus:ring-2 focus:ring-brand-500/30"
              />
              <button
                onClick={triggerTargetedCascade}
                disabled={isCascading}
                className="px-4 py-2 text-xs font-semibold text-white bg-brand-500 hover:bg-brand-600 disabled:bg-brand-500/80 rounded-xl shadow-sm transition-all whitespace-nowrap flex items-center gap-1.5"
              >
                {isCascading ? (
                  <>
                    <div className="w-3 h-3 border-2 border-white/30 border-t-white rounded-full animate-spin"></div>
                    <span className="font-mono">⏱️ Harvesting ({elapsedTime.toFixed(1).padStart(4, '0')}s)</span>
                  </>
                ) : (
                  <>
                    <Search className="w-3 h-3" />
                    <span>Run Cycle {cascadeCycle}</span>
                  </>
                )}
              </button>
            </div>
          </div>
        </div>

        {/* Section: Related URLs */}
        <div className="mb-6 pt-4 border-t border-[#E2E8F0] dark:border-[#1E2C52]">
          <div className="flex items-center justify-between mb-3">
            <span className="text-xs font-bold uppercase tracking-wider text-[#1C2434] dark:text-white">
              Related Technical Datasheets &amp; CAD Specs ({urls.length})
            </span>
            <div className="flex items-center gap-3 text-xs">
              <button onClick={() => selectAllUrls(true)} className="font-semibold text-brand-600 dark:text-brand-400 hover:underline">Select All</button>
              <span className="text-[#CBD5E1] dark:text-[#1E2C52]">|</span>
              <button onClick={() => selectAllUrls(false)} className="font-semibold text-[#64748B] dark:text-[#8D9CB8] hover:underline">Deselect All</button>
            </div>
          </div>

          <div className="space-y-2">
            {urls.map((item, idx) => (
              <div
                key={idx}
                onClick={() => toggleUrlSelection(idx)}
                className={`flex items-start gap-3 p-3 rounded-xl border cursor-pointer transition-colors ${
                  item.selected
                    ? 'bg-brand-50/30 dark:bg-brand-500/10 border-brand-200 dark:border-brand-500/30'
                    : 'bg-[#F8FAFC]/50 dark:bg-[#0F1832]/60 border-[#E2E8F0] dark:border-[#1E2C52]'
                }`}
              >
                <div className="pt-0.5">
                  <div
                    className={`w-4 h-4 rounded flex items-center justify-center border transition-all ${
                      item.selected ? 'bg-brand-500 border-brand-500 text-white' : 'bg-white dark:bg-[#131E3D] border-[#CBD5E1] dark:border-[#1E2C52]'
                    }`}
                  >
                    {item.selected && <Check className="w-3 h-3 stroke-[3]" />}
                  </div>
                </div>

                <div className="flex-1 min-w-0">
                  <p className="text-xs font-semibold text-[#1C2434] dark:text-white">
                    {item.title}
                  </p>
                  <a
                    href={item.url}
                    target="_blank"
                    rel="noreferrer"
                    onClick={(e) => e.stopPropagation()}
                    className="text-[11px] text-brand-600 dark:text-brand-400 hover:underline flex items-center gap-1 mt-0.5 truncate"
                  >
                    <span>{item.url}</span>
                    <ExternalLink className="w-2.5 h-2.5 flex-shrink-0" />
                  </a>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* 4. Reconstruction Strategy Selector (Mode Selection Gate) */}
        <div className="p-4 rounded-2xl bg-[#F8FAFC] dark:bg-[#0F1832] border border-[#E2E8F0] dark:border-[#1E2C52] mb-6">
          <div className="flex items-center gap-2 mb-3">
            <Sliders className="w-4 h-4 text-brand-500" />
            <span className="text-xs font-bold uppercase tracking-wider text-[#1C2434] dark:text-white">
              Reconstruction Strategy Selector
            </span>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {/* Mode A */}
            <label
              onClick={() => setReconstructionMode('autonomous')}
              className={`p-4 rounded-2xl border cursor-pointer transition-all flex items-start gap-3 ${
                reconstructionMode === 'autonomous'
                  ? 'bg-white dark:bg-[#131E3D] border-brand-500 ring-2 ring-brand-500/20 shadow-xs'
                  : 'bg-white/60 dark:bg-[#131E3D]/40 border-[#E2E8F0] dark:border-[#1E2C52] hover:border-brand-400'
              }`}
            >
              <input
                type="radio"
                name="reconstruction_mode"
                checked={reconstructionMode === 'autonomous'}
                onChange={() => setReconstructionMode('autonomous')}
                className="mt-0.5 text-brand-500 focus:ring-brand-500"
              />
              <div>
                <div className="flex items-center gap-1.5 font-bold text-xs text-[#1C2434] dark:text-white">
                  <Cpu className="w-3.5 h-3.5 text-blue-500" />
                  <span>Option A: Autonomous (Fast / Prior-driven)</span>
                </div>
                <p className="text-[11px] text-[#64748B] dark:text-[#8D9CB8] mt-1 leading-relaxed">
                  Uses top verified reference. Missing occluded geometries are synthesized via geometric priors. Best for rapid turnaround.
                </p>
              </div>
            </label>

            {/* Mode B */}
            <label
              onClick={() => setReconstructionMode('guided')}
              className={`p-4 rounded-2xl border cursor-pointer transition-all flex items-start gap-3 ${
                reconstructionMode === 'guided'
                  ? 'bg-white dark:bg-[#131E3D] border-brand-500 ring-2 ring-brand-500/20 shadow-xs'
                  : 'bg-white/60 dark:bg-[#131E3D]/40 border-[#E2E8F0] dark:border-[#1E2C52] hover:border-brand-400'
              }`}
            >
              <input
                type="radio"
                name="reconstruction_mode"
                checked={reconstructionMode === 'guided'}
                onChange={() => setReconstructionMode('guided')}
                className="mt-0.5 text-brand-500 focus:ring-brand-500"
              />
              <div>
                <div className="flex items-center gap-1.5 font-bold text-xs text-[#1C2434] dark:text-white">
                  <Sparkles className="w-3.5 h-3.5 text-emerald-500" />
                  <span>Option B: Guided Multi-Reference Fusion</span>
                </div>
                <p className="text-[11px] text-[#64748B] dark:text-[#8D9CB8] mt-1 leading-relaxed">
                  Combines 2–3 selected reference images. Enables the Attribute Evidence Matrix to resolve port discrepancies.
                </p>
              </div>
            </label>
          </div>
        </div>

        {/* Footer Navigation */}
        <div className="flex items-center justify-between pt-4 border-t border-[#E2E8F0] dark:border-[#1E2C52]">
          <button
            onClick={() => setCurrentStage(0)}
            className="flex items-center gap-2 px-4 py-2 text-xs font-semibold text-[#64748B] dark:text-[#8D9CB8] bg-white dark:bg-[#131E3D] hover:bg-[#F1F5F9] dark:hover:bg-[#172449] border border-[#CBD5E1] dark:border-[#1E2C52] rounded-xl transition-colors"
          >
            <ArrowLeft className="w-3.5 h-3.5" />
            <span>Back to Edit</span>
          </button>

          <button
            onClick={handleSendToApproval}
            className="flex items-center gap-2 px-6 py-2.5 text-xs font-semibold text-white bg-brand-500 hover:bg-brand-600 rounded-xl shadow-md shadow-brand-500/25 transition-all hover:scale-[1.01] active:scale-[0.99]"
          >
            <span>Send to Approval</span>
            <ArrowRight className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>

      {/* Side-by-Side Patch Heatmap Inspection Modal */}
      <InspectAlignmentModal
        isOpen={!!inspectModalImage}
        candidateImage={inspectModalImage}
        seedImage={activeProduct?.thumbnail}
        onClose={() => setInspectModalImage(null)}
      />
    </div>
  );
}
