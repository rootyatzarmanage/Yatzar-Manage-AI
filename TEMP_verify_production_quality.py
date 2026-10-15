import os
import sys
import glob
import json
import torch
import numpy as np
import trimesh
from PIL import Image, ImageDraw, ImageFont

# Add standalone_pixal3d directory to path for nvdiffrast renderer
sys.path.insert(0, os.path.abspath('standalone_pixal3d'))
import nvdiffrast.torch as dr

device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
glctx = dr.RasterizeGLContext()

def get_projection_matrix(fov=36.0, aspect=1.0, near=0.1, far=10.0):
    f = 1.0 / np.tan(np.radians(fov) / 2.0)
    proj = np.zeros((4, 4), dtype=np.float32)
    proj[0, 0] = f / aspect
    proj[1, 1] = f
    proj[2, 2] = (far + near) / (near - far)
    proj[2, 3] = (2.0 * far * near) / (near - far)
    proj[3, 2] = -1.0
    return proj

def get_lookat_matrix(eye, target, up=np.array([0, 1, 0], dtype=np.float32)):
    forward = target - eye
    forward /= np.linalg.norm(forward)
    
    cam_z = -forward
    cam_x = np.cross(up, cam_z)
    if np.linalg.norm(cam_x) < 1e-5:
        up = np.array([0, 0, 1], dtype=np.float32)
        cam_x = np.cross(up, cam_z)
    cam_x /= np.linalg.norm(cam_x)
    cam_y = np.cross(cam_z, cam_x)
    
    view = np.eye(4, dtype=np.float32)
    view[0, :3] = cam_x
    view[1, :3] = cam_y
    view[2, :3] = cam_z
    view[:3, 3] = -view[:3, :3] @ eye
    return view

def get_orbit_camera(dist=2.2, elev=10.0, azim=0.0):
    elev_rad = np.radians(elev)
    azim_rad = np.radians(azim)
    eye = np.array([
        dist * np.cos(elev_rad) * np.sin(azim_rad),
        dist * np.sin(elev_rad),
        dist * np.cos(elev_rad) * np.cos(azim_rad)
    ], dtype=np.float32)
    target = np.array([0, 0, 0], dtype=np.float32)
    return get_lookat_matrix(eye, target)

def render_mesh(mesh, view_mat, proj_mat, resolution=1024, texture_img=None):
    verts = mesh.vertices.copy()
    center = (verts.max(axis=0) + verts.min(axis=0)) / 2.0
    verts -= center
    max_extent = np.max(verts.max(axis=0) - verts.min(axis=0))
    verts = verts / max_extent * 1.05
    
    verts_h = np.concatenate([verts, np.ones((len(verts), 1), dtype=np.float32)], axis=1)
    mvp = proj_mat @ view_mat
    pos_clip = (verts_h @ mvp.T).astype(np.float32)
    
    pos_clip_t = torch.from_numpy(pos_clip).unsqueeze(0).to(device)
    faces_t = torch.from_numpy(mesh.faces.astype(np.int32)).to(device)
    
    rast, _ = dr.rasterize(glctx, pos_clip_t, faces_t, resolution=[resolution, resolution])
    mask = rast[..., 3:4] > 0
    
    if texture_img is not None and hasattr(mesh.visual, 'uv'):
        uvs = mesh.visual.uv.copy()
        uvs[:, 1] = 1.0 - uvs[:, 1]
        uvs_t = torch.from_numpy(uvs.astype(np.float32)).unsqueeze(0).to(device)
        interp_uv, _ = dr.interpolate(uvs_t, rast, faces_t)
        tex_np = np.array(texture_img.convert('RGB'), dtype=np.float32) / 255.0
        tex_t = torch.from_numpy(tex_np).unsqueeze(0).to(device)
        color = dr.texture(tex_t, interp_uv)
    else:
        if hasattr(mesh.visual, 'vertex_colors') and mesh.visual.vertex_colors is not None:
            v_colors = (mesh.visual.vertex_colors[:, :3].astype(np.float32) / 255.0)
            v_colors_t = torch.from_numpy(v_colors).unsqueeze(0).to(device)
            color, _ = dr.interpolate(v_colors_t, rast, faces_t)
        else:
            color = torch.ones_like(rast[..., :3]) * 0.82
            
    # Key light + fill light
    normals = mesh.vertex_normals.copy()
    normals_t = torch.from_numpy(normals.astype(np.float32)).unsqueeze(0).to(device)
    interp_normals, _ = dr.interpolate(normals_t, rast, faces_t)
    interp_normals = torch.nn.functional.normalize(interp_normals, dim=-1)
    
    key_light = torch.tensor([0.4, 0.7, 0.6], device=device).unsqueeze(0).unsqueeze(0).unsqueeze(0)
    key_light = torch.nn.functional.normalize(key_light, dim=-1)
    fill_light = torch.tensor([-0.4, 0.3, -0.6], device=device).unsqueeze(0).unsqueeze(0).unsqueeze(0)
    fill_light = torch.nn.functional.normalize(fill_light, dim=-1)
    
    diff_key = torch.clamp(torch.sum(interp_normals * key_light, dim=-1, keepdim=True), min=0.0)
    diff_fill = torch.clamp(torch.sum(interp_normals * fill_light, dim=-1, keepdim=True), min=0.0)
    shading = 0.52 + 0.38 * diff_key + 0.15 * diff_fill
    
    shaded_color = color * shading
    bg_color = torch.tensor([0.09, 0.10, 0.14], device=device)
    final_img = torch.where(mask, shaded_color, bg_color)
    
    img_np = (final_img[0].clamp(0.0, 1.0).cpu().numpy() * 255.0).astype(np.uint8)
    img_np = np.flip(img_np, axis=0)
    return Image.fromarray(img_np)

