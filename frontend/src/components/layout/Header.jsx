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
        {/* API Connected Pill */}
        <div className="hidden sm:flex items-center gap-2 px-3 py-1 rounded-full bg-emerald-50 dark:bg-emerald-950/40 border border-emerald-200 dark:border-emerald-800/60 text-emerald-700 dark:text-emerald-400 text-xs font-semibold">
          <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse"></span>
          <span>API Connected</span>
        </div>

        {/* DINOv2 Engine Pill */}
        <div className="hidden lg:flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-blue-50 dark:bg-blue-950/40 border border-blue-200 dark:border-blue-800/60 text-blue-700 dark:text-blue-300 text-xs font-medium">
          <Sparkles className="w-3.5 h-3.5 text-blue-500" />
          <span>DINOv2 ViT-B14</span>
        </div>

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
