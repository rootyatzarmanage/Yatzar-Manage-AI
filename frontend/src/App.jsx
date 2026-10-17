import React from 'react';
import { ProductProvider, useProducts } from './context/ProductContext';
import Header from './components/layout/Header';
import Sidebar from './components/layout/Sidebar';
import StageStepper from './components/layout/StageStepper';
import InputStage from './components/stages/InputStage';
import ScrapeStage from './components/stages/ScrapeStage';
import ImageApprovalStage from './components/stages/ImageApprovalStage';
import Generate3DStage from './components/stages/Generate3DStage';
import Approval3DStage from './components/stages/Approval3DStage';
import ReferenceSheetStage from './components/stages/ReferenceSheetStage';

function MainContent() {
  const { currentStage, activeProduct } = useProducts();

  const renderStage = () => {
    const stageKey = `${activeProduct?.id || 'prod'}-stage-${currentStage}`;
    switch (currentStage) {
      case 0:
        return <InputStage key={stageKey} />;
      case 1:
        return <ScrapeStage key={stageKey} />;
      case 2:
        return <ImageApprovalStage key={stageKey} />;
      case 3:
        return <Generate3DStage key={stageKey} />;
      case 4:
        return <Approval3DStage key={stageKey} />;
      case 5:
        return <ReferenceSheetStage key={stageKey} />;
      default:
        return <InputStage key={stageKey} />;
    }
  };


  return (
    <div className="flex h-screen overflow-hidden bg-[#F1F5F9] dark:bg-[#0B1120] text-[#1C2434] dark:text-white">
      {/* Left Sidebar Product Queue */}
      <Sidebar />

      {/* Right Content Area */}
      <div className="flex-1 flex flex-col min-w-0 h-screen overflow-hidden">
        {/* Top Header */}
        <Header />

        {/* 5-Stage Stepper Navigation */}
        <StageStepper />

        {/* Scrollable Stage Viewport */}
        <main className="flex-1 overflow-y-auto bg-[#F8FAFC] dark:bg-[#0B1120] pb-12 transition-colors">
          {renderStage()}
        </main>
      </div>

      {/* Floating Notifications */}
      <ToastContainer />
    </div>
  );
}

function ToastContainer() {
  const { notifications = [], dismissNotification } = useProducts();

  if (notifications.length === 0) return null;

  return (
    <div className="fixed bottom-6 right-6 z-50 flex flex-col gap-2 max-w-sm w-full pointer-events-none">
      {notifications.map((n) => (
        <div
          key={n.id}
          className={`pointer-events-auto flex items-center justify-between p-3.5 rounded-2xl shadow-xl border backdrop-blur-md transition-all animate-slide-up ${
            n.type === 'success'
              ? 'bg-emerald-950/90 text-emerald-100 border-emerald-700/50'
              : n.type === 'error'
              ? 'bg-rose-950/90 text-rose-100 border-rose-700/50'
              : 'bg-[#0E172E]/90 text-slate-100 border-[#1E2C52]'
          }`}
        >
          <div className="flex items-center gap-2.5">
            <div className={`w-2 h-2 rounded-full ${
              n.type === 'success' ? 'bg-emerald-400' : n.type === 'error' ? 'bg-rose-400' : 'bg-brand-400'
            }`} />
            <p className="text-xs font-medium">{n.message}</p>
          </div>
          <button
            onClick={() => dismissNotification(n.id)}
            className="text-xs opacity-60 hover:opacity-100 px-1.5 py-0.5"
          >
            ✕
          </button>
        </div>
      ))}
    </div>
  );
}

export default function App() {
  return (
    <ProductProvider>
      <MainContent />
    </ProductProvider>
  );
}
