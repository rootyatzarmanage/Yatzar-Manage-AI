import React, { useRef, useState, useEffect } from 'react';
import * as THREE from 'three';
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';
import { Box, RotateCw, Eye, Sparkles } from 'lucide-react';

const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:5000';

export default function ThreeCADViewer({ 
  modelUrl = null,
  productName = '3D Product Model',
  meshStats = null,
  onLoaded = null
}) {
  const mountRef = useRef(null);
  const rendererRef = useRef(null);
  const sceneRef = useRef(null);
  const cameraRef = useRef(null);
  const controlsRef = useRef(null);
  const currentModelRef = useRef(null);

  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState(null);
  const [autoRotate, setAutoRotate] = useState(true);
  const [wireframe, setWireframe] = useState(false);

  // Initialize Scene & Renderer
  useEffect(() => {
    const currentMount = mountRef.current;
    if (!currentMount) return;

    const width = currentMount.clientWidth;
    const height = currentMount.clientHeight || 450;

    const scene = new THREE.Scene();
    scene.background = new THREE.Color('#0B1120');
    sceneRef.current = scene;

    const camera = new THREE.PerspectiveCamera(45, width / height, 0.01, 1000);
    camera.position.set(2.5, 1.8, 2.5);
    cameraRef.current = camera;

    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    renderer.setSize(width, height);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.shadowMap.enabled = true;
    renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 1.1;
    currentMount.appendChild(renderer.domElement);
    rendererRef.current = renderer;

    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.dampingFactor = 0.05;
    controls.autoRotate = autoRotate;
    controls.autoRotateSpeed = 1.5;
    controlsRef.current = controls;

    // Lighting
    const ambientLight = new THREE.AmbientLight(0xffffff, 1.2);
    scene.add(ambientLight);

    const keyLight = new THREE.DirectionalLight(0xffffff, 2.0);
    keyLight.position.set(5, 8, 5);
    keyLight.castShadow = true;
    scene.add(keyLight);

    const fillLight = new THREE.DirectionalLight(0x60a5fa, 1.0);
    fillLight.position.set(-5, 2, -4);
    scene.add(fillLight);

    const rimLight = new THREE.DirectionalLight(0xa78bfa, 0.8);
    rimLight.position.set(0, -5, 3);
    scene.add(rimLight);

    // High-tech Engineering Grid Floor
    const gridHelper = new THREE.GridHelper(8, 16, 0x3b82f6, 0x1e293b);
    gridHelper.position.y = -0.01;
    scene.add(gridHelper);

    // Animation loop
    let animationId;
    const animate = () => {
      animationId = requestAnimationFrame(animate);
      if (controlsRef.current) {
        controlsRef.current.autoRotate = autoRotate;
        controlsRef.current.update();
      }
      renderer.render(scene, camera);
    };
    animate();

    const handleResize = () => {
      if (!currentMount || !rendererRef.current || !cameraRef.current) return;
      const w = currentMount.clientWidth;
      const h = currentMount.clientHeight || 450;
      cameraRef.current.aspect = w / h;
      cameraRef.current.updateProjectionMatrix();
      rendererRef.current.setSize(w, h);
    };
    window.addEventListener('resize', handleResize);

    return () => {
      cancelAnimationFrame(animationId);
      window.removeEventListener('resize', handleResize);
      if (renderer.domElement.parentNode) {
        renderer.domElement.parentNode.removeChild(renderer.domElement);
      }
    };
  }, []);

  // Update autoRotate when state changes
  useEffect(() => {
    if (controlsRef.current) {
      controlsRef.current.autoRotate = autoRotate;
    }
  }, [autoRotate]);

  // Load real GLB model
  useEffect(() => {
    if (!sceneRef.current) return;

    // Clear previous loaded model
    if (currentModelRef.current) {
      sceneRef.current.remove(currentModelRef.current);
      currentModelRef.current = null;
    }

    if (!modelUrl) {
      return;
    }

    setLoading(true);
    setLoadError(null);

    const fullUrl = modelUrl.startsWith('http') ? modelUrl : `${API_BASE}${modelUrl}`;
    const loader = new GLTFLoader();

    loader.load(
      fullUrl,
      (gltf) => {
        const model = gltf.scene;

        // Apply materials / wireframe if needed
        model.traverse((child) => {
          if (child.isMesh) {
            child.castShadow = true;
            child.receiveShadow = true;
            if (child.material) {
              child.material.wireframe = wireframe;
            }
          }
        });

        // Compute bounding box and center model
        const box = new THREE.Box3().setFromObject(model);
        const center = box.getCenter(new THREE.Vector3());
        const size = box.getSize(new THREE.Vector3());

        const maxDim = Math.max(size.x, size.y, size.z) || 1.0;
        const scale = 1.6 / maxDim;
        model.scale.set(scale, scale, scale);

        // Center on grid
        model.position.x = -center.x * scale;
        model.position.y = -box.min.y * scale; // Sit on floor
        model.position.z = -center.z * scale;

        sceneRef.current.add(model);
        currentModelRef.current = model;

        if (controlsRef.current && cameraRef.current) {
          cameraRef.current.position.set(2.2, 1.4, 2.2);
          controlsRef.current.target.set(0, 0.8, 0);
          controlsRef.current.update();
        }

        setLoading(false);
        if (onLoaded) {
          onLoaded({ success: true, url: fullUrl });
        }
      },
      (progress) => {
        // Loading progress
      },
      (err) => {
        console.error('Error loading 3D GLB model:', err);
        setLoading(false);
        setLoadError('Failed to load generated 3D asset (.glb).');
        if (onLoaded) {
          onLoaded({ success: false, error: err.message });
        }
      }
    );
  }, [modelUrl]);

  // Toggle wireframe on active model
  useEffect(() => {
    if (currentModelRef.current) {
      currentModelRef.current.traverse((child) => {
        if (child.isMesh && child.material) {
          child.material.wireframe = wireframe;
        }
      });
    }
  }, [wireframe]);

  const setViewAngle = (angle) => {
    if (!controlsRef.current || !cameraRef.current) return;
    if (angle === 'front') {
      cameraRef.current.position.set(0, 0.8, 3.0);
    } else if (angle === 'profile') {
      cameraRef.current.position.set(3.0, 0.8, 0);
    } else if (angle === 'rear') {
      cameraRef.current.position.set(0, 0.8, -3.0);
    } else if (angle === 'iso') {
      cameraRef.current.position.set(2.2, 1.5, 2.2);
    } else if (angle === 'top') {
      cameraRef.current.position.set(0, 3.2, 0.01);
    }
    controlsRef.current.target.set(0, 0.8, 0);
    controlsRef.current.update();
  };

  return (
    <div className="relative w-full h-[480px] rounded-2xl overflow-hidden bg-slate-950 border border-slate-800 shadow-2xl">
      {/* 3D WebGL Canvas */}
      <div ref={mountRef} className="w-full h-full cursor-grab active:cursor-grabbing" />

      {/* Loading Overlay */}
      {loading && (
        <div className="absolute inset-0 bg-slate-950/70 backdrop-blur-xs flex flex-col items-center justify-center text-white z-10">
          <div className="w-8 h-8 border-2 border-brand-500 border-t-transparent rounded-full animate-spin mb-3"></div>
          <span className="text-xs font-semibold tracking-wide">Loading Real 3D Asset (.glb)...</span>
        </div>
      )}

      {/* Error Overlay */}
      {loadError && (
        <div className="absolute inset-0 bg-slate-950/80 backdrop-blur-xs flex flex-col items-center justify-center text-rose-400 z-10 p-6 text-center">
          <span className="text-xs font-bold mb-1">Asset Load Error</span>
          <span className="text-[11px] text-slate-300">{loadError}</span>
        </div>
      )}

      {/* Camera View Angle Presets */}
      <div className="absolute top-3 left-3 flex items-center gap-1.5 bg-slate-900/85 backdrop-blur-md px-2.5 py-1.5 rounded-xl border border-slate-700/60 text-xs text-slate-300">
        <span className="font-semibold text-slate-400">View:</span>
        <button onClick={() => setViewAngle('front')} className="hover:text-white px-2 py-0.5 rounded bg-slate-800/80">Front</button>
        <button onClick={() => setViewAngle('profile')} className="hover:text-white px-2 py-0.5 rounded bg-slate-800/80">Side</button>
        <button onClick={() => setViewAngle('rear')} className="hover:text-white px-2 py-0.5 rounded bg-slate-800/80">Rear</button>
        <button onClick={() => setViewAngle('iso')} className="hover:text-white px-2 py-0.5 rounded bg-brand-600 text-white font-semibold">Iso</button>
        <button onClick={() => setViewAngle('top')} className="hover:text-white px-2 py-0.5 rounded bg-slate-800/80">Top</button>
      </div>

      {/* Interactive Controls Overlay (Top Right) */}
      <div className="absolute top-3 right-3 flex items-center gap-2">
        <button
          onClick={() => setAutoRotate(!autoRotate)}
          className={`px-2.5 py-1 rounded-xl text-xs font-semibold border backdrop-blur-md transition-all flex items-center gap-1.5 ${
            autoRotate
              ? 'bg-brand-500/20 text-brand-300 border-brand-500/40'
              : 'bg-slate-900/80 text-slate-300 border-slate-700/60'
          }`}
        >
          <RotateCw className={`w-3 h-3 ${autoRotate ? 'animate-spin' : ''}`} />
          <span>{autoRotate ? 'Auto-Rotate ON' : 'Auto-Rotate OFF'}</span>
        </button>

        <button
          onClick={() => setWireframe(!wireframe)}
          className={`px-2.5 py-1 rounded-xl text-xs font-semibold border backdrop-blur-md transition-all ${
            wireframe
              ? 'bg-brand-500 text-white border-brand-500'
              : 'bg-slate-900/80 text-slate-300 border-slate-700/60'
          }`}
        >
          Wireframe
        </button>
      </div>

      {/* Model Status Tag (Bottom-Left) */}
      <div className="absolute bottom-3 left-3 flex items-center gap-2 px-3 py-1.5 rounded-xl bg-slate-900/90 border border-slate-700 text-xs font-semibold text-slate-200 backdrop-blur-md">
        <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse"></span>
        <span>{productName}</span>
        {modelUrl && (
          <span className="text-[10px] text-emerald-400 font-mono">
            • Real Binary GLB
          </span>
        )}
      </div>

      {/* Real Mesh Specs (Bottom-Right) */}
      <div className="absolute bottom-3 right-3 px-3 py-1.5 rounded-xl bg-slate-900/90 border border-slate-700 text-[11px] text-slate-300 font-mono backdrop-blur-md">
        {meshStats ? (
          <span>
            {meshStats.vertexCount?.toLocaleString()} Verts • {meshStats.faceCount?.toLocaleString()} Faces • {meshStats.watertight ? 'Watertight' : 'Non-watertight'}
          </span>
        ) : (
          <span>Three.js GLTF Engine</span>
        )}
      </div>
    </div>
  );
}
