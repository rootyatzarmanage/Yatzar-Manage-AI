import os
import torch
import numpy as np
import trimesh
from PIL import Image, ImageDraw, ImageFont
import nvdiffrast.torch as dr

device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
glctx = dr.RasterizeGLContext()

def get_projection_matrix(fov=40.0, aspect=1.0, near=0.1, far=10.0):
    f = 1.0 / np.tan(np.radians(fov) / 2.0)
    proj = np.zeros((4, 4), dtype=np.float32)
    proj[0, 0] = f / aspect
    proj[1, 1] = f
    proj[2, 2] = (far + near) / (near - far)
    proj[2, 3] = (2.0 * far * near) / (near - far)
    proj[3, 2] = -1.0
    return proj

def get_view_matrix(dist=1.8, elev=15.0, azim=0.0, center=(0, 0, 0)):
    elev_rad = np.radians(elev)
    azim_rad = np.radians(azim)
    cx, cy, cz = center
    eye = np.array([
        cx + dist * np.cos(elev_rad) * np.sin(azim_rad),
        cy + dist * np.sin(elev_rad),
        cz + dist * np.cos(elev_rad) * np.cos(azim_rad)
    ], dtype=np.float32)
    target = np.array([cx, cy, cz], dtype=np.float32)
    forward = target - eye
    forward = forward / np.linalg.norm(forward)
    up = np.array([0, 1, 0], dtype=np.float32)
    right = np.cross(forward, up)
    if np.linalg.norm(right) < 1e-4:
        up = np.array([0, 0, 1], dtype=np.float32)
        right = np.cross(forward, up)
    right = right / np.linalg.norm(right)
    true_up = np.cross(right, forward)
    view = np.eye(4, dtype=np.float32)
    view[0, :3] = right
    view[1, :3] = true_up
    view[2, :3] = -forward
    view[:3, 3] = -view[:3, :3] @ eye
    return view

def render_mesh(mesh, view_mat, proj_mat, resolution=1024, is_pixal3d=True, texture_img=None):
    # Normalize mesh vertices to fit nicely in unit sphere centered at origin
    verts = mesh.vertices.copy()
    center = (verts.max(axis=0) + verts.min(axis=0)) / 2.0
    verts -= center
    max_extent = np.max(verts.max(axis=0) - verts.min(axis=0))
    verts = verts / max_extent * 1.0  # normalize span to 1.0
    
    verts_h = np.concatenate([verts, np.ones((len(verts), 1), dtype=np.float32)], axis=1)
    mvp = proj_mat @ view_mat
    pos_clip = (verts_h @ mvp.T).astype(np.float32)
    
    pos_clip_t = torch.from_numpy(pos_clip).unsqueeze(0).to(device)
    faces_t = torch.from_numpy(mesh.faces.astype(np.int32)).to(device)
    
    rast, _ = dr.rasterize(glctx, pos_clip_t, faces_t, resolution=[resolution, resolution])
    mask = rast[..., 3:4] > 0
    
    if is_pixal3d and texture_img is not None and hasattr(mesh.visual, 'uv'):
        uvs = mesh.visual.uv.copy()
        uvs[:, 1] = 1.0 - uvs[:, 1]  # flip V coordinate for OpenGL/nvdiffrast
        uvs_t = torch.from_numpy(uvs.astype(np.float32)).unsqueeze(0).to(device)
        
        # Interpolate UVs
        interp_uv, _ = dr.interpolate(uvs_t, rast, faces_t)
        
        # Texture
        tex_np = np.array(texture_img.convert('RGB'), dtype=np.float32) / 255.0
        tex_t = torch.from_numpy(tex_np).unsqueeze(0).to(device)
        color = dr.texture(tex_t, interp_uv)
    else:
        # Vertex colors or shaded neutral
        if hasattr(mesh.visual, 'vertex_colors') and mesh.visual.vertex_colors is not None:
            v_colors = (mesh.visual.vertex_colors[:, :3].astype(np.float32) / 255.0)
            v_colors_t = torch.from_numpy(v_colors).unsqueeze(0).to(device)
            color, _ = dr.interpolate(v_colors_t, rast, faces_t)
        else:
            color = torch.ones_like(rast[..., :3]) * 0.8
            
    # Simple directional light
    normals = mesh.vertex_normals.copy()
    normals_t = torch.from_numpy(normals.astype(np.float32)).unsqueeze(0).to(device)
    interp_normals, _ = dr.interpolate(normals_t, rast, faces_t)
    interp_normals = torch.nn.functional.normalize(interp_normals, dim=-1)
    
    light_dir = torch.tensor([0.2, 0.5, 1.0], device=device).unsqueeze(0).unsqueeze(0).unsqueeze(0)
    light_dir = torch.nn.functional.normalize(light_dir, dim=-1)
    diffuse = torch.clamp(torch.sum(interp_normals * light_dir, dim=-1, keepdim=True), min=0.0)
    shading = 0.45 + 0.55 * diffuse
    
    shaded_color = color * shading
    bg_color = torch.tensor([0.12, 0.14, 0.18], device=device) # sleek dark studio backdrop
    final_img = torch.where(mask, shaded_color, bg_color)
    
    img_np = (final_img[0].clamp(0.0, 1.0).cpu().numpy() * 255.0).astype(np.uint8)
    return Image.fromarray(img_np)

