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

function MainContent() {
  const { currentStage } = useProducts();

  const renderStage = () => {
    switch (currentStage) {
      case 0:
        return <InputStage />;
      case 1:
        return <ScrapeStage />;
      case 2:
        return <ImageApprovalStage />;
      case 3:
        return <Generate3DStage />;
      case 4:
        return <Approval3DStage />;
      default:
        return <InputStage />;
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
