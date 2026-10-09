import * as THREE from 'three';
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';

/**
 * Deterministic Multi-View 3D Renderer for Reconstructed GLB Assets.
 * Renders Front, Rear, Side, and Top/3-Quarter views deterministically from the GLB geometry.
 * Auto-frames models of any aspect ratio using exact bounding box / sphere calculations.
 */
export async function renderDeterministicViews(modelUrl, options = {}) {
  const width = options.width || 800;
  const height = options.height || 800;
  const backgroundColor = options.backgroundColor !== undefined ? options.backgroundColor : 0xf8fafc;

  return new Promise((resolve, reject) => {
    if (!modelUrl) {
      return reject(new Error('Model URL is required for multi-view rendering'));
    }

    const loader = new GLTFLoader();
    loader.load(
      modelUrl,
      (gltf) => {
        try {
          // Off-screen isolated WebGL renderer
          const renderer = new THREE.WebGLRenderer({
            antialias: true,
            alpha: true,
            preserveDrawingBuffer: true,
            powerPreference: 'high-performance'
          });
          renderer.setSize(width, height);
          renderer.setPixelRatio(1);
          renderer.toneMapping = THREE.ACESFilmicToneMapping;
          renderer.toneMappingExposure = 1.2;
          renderer.shadowMap.enabled = true;
          renderer.shadowMap.type = THREE.PCFSoftShadowMap;

          const scene = new THREE.Scene();
          scene.background = new THREE.Color(backgroundColor);

          // Studio Lighting Setup
          const ambientLight = new THREE.AmbientLight(0xffffff, 2.0);
          scene.add(ambientLight);

          const keyLight = new THREE.DirectionalLight(0xffffff, 2.5);
          keyLight.position.set(5, 8, 5);
          scene.add(keyLight);

          const fillLight = new THREE.DirectionalLight(0xe2e8f0, 1.8);
          fillLight.position.set(-5, 3, -4);
          scene.add(fillLight);

          const backLight = new THREE.DirectionalLight(0xffffff, 1.5);
          backLight.position.set(0, 5, -5);
          scene.add(backLight);

          const bottomLight = new THREE.DirectionalLight(0xffffff, 0.8);
          bottomLight.position.set(0, -5, 0);
          scene.add(bottomLight);

          const model = gltf.scene;

          // Preserve vertex colors and material appearances
          model.traverse((child) => {
            if (child.isMesh) {
              child.castShadow = true;
              child.receiveShadow = true;
              if (child.material) {
                child.material.side = THREE.DoubleSide;
                child.material.roughness = 0.45;
                child.material.metalness = 0.15;
              }
            }
          });

          scene.add(model);

          // Calculate bounding box and center model at origin (0, 0, 0)
          const box = new THREE.Box3().setFromObject(model);
          const center = box.getCenter(new THREE.Vector3());
          const size = box.getSize(new THREE.Vector3());
          model.position.sub(center);

          // Adaptive camera distance calculation
          const maxDim = Math.max(size.x, size.y, size.z) || 1.0;
          const fov = 45;
          const camera = new THREE.PerspectiveCamera(fov, width / height, 0.01, 1000);
          const dist = (maxDim / 2) / Math.tan(THREE.MathUtils.degToRad(fov / 2)) * 1.35;

          const renderedViews = {};

          // 1. FRONT VIEW (Camera along +Z facing -Z towards (0,0,0))
          camera.position.set(0, 0, dist);
          camera.lookAt(0, 0, 0);
          camera.updateProjectionMatrix();
          renderer.render(scene, camera);
          renderedViews.front = renderer.domElement.toDataURL('image/png');

          // 2. REAR VIEW (Camera along -Z facing +Z towards (0,0,0))
          camera.position.set(0, 0, -dist);
          camera.lookAt(0, 0, 0);
          camera.updateProjectionMatrix();
          renderer.render(scene, camera);
          renderedViews.rear = renderer.domElement.toDataURL('image/png');

          // 3. SIDE VIEW (Right Profile: Camera along +X facing -X towards (0,0,0))
          camera.position.set(dist, 0, 0);
          camera.lookAt(0, 0, 0);
          camera.updateProjectionMatrix();
          renderer.render(scene, camera);
          renderedViews.side = renderer.domElement.toDataURL('image/png');

          // 4. TOP / 3-QUARTER VIEW (Camera at isometric elevation)
          const isoDist = dist * 0.75;
          camera.position.set(isoDist, isoDist * 0.9, isoDist);
          camera.lookAt(0, 0, 0);
          camera.updateProjectionMatrix();
          renderer.render(scene, camera);
          renderedViews.top_3quarter = renderer.domElement.toDataURL('image/png');

          // Clean up GPU and scene resources
          scene.traverse((obj) => {
            if (obj.geometry) obj.geometry.dispose();
            if (obj.material) {
              if (Array.isArray(obj.material)) {
                obj.material.forEach((m) => m.dispose());
              } else {
                obj.material.dispose();
              }
            }
          });
          renderer.dispose();

          resolve({
            views: renderedViews,
            dimensions: {
              width: parseFloat(size.x.toFixed(3)),
              height: parseFloat(size.y.toFixed(3)),
              depth: parseFloat(size.z.toFixed(3))
            },
            renderedAt: new Date().toISOString()
          });
        } catch (err) {
          reject(err);
        }
      },
      undefined,
      (error) => {
        reject(error);
      }
    );
  });
}
