import os
import sys
import gc
import time
import torch
import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pixal3d.pipelines import Pixal3DImageTo3DPipeline
import o_voxel

def main():
    print("[Export] Starting GLB generation from Stage 4 latents...")
    cache_latents_pt = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_stage4_latents_1536.pt")
    cache_mesh_pt = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_stage5_mesh_1536.pt")
    output_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output_standard_1536.glb")

    if os.path.exists(cache_mesh_pt):
        print(f"[Export] Found cached stage 5 mesh at {cache_mesh_pt}, loading directly...")
        mesh_data = torch.load(cache_mesh_pt, weights_only=False)
        vertices = mesh_data['vertices'].cuda()
        faces = mesh_data['faces'].cuda()
        attrs = mesh_data['attrs'].cuda()
        coords = mesh_data['coords'].cuda()
        pbr_layout = mesh_data['pbr_layout']
        res = mesh_data['res']
    else:
        assert os.path.exists(cache_latents_pt), f"Latents cache not found: {cache_latents_pt}"

        # 1. Load pipeline for decoding only
        print("[Export] Loading pipeline decoders...")
        pipeline = Pixal3DImageTo3DPipeline.from_pretrained("TencentARC/Pixal3D")
        pipeline.low_vram = True
        pipeline._device = torch.device("cuda")

        # 2. Load latents
        print("[Export] Loading cached latents...")
        data = torch.load(cache_latents_pt, weights_only=False)
        shape_slat = data['shape_slat'].to('cuda')
        tex_slat = data['tex_slat'].to('cuda')
        res = data['res']
        del data
        gc.collect()
        torch.cuda.empty_cache()

        # 3. Decode latent
        t0 = time.time()
        print(f"[Export] Decoding latent at resolution {res}...")
        mesh_list = pipeline.decode_latent(shape_slat, tex_slat, res)
        mesh = mesh_list[0]
        print(f"[Export] Latent decoded in {time.time() - t0:.2f}s!")
        print(f"         Vertices: {mesh.vertices.shape}, Faces: {mesh.faces.shape}")
        print(f"         Attrs: {mesh.attrs.shape}, Coords: {mesh.coords.shape}")

        pbr_layout = pipeline.pbr_attr_layout
        vertices = mesh.vertices
        faces = mesh.faces
        attrs = mesh.attrs
        coords = mesh.coords

        # Cache decoded mesh so decode_latent never needs to run again
        try:
            torch.save({
                'vertices': vertices.cpu(),
                'faces': faces.cpu(),
                'attrs': attrs.cpu(),
                'coords': coords.cpu(),
                'pbr_layout': pbr_layout,
                'res': res,
            }, cache_mesh_pt)
            print(f"[Export] Decoded mesh cached to: {cache_mesh_pt}")
            vertices = vertices.cuda()
            faces = faces.cuda()
            attrs = attrs.cuda()
            coords = coords.cuda()
        except Exception as e:
            print(f"[Export] Warning: Could not cache mesh: {e}")

        del mesh_list, mesh, shape_slat, tex_slat, pipeline
        gc.collect()
        torch.cuda.empty_cache()

    print(f"[Export] Pipeline unloaded. VRAM allocated: {torch.cuda.memory_allocated() / (1024**2):.1f} MB")

    # 4. Extract GLB
    # Ensure attrs and vertices are float32 to avoid dtype mismatch in grid_sample_3d
    t1 = time.time()
    print("[Export] Running o_voxel.postprocess.to_glb with remesh=False and float32 attrs...")
    glb = o_voxel.postprocess.to_glb(
        vertices=vertices.float(),
        faces=faces,
        attr_volume=attrs.float(),
        coords=coords,
        attr_layout=pbr_layout,
        grid_size=res,
        aabb=[[-0.5, -0.5, -0.5], [0.5, 0.5, 0.5]],
        decimation_target=300000,
        texture_size=2048,
        remesh=False,
        verbose=True,
        use_tqdm=True,
    )

    print(f"[Export] to_glb completed in {time.time() - t1:.2f}s!")

    # 5. Apply rotation
    rot = np.array([
        [-1,  0,  0,  0],
        [ 0,  0, -1,  0],
        [ 0, -1,  0,  0],
        [ 0,  0,  0,  1],
    ], dtype=np.float64)
    glb.apply_transform(rot)

    # 6. Export GLB
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    glb.export(output_path, extension_webp=True)
    print(f"[DONE] Official Pixal3D 1536 GLB exported to: {output_path}")
    print(f"       File size: {os.path.getsize(output_path)} bytes ({os.path.getsize(output_path) / (1024**2):.2f} MB)")

if __name__ == "__main__":
    main()
