import React from 'react';
import { useProducts } from '../../context/ProductContext';
import { Plus, CheckCircle, XCircle, Clock, Image as ImageIcon, Sparkles, Box } from 'lucide-react';

export default function Sidebar() {
  const { 
    products, 
    activeProductId, 
    selectProduct, 
    createNewProduct,
    searchQuery 
  } = useProducts();

  const filteredProducts = products.filter(p => 
    p.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
    p.category?.toLowerCase().includes(searchQuery.toLowerCase()) ||
    p.modelNumber?.toLowerCase().includes(searchQuery.toLowerCase())
  );

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
                    <h2 className="text-xs font-semibold text-[#1C2434] dark:text-white truncate" title={product.name}>
                      {product.name}
                    </h2>
                  </div>

                  {/* Status Pill */}
                  <div className="flex items-center gap-2 mb-1.5">
                    {product.status === 'APPROVED' && (
                      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold bg-emerald-50 dark:bg-emerald-950/50 text-emerald-600 dark:text-emerald-400 border border-emerald-200 dark:border-emerald-800">
                        <CheckCircle className="w-2.5 h-2.5" />
                        APPROVED
                      </span>
                    )}
                    {product.status === 'DROPPED' && (
                      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold bg-rose-50 dark:bg-rose-950/50 text-rose-600 dark:text-rose-400 border border-rose-200 dark:border-rose-800">
                        <XCircle className="w-2.5 h-2.5" />
                        DROPPED
                      </span>
                    )}
                    {product.status === 'IN_PROGRESS' && (
                      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold bg-blue-50 dark:bg-blue-950/50 text-blue-600 dark:text-blue-400 border border-blue-200 dark:border-blue-800">
                        <Clock className="w-2.5 h-2.5 animate-spin" />
                        IN PROGRESS
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