def main():
    os.makedirs('standalone_pixal3d/renders', exist_ok=True)
    
    p3d_path = 'standalone_pixal3d/output_standard_1536.glb'
    tsr_path = 'backend/cache/models/VS-LS800HD_pixal3d_1791890700133.glb'
    
    # Load Pixal3D
    p3d_scene = trimesh.load(p3d_path)
    p3d_mesh = trimesh.util.concatenate([g for g in p3d_scene.geometry.values() if isinstance(g, trimesh.Trimesh)])
    mat = list(p3d_scene.geometry.values())[0].visual.material
    p3d_tex = getattr(mat, 'baseColorTexture', None)
    if p3d_tex is None and os.path.exists('standalone_pixal3d/pixal3d_baseColor.png'):
        p3d_tex = Image.open('standalone_pixal3d/pixal3d_baseColor.png')
        
    # Load TripoSR
    tsr_scene = trimesh.load(tsr_path)
    tsr_mesh = trimesh.util.concatenate([g for g in tsr_scene.geometry.values() if isinstance(g, trimesh.Trimesh)])
    
    # Standard 4 angles:
    # 1. Front (0 deg)
    # 2. Isometric 3/4 front-left (35 deg azim, 20 deg elev)
    # 3. Side (90 deg azim, 10 deg elev)
    # 4. Top-down (0 deg azim, 75 deg elev)
    angles = [
        ('front', 0.0, 15.0),
        ('iso_front_left', 35.0, 20.0),
        ('side_left', 90.0, 10.0),
        ('top', 0.0, 75.0),
        ('rear', 180.0, 15.0)
    ]
    
    proj = get_projection_matrix(fov=40.0, aspect=1.0)
    
    rendered_p3d = {}
    rendered_tsr = {}
    
    print('Rendering Pixal3D 1536...')
    for name, azim, elev in angles:
        view = get_view_matrix(dist=1.8, elev=elev, azim=azim)
        img = render_mesh(p3d_mesh, view, proj, resolution=1024, is_pixal3d=True, texture_img=p3d_tex)
        img.save(f'standalone_pixal3d/renders/pixal3d_1536_{name}.png')
        rendered_p3d[name] = img
        print(f'  Saved pixal3d_1536_{name}.png')
        
    print('Rendering TripoSR Baseline...')
    for name, azim, elev in angles:
        # TripoSR mesh might have different canonical axis (often Z-up or Y-up)
        view = get_view_matrix(dist=1.8, elev=elev, azim=azim)
        img = render_mesh(tsr_mesh, view, proj, resolution=1024, is_pixal3d=False)
        img.save(f'standalone_pixal3d/renders/triposr_{name}.png')
        rendered_tsr[name] = img
        print(f'  Saved triposr_{name}.png')
        
    # Create Side-by-Side Comparison Collage (1024x512 per angle pair)
    # Rows: 1. Input image, 2. Front, 3. Isometric, 4. Side, 5. Top
    ref_img_path = 'backend/cache/candidates/verified_4d28321d64f4.jpg'
    ref_img = Image.open(ref_img_path).convert('RGB').resize((512, 512))
    
    w, h = 512, 512
    collage = Image.new('RGB', (w * 3, h * 4), (20, 22, 28))
    draw = ImageDraw.Draw(collage)
    
    # Column 0: Reference & Info
    # Column 1: TripoSR Baseline
    # Column 2: Official Pixal3D 1536 Cascade
    
    # Row 0: Reference View & Front View
    collage.paste(ref_img, (0, 0))
    collage.paste(rendered_tsr['front'].resize((w, h)), (w, 0))
    collage.paste(rendered_p3d['front'].resize((w, h)), (w * 2, 0))
    
    # Row 1: Isometric View
    collage.paste(rendered_tsr['iso_front_left'].resize((w, h)), (w, h))
    collage.paste(rendered_p3d['iso_front_left'].resize((w, h)), (w * 2, h))
    
    # Row 2: Side View
    collage.paste(rendered_tsr['side_left'].resize((w, h)), (w, h * 2))
    collage.paste(rendered_p3d['side_left'].resize((w, h)), (w * 2, h * 2))
    
    # Row 3: Top View
    collage.paste(rendered_tsr['top'].resize((w, h)), (w, h * 3))
    collage.paste(rendered_p3d['top'].resize((w, h)), (w * 2, h * 3))
    
    # Draw headers & labels
    draw.text((20, 20), "REFERENCE INPUT (LS800HD)", fill=(255, 255, 255))
    draw.text((w + 20, 20), "TRIPOSR (BASELINE) - Front", fill=(255, 200, 100))
    draw.text((w * 2 + 20, 20), "PIXAL3D 1536 - Front", fill=(100, 255, 150))
    
    draw.text((w + 20, h + 20), "TRIPOSR - Isometric 3/4", fill=(255, 200, 100))
    draw.text((w * 2 + 20, h + 20), "PIXAL3D 1536 - Isometric 3/4", fill=(100, 255, 150))
    
    draw.text((w + 20, h * 2 + 20), "TRIPOSR - Side Profile", fill=(255, 200, 100))
    draw.text((w * 2 + 20, h * 2 + 20), "PIXAL3D 1536 - Side Profile", fill=(100, 255, 150))
    
    draw.text((w + 20, h * 3 + 20), "TRIPOSR - Top Down", fill=(255, 200, 100))
    draw.text((w * 2 + 20, h * 3 + 20), "PIXAL3D 1536 - Top Down", fill=(100, 255, 150))
    
    collage.save('standalone_pixal3d/renders/comparison_matrix.png')
    print('Comparison matrix saved to standalone_pixal3d/renders/comparison_matrix.png')

if __name__ == '__main__':
    main()
