import React, { useRef, useState, useEffect } from 'react';
import * as THREE from 'three';

export default function ThreeCADViewer({ 
  proceduralStep = 3, // 1: Primitives, 2: CSG Booleans, 3: PBR Final
  isInverted = false,
  isPaused = false,
  productName = 'Alfa Laval Industrial Plate Heat Exchanger' 
}) {
  const mountRef = useRef(null);
  const rendererRef = useRef(null);
  const sceneRef = useRef(null);
  const cameraRef = useRef(null);
  const modelGroupRef = useRef(null);
  const isDraggingRef = useRef(false);
  const previousMousePositionRef = useRef({ x: 0, y: 0 });

  // Mesh component refs
  const meshObjectsRef = useRef({});

  useEffect(() => {
    const currentMount = mountRef.current;
    if (!currentMount) return;

    const width = currentMount.clientWidth;
    const height = currentMount.clientHeight || 450;

    // Scene
    const scene = new THREE.Scene();
    scene.background = new THREE.Color('#0B1120');
    sceneRef.current = scene;

    // Camera
    const camera = new THREE.PerspectiveCamera(45, width / height, 0.1, 1000);
    camera.position.set(3.4, 2.2, 4.2);
    camera.lookAt(0, 0, 0);
    cameraRef.current = camera;

    // Renderer
    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    renderer.setSize(width, height);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.shadowMap.enabled = true;
    renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    currentMount.appendChild(renderer.domElement);
    rendererRef.current = renderer;

    // Lighting
    const ambientLight = new THREE.AmbientLight(0xffffff, 0.9);
    scene.add(ambientLight);

    const keyLight = new THREE.DirectionalLight(0xffffff, 2.0);
    keyLight.position.set(5, 10, 7);
    keyLight.castShadow = true;
    scene.add(keyLight);

    const fillLight = new THREE.DirectionalLight(0x38bdf8, 1.0);
    fillLight.position.set(-6, -2, -5);
    scene.add(fillLight);

    const rimLight = new THREE.DirectionalLight(0x818cf8, 0.7);
    rimLight.position.set(0, -8, 4);
    scene.add(rimLight);

    // High-tech Engineering Grid Floor
    const gridHelper = new THREE.GridHelper(12, 24, 0x3b82f6, 0x1e293b);
    gridHelper.position.y = -1.3;
    scene.add(gridHelper);

    // Master CAD Assembly Group
    const modelGroup = new THREE.Group();
    modelGroupRef.current = modelGroup;

    // 1. BOUNDING PRIMITIVES (Wireframe / Semi-transparent stack)
    const bboxGeo = new THREE.BoxGeometry(1.65, 2.25, 1.25);
    const wireframeMat = new THREE.MeshBasicMaterial({
      color: 0x38bdf8,
      wireframe: true,
      transparent: true,
      opacity: 0.8
    });
    const primitiveMesh = new THREE.Mesh(bboxGeo, wireframeMat);
    modelGroup.add(primitiveMesh);
    meshObjectsRef.current.primitiveMesh = primitiveMesh;

    // 2. SOLID GEOMETRY COMPONENTS (Clay / PBR)
    // Front Plate
    const plateGeo = new THREE.BoxGeometry(1.55, 2.15, 0.16);
    const frontPlate = new THREE.Mesh(plateGeo, new THREE.MeshStandardMaterial());
    frontPlate.position.z = 0.55;
    frontPlate.castShadow = true;
    modelGroup.add(frontPlate);
    meshObjectsRef.current.frontPlate = frontPlate;

    // Rear Plate
    const rearPlate = new THREE.Mesh(plateGeo, new THREE.MeshStandardMaterial());
    rearPlate.position.z = -0.55;
    rearPlate.castShadow = true;
    modelGroup.add(rearPlate);
    meshObjectsRef.current.rearPlate = rearPlate;

    // Corrugated Plate Pack (Core)
    const coreGeo = new THREE.BoxGeometry(1.35, 1.95, 0.94);
    const coreMesh = new THREE.Mesh(coreGeo, new THREE.MeshStandardMaterial());
    coreMesh.castShadow = true;
    modelGroup.add(coreMesh);
    meshObjectsRef.current.coreMesh = coreMesh;

    // 4 Corner Fluid Port Flanges (Cylinders punched through)
    const portGeo = new THREE.CylinderGeometry(0.19, 0.19, 0.38, 32);
    const ports = [];
    const portPositions = [
      [0.44, 0.62, 0.68],
      [-0.44, 0.62, 0.68],
      [0.44, -0.62, 0.68],
      [-0.44, -0.62, 0.68]
    ];

    portPositions.forEach((pos, i) => {
      const port = new THREE.Mesh(portGeo, new THREE.MeshStandardMaterial());
      port.rotation.x = Math.PI / 2;
      port.position.set(pos[0], pos[1], pos[2]);
      modelGroup.add(port);
      ports.push(port);
    });
    meshObjectsRef.current.ports = ports;

    // Top and Bottom Carrying Bars (Guide Rails)
    const barGeo = new THREE.CylinderGeometry(0.045, 0.045, 1.6, 16);
    const topBar = new THREE.Mesh(barGeo, new THREE.MeshStandardMaterial());
    topBar.rotation.x = Math.PI / 2;
    topBar.position.set(0, 1.14, 0);
    modelGroup.add(topBar);
    meshObjectsRef.current.topBar = topBar;

    const bottomBar = new THREE.Mesh(barGeo, new THREE.MeshStandardMaterial());
    bottomBar.rotation.x = Math.PI / 2;
    bottomBar.position.set(0, -1.14, 0);
    modelGroup.add(bottomBar);
    meshObjectsRef.current.bottomBar = bottomBar;

    // Tightening Side Compression Bolts (8x bolts along perimeter)
    const boltGeo = new THREE.CylinderGeometry(0.02, 0.02, 1.45, 12);
    const bolts = [];
    const boltYPositions = [0.85, 0.3, -0.3, -0.85];
    boltYPositions.forEach(y => {
      // Left side bolt
      const boltL = new THREE.Mesh(boltGeo, new THREE.MeshStandardMaterial());
      boltL.rotation.x = Math.PI / 2;
      boltL.position.set(-0.72, y, 0);
      modelGroup.add(boltL);
      bolts.push(boltL);

      // Right side bolt
      const boltR = new THREE.Mesh(boltGeo, new THREE.MeshStandardMaterial());
      boltR.rotation.x = Math.PI / 2;
      boltR.position.set(0.72, y, 0);
      modelGroup.add(boltR);
      bolts.push(boltR);
    });
    meshObjectsRef.current.bolts = bolts;

    scene.add(modelGroup);

    // Animation Loop
    let animationId;
    const animate = () => {
      animationId = requestAnimationFrame(animate);
      if (!isDraggingRef.current && !isPaused && modelGroupRef.current) {
        modelGroupRef.current.rotation.y += 0.003;
      }
      renderer.render(scene, camera);
    };
    animate();

    // Mouse Interaction
    const handleMouseDown = (e) => {
      isDraggingRef.current = true;
      previousMousePositionRef.current = { x: e.clientX, y: e.clientY };
    };

    const handleMouseMove = (e) => {
      if (!isDraggingRef.current || !modelGroupRef.current) return;
      const deltaX = e.clientX - previousMousePositionRef.current.x;
      const deltaY = e.clientY - previousMousePositionRef.current.y;

      modelGroupRef.current.rotation.y += deltaX * 0.01;
      modelGroupRef.current.rotation.x += deltaY * 0.01;

      previousMousePositionRef.current = { x: e.clientX, y: e.clientY };
    };

    const handleMouseUp = () => {
      isDraggingRef.current = false;
    };

    const handleWheel = (e) => {
      e.preventDefault();
      if (!cameraRef.current) return;
      cameraRef.current.position.z = Math.max(2, Math.min(9, cameraRef.current.position.z + e.deltaY * 0.005));
    };

    const domElement = renderer.domElement;
    domElement.addEventListener('mousedown', handleMouseDown);
    window.addEventListener('mousemove', handleMouseMove);
    window.addEventListener('mouseup', handleMouseUp);
    domElement.addEventListener('wheel', handleWheel, { passive: false });

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
      domElement.removeEventListener('mousedown', handleMouseDown);
      window.removeEventListener('mousemove', handleMouseMove);
      window.removeEventListener('mouseup', handleMouseUp);
      domElement.removeEventListener('wheel', handleWheel);
      window.removeEventListener('resize', handleResize);
      if (renderer.domElement.parentNode) {
        renderer.domElement.parentNode.removeChild(renderer.domElement);
      }
    };
  }, []);

  // Update Geometry & Materials based on proceduralStep and isInverted
  useEffect(() => {
    const objs = meshObjectsRef.current;
    if (!objs.frontPlate) return;

    if (proceduralStep === 1) {
      // STATE 1: Bounding Primitives (Wireframe streaming)
      objs.primitiveMesh.visible = true;
      objs.frontPlate.visible = false;
      objs.rearPlate.visible = false;
      objs.coreMesh.visible = false;
      objs.topBar.visible = true;
      objs.bottomBar.visible = true;
      objs.ports?.forEach(p => p.visible = false);
      objs.bolts?.forEach(b => b.visible = false);

      objs.topBar.material = new THREE.MeshBasicMaterial({ color: 0x38bdf8, wireframe: true });
      objs.bottomBar.material = new THREE.MeshBasicMaterial({ color: 0x38bdf8, wireframe: true });
    } 
    else if (proceduralStep === 2) {
      // STATE 2: CSG Booleans (Solid Gray Clay with 4 Port Holes)
      objs.primitiveMesh.visible = false;
      objs.frontPlate.visible = true;
      objs.rearPlate.visible = true;
      objs.coreMesh.visible = true;
      objs.topBar.visible = true;
      objs.bottomBar.visible = true;
      objs.ports?.forEach(p => p.visible = true);
      objs.bolts?.forEach(b => b.visible = false);

      const clayMat = new THREE.MeshStandardMaterial({
        color: isInverted ? 0xf87171 : 0xd1d5db,
        metalness: 0.05,
        roughness: 0.8
      });
      const portClayMat = new THREE.MeshStandardMaterial({
        color: isInverted ? 0x991b1b : 0x9ca3af,
        metalness: 0.1,
        roughness: 0.7
      });

      objs.frontPlate.material = clayMat;
      objs.rearPlate.material = clayMat;
      objs.coreMesh.material = clayMat;
      objs.topBar.material = clayMat;
      objs.bottomBar.material = clayMat;
      objs.ports?.forEach(p => p.material = portClayMat);
    } 
    else if (proceduralStep === 3) {
      // STATE 3: PBR Final (Industrial Epoxy Blue #1A4B8B, Metallic Flanges, Chrome Bolts)
      objs.primitiveMesh.visible = false;
      objs.frontPlate.visible = true;
      objs.rearPlate.visible = true;
      objs.coreMesh.visible = true;
      objs.topBar.visible = true;
      objs.bottomBar.visible = true;
      objs.ports?.forEach(p => p.visible = true);
      objs.bolts?.forEach(b => b.visible = true);

      // Industrial Blue Powder Coat
      const blueEpoxyMat = new THREE.MeshStandardMaterial({
        color: 0x1a4b8b, // Alfa Laval Blue
        metalness: 0.78,
        roughness: 0.28
      });

      // Corrugated Plate Pack Core
      const platePackMat = new THREE.MeshStandardMaterial({
        color: 0x334155,
        metalness: 0.92,
        roughness: 0.35
      });

      // Chrome / Stainless Steel Ports
      const chromePortMat = new THREE.MeshStandardMaterial({
        color: isInverted ? 0xf59e0b : 0x60a5fa,
        metalness: 0.95,
        roughness: 0.14
      });

      // Chrome Tightening Guide Bars & Bolts
      const chromeBarMat = new THREE.MeshStandardMaterial({
        color: 0xe2e8f0,
        metalness: 0.98,
        roughness: 0.08
      });

      objs.frontPlate.material = blueEpoxyMat;
      objs.rearPlate.material = blueEpoxyMat;
      objs.coreMesh.material = platePackMat;
      objs.topBar.material = chromeBarMat;
      objs.bottomBar.material = chromeBarMat;
      objs.ports?.forEach(p => p.material = chromePortMat);
      objs.bolts?.forEach(b => b.material = chromeBarMat);
    }
  }, [proceduralStep, isInverted]);

  const setViewAngle = (angle) => {
    if (!modelGroupRef.current) return;
    if (angle === 'front') {
      modelGroupRef.current.rotation.set(0, 0, 0);
    } else if (angle === 'profile') {
      modelGroupRef.current.rotation.set(0, Math.PI / 2, 0);
    } else if (angle === 'rear') {
      modelGroupRef.current.rotation.set(0, Math.PI, 0);
    } else if (angle === 'iso') {
      modelGroupRef.current.rotation.set(0.35, 0.75, 0);
    } else if (angle === 'top') {
      modelGroupRef.current.rotation.set(Math.PI / 2, 0, 0);
    }
  };

  return (
    <div className="relative w-full h-[480px] rounded-xl overflow-hidden bg-slate-950 border border-slate-800 shadow-2xl">
      {/* 3D WebGL Canvas */}
      <div ref={mountRef} className="w-full h-full cursor-grab active:cursor-grabbing" />

      {/* Floating Viewport Camera Presets */}
      <div className="absolute top-3 left-3 flex items-center gap-1.5 bg-slate-900/85 backdrop-blur-md px-2.5 py-1.5 rounded-lg border border-slate-700/60 text-xs text-slate-300">
        <span className="font-semibold text-slate-400">View:</span>
        <button onClick={() => setViewAngle('front')} className="hover:text-white px-2 py-0.5 rounded bg-slate-800/80">0° Front</button>
        <button onClick={() => setViewAngle('profile')} className="hover:text-white px-2 py-0.5 rounded bg-slate-800/80">90° Side</button>
        <button onClick={() => setViewAngle('rear')} className="hover:text-white px-2 py-0.5 rounded bg-slate-800/80">180° Rear</button>
        <button onClick={() => setViewAngle('iso')} className="hover:text-white px-2 py-0.5 rounded bg-blue-600 text-white font-semibold">Isometric</button>
        <button onClick={() => setViewAngle('top')} className="hover:text-white px-2 py-0.5 rounded bg-slate-800/80">Top</button>
      </div>

      {/* Live Procedural Step Tag (Bottom-Left) */}
      <div className="absolute bottom-3 left-3 flex items-center gap-2 px-3 py-1 rounded-md bg-slate-900/90 border border-slate-700 text-xs font-semibold text-slate-200 backdrop-blur-xs">
        <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse"></span>
        <span>
          {proceduralStep === 1 && 'Phase 1: Bounding Wireframe (T = 0s)'}
          {proceduralStep === 2 && 'Phase 2: CSG Boolean Cuts (T = 2s)'}
          {proceduralStep === 3 && 'Phase 3: High-Poly PBR Material (T = 4s)'}
        </span>
        {isInverted && (
          <span className="px-1.5 py-0.5 rounded bg-amber-500 text-black text-[10px] font-bold">
            CUT INVERTED
          </span>
        )}
      </div>

      {/* FPS & WebGL Badge (Bottom-Right) */}
      <div className="absolute bottom-3 right-3 px-2 py-1 rounded bg-slate-900/80 text-[10px] text-slate-400 font-mono border border-slate-800">
        WebGL 60 FPS • three-bvh-csg
      </div>
    </div>
  );
}