def load_glb(path):
    scene = trimesh.load(path)
    mesh = trimesh.util.concatenate([g for g in scene.geometry.values() if isinstance(g, trimesh.Trimesh)])
    mat = list(scene.geometry.values())[0].visual.material
    tex = getattr(mat, 'baseColorTexture', None)
    if tex is None and hasattr(mat, 'image'):
        tex = mat.image
    return mesh, tex

def main():
    os.makedirs('reports/renders', exist_ok=True)
    
    standalone_ref = 'standalone_pixal3d/output_standard_1536.glb'
    
    # Locate latest generated production GLB
    e2e_pattern = 'backend/cache/models/PROD-VIEWSONIC-E2E-*_pixal3d_*.glb'
    candidates = glob.glob(e2e_pattern)
    if not candidates:
        # Fallback to any latest pixal3d glb in backend/cache/models
        candidates = sorted(glob.glob('backend/cache/models/*_pixal3d_*.glb'), key=os.path.getmtime)
    
    if not candidates:
        print("ERROR: No production Pixal3D GLB found!")
        sys.exit(1)
        
    production_glb = sorted(candidates, key=os.path.getmtime)[-1]
    print(f"Comparing Standalone Reference: {standalone_ref}")
    print(f"Versus Live Production GLB:     {production_glb}")
    
    # Metric Audit
    s_size = os.path.getsize(standalone_ref)
    p_size = os.path.getsize(production_glb)
    
    s_mesh, s_tex = load_glb(standalone_ref)
    p_mesh, p_tex = load_glb(production_glb)
    
    print("\n--- GEOMETRY & ASSET METRICS ---")
    print(f"Standalone Reference GLB: {s_size / (1024*1024):.2f} MB | Vertices: {len(s_mesh.vertices):,} | Faces: {len(s_mesh.faces):,}")
    print(f"Production Integrated GLB: {p_size / (1024*1024):.2f} MB | Vertices: {len(p_mesh.vertices):,} | Faces: {len(p_mesh.faces):,}")
    
    if s_tex is not None:
        print(f"Standalone Texture: {s_tex.size} {s_tex.mode}")
    if p_tex is not None:
        print(f"Production Texture: {p_tex.size} {p_tex.mode}")
        
    # Render Multi-Angle Comparisons
    angles = [
        ('01_front', 0.0, 4.0),
        ('02_iso_front_right', -35.0, 18.0),
        ('03_iso_front_left', 35.0, 18.0),
        ('04_top', 0.0, 80.0),
        ('05_side', 90.0, 8.0)
    ]
    
    proj = get_projection_matrix()
    s_renders = {}
    p_renders = {}
    
    for tag, azim, elev in angles:
        view = get_orbit_camera(dist=2.2, elev=elev, azim=azim)
        img_s = render_mesh(s_mesh, view, proj, resolution=1024, texture_img=s_tex)
        img_p = render_mesh(p_mesh, view, proj, resolution=1024, texture_img=p_tex)
        
        img_s.save(f'reports/renders/ref_standalone_{tag}.png')
        img_p.save(f'reports/renders/prod_integrated_{tag}.png')
        s_renders[tag] = img_s
        p_renders[tag] = img_p
        print(f"Rendered {tag}")
        
    # Build Consolidated Comparison Matrix (2 rows x 4 columns: Ref Image, Front, Iso Right, Top)
    ref_img = Image.open('backend/cache/candidates/verified_4d28321d64f4.jpg').convert('RGB').resize((600, 600))
    w, h = 600, 600
    comp = Image.new('RGB', (w * 4, h * 2), (15, 18, 25))
    draw = ImageDraw.Draw(comp)
    
    # Row 1: Standalone Reference
    comp.paste(ref_img, (0, 0))
    comp.paste(s_renders['01_front'].resize((w, h)), (w, 0))
    comp.paste(s_renders['02_iso_front_right'].resize((w, h)), (w * 2, 0))
    comp.paste(s_renders['04_top'].resize((w, h)), (w * 3, 0))
    
    # Row 2: Production Integrated Yatzar
    comp.paste(ref_img, (0, h))
    comp.paste(p_renders['01_front'].resize((w, h)), (w, h))
    comp.paste(p_renders['02_iso_front_right'].resize((w, h)), (w * 2, h))
    comp.paste(p_renders['04_top'].resize((w, h)), (w * 3, h))
    
    # Text Badges
    draw.text((25, 25), "INPUT CANDIDATE (LS800HD)", fill=(255, 255, 255))
    draw.text((w + 25, 25), "STANDALONE REF (1536) - Front", fill=(80, 220, 255))
    draw.text((w * 2 + 25, 25), "STANDALONE REF - Iso Right", fill=(80, 220, 255))
    draw.text((w * 3 + 25, 25), "STANDALONE REF - Top", fill=(80, 220, 255))
    
    draw.text((25, h + 25), "INPUT CANDIDATE (LS800HD)", fill=(255, 255, 255))
    draw.text((w + 25, h + 25), "YATZAR PROD (1536) - Front", fill=(80, 255, 150))
    draw.text((w * 2 + 25, h + 25), "YATZAR PROD - Iso Right", fill=(80, 255, 150))
    draw.text((w * 3 + 25, h + 25), "YATZAR PROD - Top", fill=(80, 255, 150))
    
    matrix_path = 'reports/renders/production_quality_comparison_matrix.png'
    comp.save(matrix_path)
    print(f"\nSaved production comparison matrix to {matrix_path}")
    
    report_data = {
        "status": "SUCCESS",
        "standalone_reference": {
            "path": standalone_ref,
            "size_bytes": s_size,
            "vertices": len(s_mesh.vertices),
            "faces": len(s_mesh.faces),
            "texture": list(s_tex.size) if s_tex else None
        },
        "production_integrated": {
            "path": production_glb,
            "size_bytes": p_size,
            "vertices": len(p_mesh.vertices),
            "faces": len(p_mesh.faces),
            "texture": list(p_tex.size) if p_tex else None
        },
        "comparison_matrix": matrix_path
    }
    with open('TEMP_QUALITY_COMPARISON_REPORT.json', 'w') as f:
        json.dump(report_data, f, indent=2)
    print("Exported TEMP_QUALITY_COMPARISON_REPORT.json")

if __name__ == '__main__':
    main()
