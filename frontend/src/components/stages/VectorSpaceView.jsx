import React, { useState } from 'react';
import { Sparkles, Crosshair, ShieldCheck, Eye, Anchor, CheckCircle2, ShieldAlert } from 'lucide-react';

export default function VectorSpaceView({ 
  images = [], 
  seedImage, 
  onInspectAlignment, 
  onToggleSelect 
}) {
  const [hoveredNode, setHoveredNode] = useState(null);

  // Center coordinate of the 600x600 SVG canvas
  const centerX = 300;
  const centerY = 300;

  // Compute 2D positions for candidate images using real PCA coordinates or polar projection
  const nodes = images.map((img, idx) => {
    let x, y;
    if (img.coordinates && typeof img.coordinates.x === 'number' && typeof img.coordinates.y === 'number') {
      // Scale PCA coordinates to the 600x600 SVG canvas (PCA offsets are typically within [-1.5, 1.5])
      const scale = 180;
      x = centerX + Math.max(-240, Math.min(240, img.coordinates.x * scale));
      y = centerY + Math.max(-240, Math.min(240, img.coordinates.y * scale));
    } else {
      const angleRad = (idx / Math.max(images.length, 1)) * 2 * Math.PI - Math.PI / 2;
      const distance = (1.0 - Math.min(Math.max(img.score, 0.2), 0.98)) * 320 + 70;
      x = centerX + Math.cos(angleRad) * distance;
      y = centerY + Math.sin(angleRad) * distance;
    }

    const isHighMatch = img.score >= 0.80;
    const isPassing = img.score >= 0.60;

    return {
      ...img,
      x,
      y,
      isHighMatch,
      isPassing
    };
  });

  return (
    <div className="relative w-full rounded-2xl bg-slate-950 border border-slate-800 p-6 overflow-hidden">
      {/* Top Banner / Legend */}
      <div className="flex flex-wrap items-center justify-between gap-3 mb-4 pb-4 border-b border-slate-800/80">
        <div className="flex items-center gap-2.5">
          <div className="w-7 h-7 rounded-lg bg-brand-500/20 text-brand-400 flex items-center justify-center">
            <Crosshair className="w-4 h-4" />
          </div>
          <div>
            <h3 className="text-xs font-bold text-white uppercase tracking-wider">
              2D Latent Vector Space (t-SNE / PCA Projection)
            </h3>
            <p className="text-[11px] text-slate-400">
              Euclidean distance directly reflects DINOv2 768-dim cosine distance relative to the Seed Anchor.
            </p>
          </div>
        </div>

        {/* Legend */}
        <div className="flex items-center gap-4 text-xs font-medium">
          <div className="flex items-center gap-1.5">
            <span className="w-2.5 h-2.5 rounded-full bg-emerald-500 shadow-sm shadow-emerald-500/50"></span>
            <span className="text-slate-300">Cluster Core (&ge;80%)</span>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="w-2.5 h-2.5 rounded-full bg-amber-500"></span>
            <span className="text-slate-300">Alternate View (65-80%)</span>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="w-2.5 h-2.5 rounded-full bg-rose-500"></span>
            <span className="text-slate-300">Purged Noise (&lt;65%)</span>
          </div>
        </div>
      </div>

      {/* Main Interactive Vector Map Canvas */}
      <div className="relative flex items-center justify-center h-[520px]">
        <svg className="w-full h-full max-w-[600px] max-h-[520px]" viewBox="0 0 600 600">
          {/* Concentric Threshold Radar Rings */}
          {/* 1. High Match Cluster Radius (< 120px) */}
          <circle
            cx={centerX}
            cy={centerY}
            r="120"
            fill="none"
            stroke="#10B981"
            strokeWidth="1"
            strokeDasharray="4 4"
            className="opacity-25"
          />
          <text x={centerX + 8} y={centerY - 125} fill="#10B981" fontSize="9" opacity="0.6">
            Core Cluster (≥ 80% Cosine)
          </text>

          {/* 2. Acceptance Cutoff Gate (< 190px) */}
          <circle
            cx={centerX}
            cy={centerY}
            r="190"
            fill="none"
            stroke="#F59E0B"
            strokeWidth="1.5"
            strokeDasharray="6 6"
            className="opacity-30"
          />
          <text x={centerX + 8} y={centerY - 195} fill="#F59E0B" fontSize="9" opacity="0.7">
            Cutoff Threshold (0.65 Gate)
          </text>

          {/* 3. Outer Perimeter */}
          <circle
            cx={centerX}
            cy={centerY}
            r="260"
            fill="none"
            stroke="#EF4444"
            strokeWidth="1"
            strokeDasharray="2 4"
            className="opacity-20"
          />
          <text x={centerX + 8} y={centerY - 265} fill="#EF4444" fontSize="9" opacity="0.5">
            Noise Perimeter (&lt; 0.65 Purged)
          </text>

          {/* Connector Lines between Seed Anchor and Nodes */}
          {nodes.map((node) => {
            const isHovered = hoveredNode?.id === node.id;
            const strokeColor = node.isHighMatch
              ? '#10B981'
              : node.isPassing
              ? '#F59E0B'
              : '#EF4444';

            return (
              <line
                key={`line-${node.id}`}
                x1={centerX}
                y1={centerY}
                x2={node.x}
                y2={node.y}
                stroke={strokeColor}
                strokeWidth={isHovered ? 2.5 : node.selected ? 1.5 : 0.75}
                strokeDasharray={node.isPassing ? 'none' : '3 3'}
                opacity={isHovered ? 0.9 : node.selected ? 0.5 : 0.25}
                className="transition-all duration-200"
              />
            );
          })}

          {/* Center Origin: SEED ANCHOR */}
          <g transform={`translate(${centerX}, ${centerY})`}>
            {/* Glowing Anchor Rings */}
            <circle r="36" fill="#3C50E0" opacity="0.15" className="animate-ping" />
            <circle r="26" fill="#3C50E0" opacity="0.3" />
            <circle r="20" fill="#2563EB" stroke="#60A5FA" strokeWidth="2.5" />
            <text
              textAnchor="middle"
              dy="3"
              fill="#FFFFFF"
              fontSize="9"
              fontWeight="bold"
            >
              SEED
            </text>
            <text
              textAnchor="middle"
              dy="34"
              fill="#93C5FD"
              fontSize="9"
              fontWeight="bold"
            >
              Origin (0,0)
            </text>
          </g>

          {/* Candidate Nodes */}
          {nodes.map((node) => {
            const isHovered = hoveredNode?.id === node.id;
            const strokeColor = node.isHighMatch
              ? '#10B981'
              : node.isPassing
              ? '#F59E0B'
              : '#EF4444';

            return (
              <g
                key={node.id}
                transform={`translate(${node.x}, ${node.y})`}
                onMouseEnter={() => setHoveredNode(node)}
                onMouseLeave={() => setHoveredNode(null)}
                onClick={() => onInspectAlignment(node)}
                className="cursor-pointer group"
              >
                {/* Outer Selection Halo */}
                {node.selected && (
                  <circle
                    r="22"
                    fill="none"
                    stroke="#3C50E0"
                    strokeWidth="2"
                    strokeDasharray="4 2"
                    className="animate-spin-slow"
                  />
                )}

                {/* Node Body */}
                <circle
                  r={isHovered ? 18 : 14}
                  fill={node.isPassing ? '#1E293B' : '#450A0A'}
                  stroke={strokeColor}
                  strokeWidth={isHovered ? 3 : 2}
                  className="transition-all duration-200 shadow-md"
                />

                {/* Similarity Score Label inside node */}
                <text
                  textAnchor="middle"
                  dy="3.5"
                  fill="#FFFFFF"
                  fontSize={isHovered ? "9" : "8"}
                  fontWeight="bold"
                >
                  {Math.round(node.score * 100)}%
                </text>
              </g>
            );
          })}
        </svg>

        {/* Rich Node Hover Popover Card */}
        {hoveredNode && (
          <div
            className="absolute z-30 w-72 rounded-xl bg-slate-900/95 border border-slate-700 shadow-2xl p-3.5 text-white backdrop-blur-md transition-all pointer-events-auto"
            style={{
              left: Math.min(Math.max(hoveredNode.x - 144, 20), 300),
              top: Math.max(hoveredNode.y - 180, 20)
            }}
          >
            <div className="flex items-start gap-3 mb-2.5">
              <img
                src={hoveredNode.url}
                alt={hoveredNode.title}
                className="w-14 h-14 rounded-lg object-cover border border-slate-700 flex-shrink-0"
              />
              <div className="flex-1 min-w-0">
                <span className="inline-block px-1.5 py-0.5 rounded text-[10px] font-bold bg-brand-500/30 text-brand-300 border border-brand-500/40 mb-1">
                  {hoveredNode.angle}
                </span>
                <p className="text-xs font-semibold truncate leading-tight" title={hoveredNode.title}>
                  {hoveredNode.title}
                </p>
                <p className="text-[10px] text-slate-400">
                  Cosine Match: <span className="text-emerald-400 font-bold">{(hoveredNode.score * 100).toFixed(1)}%</span>
                </p>
              </div>
            </div>

            {/* Quick Actions inside popover */}
            <div className="pt-2 border-t border-slate-800 flex items-center justify-between gap-2">
              <button
                onClick={() => onInspectAlignment(hoveredNode)}
                className="flex-1 flex items-center justify-center gap-1 py-1 px-2 rounded-md bg-slate-800 hover:bg-slate-700 text-slate-200 text-[11px] font-semibold transition-colors"
              >
                <Eye className="w-3 h-3 text-brand-400" />
                <span>Inspect Patch Grid</span>
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
