import React, { useState, useEffect } from 'react';
import { useProducts } from '../../context/ProductContext';
import { Plus, CheckCircle, XCircle, Clock, Image as ImageIcon, Sparkles, Box, Trash2 } from 'lucide-react';

export default function Sidebar() {
  const { 
    products, 
    activeProductId, 
    selectProduct, 
    createNewProduct,
    deleteProduct,
    searchQuery,
    researchJobs = {},
    reconstructionJobs = {}
  } = useProducts();

  const [confirmDeleteId, setConfirmDeleteId] = useState(null);

  useEffect(() => {
    if (!confirmDeleteId) return;
    const timer = setTimeout(() => {
      setConfirmDeleteId(null);
    }, 4000);
    return () => clearTimeout(timer);
  }, [confirmDeleteId]);

  const filteredProducts = products.filter(p => {
    const q = searchQuery.toLowerCase();
    const nameMatch = (p.name || 'Untitled Product').toLowerCase().includes(q);
    const catMatch = (p.category || '').toLowerCase().includes(q);
    const modelMatch = (p.modelNumber || '').toLowerCase().includes(q);
    const brandMatch = (p.brand || '').toLowerCase().includes(q);
    return nameMatch || catMatch || modelMatch || brandMatch;
  });

  return (
    <aside className="w-80 flex-shrink-0 bg-white border-r border-[#E2E8F0] dark:bg-[#0E172E] dark:border-[#1E2C52] flex flex-col h-[calc(100vh-4rem)] transition-colors">
      {/* Top Action Bar */}
      <div className="p-4 border-b border-[#E2E8F0] dark:border-[#1E2C52] flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="text-xs font-bold uppercase tracking-wider text-[#64748B] dark:text-[#8D9CB8]">
            PRODUCTS
          </span>
          <span className="px-2 py-0.5 text-xs font-bold rounded-full bg-[#F1F5F9] dark:bg-[#131E3D] text-[#1C2434] dark:text-white border border-[#E2E8F0] dark:border-[#1E2C52]">
            {products.length}
          </span>
        </div>

        <button
          onClick={createNewProduct}
          className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold text-white bg-brand-500 hover:bg-brand-600 rounded-xl shadow-sm shadow-brand-500/30 transition-all hover:scale-[1.02] active:scale-[0.98]"
        >
          <Plus className="w-3.5 h-3.5 stroke-[2.5]" />
          <span>New</span>
        </button>
      </div>

      {/* Product Queue List */}
      <div className="flex-1 overflow-y-auto p-3 space-y-2">
        {filteredProducts.map((product) => {
          const isActive = product.id === activeProductId;

          return (
            <div
              key={product.id}
              onClick={() => selectProduct(product.id)}
              className={`group relative p-3 rounded-2xl cursor-pointer transition-all border ${
                isActive
                  ? 'bg-brand-50/60 dark:bg-brand-500/15 border-brand-500/50 shadow-xs'
                  : 'bg-white dark:bg-[#131E3D]/60 hover:bg-[#F8FAFC] dark:hover:bg-[#131E3D] border-[#E2E8F0] dark:border-[#1E2C52]'
              }`}
            >
              <div className="flex items-start gap-3">
                {/* Product Thumbnail */}
                <div className="w-12 h-12 rounded-xl bg-[#F1F5F9] dark:bg-[#0F1832] overflow-hidden flex-shrink-0 border border-[#CBD5E1]/60 dark:border-[#1E2C52] flex items-center justify-center">
                  {product.thumbnail ? (
                    <img
                      src={product.thumbnail}
                      alt={product.name}
                      className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-300"
                    />
                  ) : (
                    <Box className="w-6 h-6 text-[#94A3B8]" />
                  )}
                </div>

                {/* Info & Metrics */}
                <div className="flex-1 min-w-0">
                  <div className="flex items-center justify-between gap-1 mb-1">
                    <h2 className="text-xs font-semibold text-[#1C2434] dark:text-white truncate" title={product.name || 'Untitled Product'}>
                      {product.name || 'Untitled Product'}
                    </h2>
                    <button
                      type="button"
                      title={confirmDeleteId === product.id ? "Click again to permanently delete" : "Delete product and assets"}
                      onClick={(e) => {
                        e.stopPropagation();
                        if (confirmDeleteId === product.id) {
                          deleteProduct(product.id);
                          setConfirmDeleteId(null);
                        } else {
                          setConfirmDeleteId(product.id);
                        }
                      }}
                      className={`flex-shrink-0 p-1 rounded-lg transition-all ${
                        confirmDeleteId === product.id
                          ? 'bg-rose-500 text-white shadow-xs animate-pulse ring-2 ring-rose-400 opacity-100'
                          : 'opacity-0 group-hover:opacity-100 text-[#94A3B8] hover:text-rose-600 hover:bg-rose-50 dark:hover:bg-rose-950/40'
                      }`}
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  </div>

                  {confirmDeleteId === product.id && (
                    <div className="mb-1.5 px-2 py-0.5 rounded text-[10px] font-semibold bg-rose-100 dark:bg-rose-950/70 text-rose-700 dark:text-rose-300 border border-rose-300 dark:border-rose-800 flex items-center justify-between">
                      <span>Click trash to confirm</span>
                      <span 
                        onClick={(e) => { e.stopPropagation(); setConfirmDeleteId(null); }}
                        className="underline cursor-pointer hover:text-rose-900 dark:hover:text-rose-100"
                      >
                        Cancel
                      </span>
                    </div>
                  )}

                  {/* Status Pill */}
                  <div className="flex items-center gap-2 mb-1.5 flex-wrap">
                    {/* Active Research Job Status */}
                    {researchJobs[product.id] && (researchJobs[product.id].status === 'RUNNING' || researchJobs[product.id].status === 'QUEUED') ? (
                      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold bg-brand-50 dark:bg-brand-950/50 text-brand-600 dark:text-brand-400 border border-brand-200 dark:border-brand-800">
                        <Clock className="w-2.5 h-2.5 animate-spin" />
                        {researchJobs[product.id].status === 'RUNNING'
                          ? `RESEARCH ${Math.round((researchJobs[product.id].progress || 0) * 100)}%`
                          : 'RESEARCH QUEUED'}
                      </span>
                    ) : reconstructionJobs[product.id] && (reconstructionJobs[product.id].status === 'RECONSTRUCTING' || reconstructionJobs[product.id].status === 'QUEUED') ? (
                      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold bg-amber-50 dark:bg-amber-950/50 text-amber-600 dark:text-amber-400 border border-amber-200 dark:border-amber-800">
                        <Sparkles className="w-2.5 h-2.5 animate-spin" />
                        {reconstructionJobs[product.id].status === 'RECONSTRUCTING'
                          ? '3D RECONSTRUCTING'
                          : `3D QUEUED (#${reconstructionJobs[product.id].queue_position || 1})`}
                      </span>
                    ) : product.modelUrl ? (
                      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold bg-emerald-50 dark:bg-emerald-950/50 text-emerald-600 dark:text-emerald-400 border border-emerald-200 dark:border-emerald-800">
                        <CheckCircle className="w-2.5 h-2.5" />
                        3D READY
                      </span>
                    ) : product.status === 'APPROVED' ? (
                      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold bg-emerald-50 dark:bg-emerald-950/50 text-emerald-600 dark:text-emerald-400 border border-emerald-200 dark:border-emerald-800">
                        <CheckCircle className="w-2.5 h-2.5" />
                        APPROVED
                      </span>
                    ) : product.status === 'DROPPED' ? (
                      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold bg-rose-50 dark:bg-rose-950/50 text-rose-600 dark:text-rose-400 border border-rose-200 dark:border-rose-800">
                        <XCircle className="w-2.5 h-2.5" />
                        DROPPED
                      </span>
                    ) : (
                      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold bg-[#F1F5F9] dark:bg-[#131E3D] text-[#64748B] dark:text-[#8D9CB8] border border-[#CBD5E1] dark:border-[#1E2C52]">
                        <Clock className="w-2.5 h-2.5" />
                        {product.status || 'DRAFT'}
                      </span>
                    )}
                  </div>

                  {/* Telemetry row */}
                  <div className="flex items-center gap-3 text-[11px] text-[#64748B] dark:text-[#8D9CB8]">
                    <span className="flex items-center gap-1">
                      <ImageIcon className="w-3 h-3 text-[#94A3B8] dark:text-[#62718E]" />
                      @{product.imagesCount || 0}
                    </span>
                    <span className="flex items-center gap-1">
                      <Clock className="w-3 h-3 text-[#94A3B8] dark:text-[#62718E]" />
                      {product.executionTime || '0s'}
                    </span>
                    {product.confidenceScore > 0 && (
                      <span className="flex items-center gap-1 text-brand-600 dark:text-brand-400 font-semibold">
                        <Sparkles className="w-3 h-3" />
                        {Math.round(product.confidenceScore * 100)}%
                      </span>
                    )}
                  </div>
                </div>
              </div>

              {/* Active selection bar indicator */}
              {isActive && (
                <div className="absolute left-0 top-1/2 -translate-y-1/2 w-1 h-8 bg-brand-500 rounded-r-md"></div>
              )}
            </div>
          );
        })}
      </div>
    </aside>
  );
}
