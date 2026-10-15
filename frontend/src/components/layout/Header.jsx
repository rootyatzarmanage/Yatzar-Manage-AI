import React from 'react';
import { useProducts } from '../../context/ProductContext';
import { 
  Search, 
  Moon, 
  Sun, 
  Bell, 
  Box, 
  Layers, 
  CheckCircle2, 
  SlidersHorizontal,
  ChevronDown,
  Sparkles,
  User
} from 'lucide-react';

export default function Header() {
  const { darkMode, setDarkMode, searchQuery, setSearchQuery, activeProduct } = useProducts();

  return (
    <header className="sticky top-0 z-40 flex items-center justify-between h-16 px-6 bg-white border-b border-[#E2E8F0] dark:bg-[#0E172E] dark:border-[#1E2C52] shadow-sm transition-colors">
      {/* Brand Identity */}
      <div className="flex items-center gap-3">
        <div className="w-10 h-10 rounded-xl bg-brand-500 flex items-center justify-center text-white shadow-md shadow-brand-500/25">
          <Box className="w-6 h-6 stroke-[2.2]" />
        </div>
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-lg font-bold tracking-tight text-[#1C2434] dark:text-white flex items-center gap-1.5">
              Product Asset Factory
            </h1>
            <span className="text-[10px] uppercase font-bold tracking-wider px-1.5 py-0.5 rounded bg-brand-50 text-brand-600 dark:bg-brand-500/20 dark:text-brand-400 border border-brand-200 dark:border-brand-500/30">
              AI 2D→3D
            </span>
          </div>
          <p className="text-xs text-[#64748B] dark:text-[#8D9CB8]">
            Uncertainty-Aware Procedural CAD Pipeline
          </p>
        </div>
      </div>

      {/* Global Search Bar */}
      <div className="hidden md:flex items-center flex-1 max-w-md mx-8">
        <div className="relative w-full">
          <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-[#94A3B8] dark:text-[#62718E]" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search or type command..."
            className="w-full pl-10 pr-12 py-2 text-xs bg-[#F1F5F9] dark:bg-[#0F1832] border border-[#E2E8F0] dark:border-[#1E2C52] rounded-xl text-[#1C2434] dark:text-white placeholder-[#94A3B8] dark:placeholder-[#62718E] focus:outline-none focus:ring-2 focus:ring-brand-500/30 focus:border-brand-500 transition-all"
          />
          <kbd className="absolute right-3 top-1/2 -translate-y-1/2 text-[10px] font-semibold text-[#64748B] dark:text-[#8D9CB8] bg-white dark:bg-[#131E3D] border border-[#CBD5E1] dark:border-[#1E2C52] px-1.5 py-0.5 rounded shadow-2xs">
            ⌘K
          </kbd>
        </div>
      </div>

      {/* Right Controls */}
      <div className="flex items-center gap-3.5">
        {/* Active Jobs Widget */}
        <ActiveJobsWidget />

        {/* Dark/Light Mode Toggle */}
        <button
          onClick={() => setDarkMode(!darkMode)}
          aria-label="Toggle Dark Mode"
          className="p-2 rounded-xl text-[#64748B] dark:text-[#8D9CB8] hover:bg-[#F1F5F9] dark:hover:bg-[#131E3D] border border-[#E2E8F0] dark:border-[#1E2C52] transition-colors"
        >
          {darkMode ? <Sun className="w-4 h-4 text-amber-400" /> : <Moon className="w-4 h-4 text-[#64748B]" />}
        </button>

        {/* Notifications */}
        <button 
          aria-label="Notifications"
          className="p-2 relative rounded-xl text-[#64748B] dark:text-[#8D9CB8] hover:bg-[#F1F5F9] dark:hover:bg-[#131E3D] border border-[#E2E8F0] dark:border-[#1E2C52] transition-colors"
        >
          <Bell className="w-4 h-4" />
          <span className="absolute top-1.5 right-1.5 w-2 h-2 bg-brand-500 rounded-full"></span>
        </button>

        <div className="h-6 w-px bg-[#E2E8F0] dark:bg-[#1E2C52]"></div>

        {/* User Profile matching default user figure */}
        <div className="flex items-center gap-2.5 pl-1 cursor-pointer group">
          <div className="w-9 h-9 rounded-full bg-[#F1F5F9] dark:bg-[#0F1832] border border-[#CBD5E1] dark:border-[#1E2C52] group-hover:border-brand-500 flex items-center justify-center text-[#64748B] dark:text-[#8D9CB8] group-hover:text-brand-500 transition-colors">
            <User className="w-4 h-4" />
          </div>
          <div className="hidden xl:block text-left">
            <p className="text-xs font-semibold text-[#1C2434] dark:text-white leading-tight">
              Sanjay
            </p>
            <p className="text-[10px] text-[#64748B] dark:text-[#8D9CB8]">
              Lead Architect
            </p>
          </div>
          <ChevronDown className="w-3.5 h-3.5 text-[#94A3B8] dark:text-[#62718E] hidden xl:block" />
        </div>
      </div>
    </header>
  );
}

function ActiveJobsWidget() {
  const { researchJobs, reconstructionJobs, products, selectProduct } = useProducts();
  const [isOpen, setIsOpen] = React.useState(false);

  const activeResearch = Object.values(researchJobs || {}).filter(
    j => j && (j.status === 'RUNNING' || j.status === 'QUEUED')
  );
  const activeReconstruct = Object.values(reconstructionJobs || {}).filter(
    j => j && (j.status === 'RECONSTRUCTING' || j.status === 'QUEUED')
  );

  const totalActive = activeResearch.length + activeReconstruct.length;

  if (totalActive === 0) return null;

  return (
    <div className="relative">
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="flex items-center gap-2 px-3 py-1.5 text-xs font-semibold rounded-xl bg-brand-50 dark:bg-brand-500/20 text-brand-600 dark:text-brand-300 border border-brand-200 dark:border-brand-500/30 hover:bg-brand-100 transition-colors shadow-xs"
      >
        <div className="w-2 h-2 rounded-full bg-brand-500 animate-ping"></div>
        <span>Active Jobs ({totalActive})</span>
      </button>

      {isOpen && (
        <div className="absolute right-0 mt-2 w-72 bg-white dark:bg-[#0E172E] border border-[#CBD5E1] dark:border-[#1E2C52] rounded-2xl shadow-xl z-50 p-3 space-y-2">
          <div className="flex items-center justify-between pb-2 border-b border-[#E2E8F0] dark:border-[#1E2C52]">
            <span className="text-xs font-bold uppercase tracking-wider text-[#64748B] dark:text-[#8D9CB8]">
              Background Jobs
            </span>
            <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-brand-500/10 text-brand-500">
              {totalActive} Running
            </span>
          </div>

          <div className="space-y-1.5 max-h-60 overflow-y-auto">
            {activeResearch.map(job => {
              const prod = products.find(p => p.id === job.product_id);
              const pName = prod?.name || job.product_id;
              const pct = Math.round((job.progress || 0) * 100);

              return (
                <div
                  key={job.product_id}
                  onClick={() => {
                    selectProduct(job.product_id);
                    setIsOpen(false);
                  }}
                  className="p-2 rounded-xl bg-[#F8FAFC] dark:bg-[#131E3D] hover:bg-brand-50 dark:hover:bg-brand-500/10 cursor-pointer border border-[#E2E8F0] dark:border-[#1E2C52] transition-colors"
                >
                  <div className="flex items-center justify-between text-xs font-semibold text-[#1C2434] dark:text-white">
                    <span className="truncate max-w-[140px]">{pName}</span>
                    <span className="text-brand-600 dark:text-brand-400 font-bold">{pct}%</span>
                  </div>
                  <div className="flex items-center justify-between mt-1 text-[10px] text-[#64748B] dark:text-[#8D9CB8]">
                    <span>Research • {job.status}</span>
                    <span>{job.current_phase || 'Searching...'}</span>
                  </div>
                </div>
              );
            })}

            {activeReconstruct.map(job => {
              const prod = products.find(p => p.id === job.product_id);
              const pName = prod?.name || job.product_id;

              return (
                <div
                  key={job.product_id}
                  onClick={() => {
                    selectProduct(job.product_id);
                    setIsOpen(false);
                  }}
                  className="p-2 rounded-xl bg-[#F8FAFC] dark:bg-[#131E3D] hover:bg-brand-50 dark:hover:bg-brand-500/10 cursor-pointer border border-[#E2E8F0] dark:border-[#1E2C52] transition-colors"
                >
                  <div className="flex items-center justify-between text-xs font-semibold text-[#1C2434] dark:text-white">
                    <span className="truncate max-w-[140px]">{pName}</span>
                    <span className="text-amber-500 font-bold">
                      {job.status === 'RECONSTRUCTING' ? 'GPU ACTIVE' : `QUEUED (#${job.queue_position || 1})`}
                    </span>
                  </div>
                  <div className="flex items-center justify-between mt-1 text-[10px] text-[#64748B] dark:text-[#8D9CB8]">
                    <span>Pixal3D 3D Engine</span>
                    <span>{job.status}</span>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
