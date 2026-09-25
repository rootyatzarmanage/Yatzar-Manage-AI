import React from 'react';
import { useProducts } from '../../context/ProductContext';
import { 
  FileText, 
  Search, 
  CheckCircle, 
  Box, 
  Eye, 
  ChevronRight,
  Sparkles
} from 'lucide-react';

const STAGES = [
  { id: 0, label: 'Input', icon: FileText, desc: 'Metadata & Seed Image' },
  { id: 1, label: 'Scrape', icon: Search, desc: 'Dynamic Angle Harvest' },
  { id: 2, label: 'Image Approval', icon: CheckCircle, desc: 'DINOv2 Vector Anchor' },
  { id: 3, label: '3D Generate', icon: Box, desc: 'Procedural CSG Engine' },
  { id: 4, label: '3D Approval', icon: Eye, desc: 'Two-Tier QA Audit' },
];

export default function StageStepper() {
  const { currentStage, setCurrentStage, activeProduct } = useProducts();

  return (
    <div className="bg-white dark:bg-[#0E172E] border-b border-[#E2E8F0] dark:border-[#1E2C52] px-6 py-3 transition-colors">
      <div className="flex items-center justify-between max-w-5xl mx-auto overflow-x-auto">
        {STAGES.map((stage, idx) => {
          const Icon = stage.icon;
          const isActive = currentStage === stage.id;
          const isCompleted = currentStage > stage.id;

          return (
            <React.Fragment key={stage.id}>
              <button
                onClick={() => setCurrentStage(stage.id)}
                className={`flex items-center gap-2.5 px-3.5 py-2 rounded-xl text-xs font-semibold transition-all group whitespace-nowrap ${
                  isActive
                    ? 'bg-brand-50 dark:bg-brand-500/15 text-brand-600 dark:text-brand-400 border border-brand-200 dark:border-brand-500/30 shadow-xs'
                    : isCompleted
                    ? 'text-emerald-600 dark:text-emerald-400 hover:bg-[#F8FAFC] dark:hover:bg-[#131E3D]'
                    : 'text-[#64748B] dark:text-[#8D9CB8] hover:bg-[#F8FAFC] dark:hover:bg-[#131E3D] opacity-70'
                }`}
              >
                <div
                  className={`w-6 h-6 rounded-full flex items-center justify-center transition-colors ${
                    isActive
                      ? 'bg-brand-500 text-white'
                      : isCompleted
                      ? 'bg-emerald-500 text-white'
                      : 'bg-[#F1F5F9] dark:bg-[#0F1832] text-[#64748B] dark:text-[#8D9CB8]'
                  }`}
                >
                  {isCompleted ? (
                    <CheckCircle className="w-3.5 h-3.5 stroke-[2.5]" />
                  ) : (
                    <Icon className="w-3.5 h-3.5" />
                  )}
                </div>

                <div className="text-left">
                  <div className="font-semibold flex items-center gap-1">
                    {stage.label}
                    {isActive && (
                      <span className="w-1.5 h-1.5 rounded-full bg-brand-500 animate-ping"></span>
                    )}
                  </div>
                </div>
              </button>

              {idx < STAGES.length - 1 && (
                <ChevronRight className="w-4 h-4 text-[#CBD5E1] dark:text-[#1E2C52] flex-shrink-0 mx-1" />
              )}
            </React.Fragment>
          );
        })}
      </div>
    </div>
  );
}
