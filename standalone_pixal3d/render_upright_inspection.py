import os
import torch
import numpy as np
import trimesh
from PIL import Image, ImageDraw, ImageFont
import nvdiffrast.torch as dr

device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
glctx = dr.RasterizeGLContext()

def get_projection_matrix(fov=38.0, aspect=1.0, near=0.1, far=10.0):
    f = 1.0 / np.tan(np.radians(fov) / 2.0)
    proj = np.zeros((4, 4), dtype=np.float32)
    proj[0, 0] = f / aspect
    proj[1, 1] = f
    proj[2, 2] = (far + near) / (near - far)
    proj[2, 3] = (2.0 * far * near) / (near - far)
    proj[3, 2] = -1.0
    return proj

def get_view_matrix(dist=1.9, elev=12.0, azim=0.0):
    elev_rad = np.radians(elev)
    azim_rad = np.radians(azim)
    eye = np.array([
        dist * np.cos(elev_rad) * np.sin(azim_rad),
        dist * np.sin(elev_rad),
        dist * np.cos(elev_rad) * np.cos(azim_rad)
    ], dtype=np.float32)
    target = np.array([0, 0, 0], dtype=np.float32)
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
    verts = mesh.vertices.copy()
    center = (verts.max(axis=0) + verts.min(axis=0)) / 2.0
    verts -= center
    max_extent = np.max(verts.max(axis=0) - verts.min(axis=0))
    verts = verts / max_extent * 0.95
    
    verts_h = np.concatenate([verts, np.ones((len(verts), 1), dtype=np.float32)], axis=1)
    mvp = proj_mat @ view_mat
    pos_clip = (verts_h @ mvp.T).astype(np.float32)
    
    pos_clip_t = torch.from_numpy(pos_clip).unsqueeze(0).to(device)
    faces_t = torch.from_numpy(mesh.faces.astype(np.int32)).to(device)
    
    rast, _ = dr.rasterize(glctx, pos_clip_t, faces_t, resolution=[resolution, resolution])
    mask = rast[..., 3:4] > 0
    
    if is_pixal3d and texture_img is not None and hasattr(mesh.visual, 'uv'):
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
            color = torch.ones_like(rast[..., :3]) * 0.8
            
    # Key light + fill light
    normals = mesh.vertex_normals.copy()
    normals_t = torch.from_numpy(normals.astype(np.float32)).unsqueeze(0).to(device)
    interp_normals, _ = dr.interpolate(normals_t, rast, faces_t)
    interp_normals = torch.nn.functional.normalize(interp_normals, dim=-1)
    
    key_light = torch.tensor([0.3, 0.6, 0.8], device=device).unsqueeze(0).unsqueeze(0).unsqueeze(0)
    key_light = torch.nn.functional.normalize(key_light, dim=-1)
    fill_light = torch.tensor([-0.4, 0.2, -0.6], device=device).unsqueeze(0).unsqueeze(0).unsqueeze(0)
    fill_light = torch.nn.functional.normalize(fill_light, dim=-1)
    
    diff_key = torch.clamp(torch.sum(interp_normals * key_light, dim=-1, keepdim=True), min=0.0)
    diff_fill = torch.clamp(torch.sum(interp_normals * fill_light, dim=-1, keepdim=True), min=0.0)
    shading = 0.50 + 0.40 * diff_key + 0.15 * diff_fill
    
    shaded_color = color * shading
    bg_color = torch.tensor([0.10, 0.12, 0.16], device=device)
    final_img = torch.where(mask, shaded_color, bg_color)
    
    img_np = (final_img[0].clamp(0.0, 1.0).cpu().numpy() * 255.0).astype(np.uint8)
    return Image.fromarray(img_np)

def main():
    os.makedirs('standalone_pixal3d/renders', exist_ok=True)
    
    p3d_path = 'standalone_pixal3d/output_standard_1536.glb'
    tsr_path = 'backend/cache/models/VS-LS800HD_pixal3d_1791890700133.glb'
    
    # 1. Pixal3D
    p3d_scene = trimesh.load(p3d_path)
    p3d_mesh = trimesh.util.concatenate([g for g in p3d_scene.geometry.values() if isinstance(g, trimesh.Trimesh)])
    mat = list(p3d_scene.geometry.values())[0].visual.material
    p3d_tex = getattr(mat, 'baseColorTexture', None)
    if p3d_tex is None and os.path.exists('standalone_pixal3d/pixal3d_baseColor.png'):
        p3d_tex = Image.open('standalone_pixal3d/pixal3d_baseColor.png')
        
    # Rotate Pixal3D upright (180 around Z so feet are on bottom)
    rot_p3d = trimesh.transformations.rotation_matrix(np.pi, [0, 0, 1])
    p3d_mesh_upright = p3d_mesh.copy()
    p3d_mesh_upright.apply_transform(rot_p3d)
    
    # 2. TripoSR
    tsr_scene = trimesh.load(tsr_path)
    tsr_mesh = trimesh.util.concatenate([g for g in tsr_scene.geometry.values() if isinstance(g, trimesh.Trimesh)])
    # TripoSR rotation: rotate -90 around Z, then check if front faces camera
    rot_tsr = trimesh.transformations.rotation_matrix(-np.pi/2, [0, 0, 1])
    tsr_mesh_upright = tsr_mesh.copy()
    tsr_mesh_upright.apply_transform(rot_tsr)
    
    # Angles:
    # 1. Front: azim=0, elev=5
    # 2. 3/4 Iso: azim=30, elev=18
    # 3. Side: azim=90, elev=5
    # 4. Top: azim=0, elev=82
    # 5. Rear: azim=180, elev=10
    angles = [
        ('01_front', 0.0, 5.0),
        ('02_iso_front_left', 32.0, 18.0),
        ('03_side', 88.0, 8.0),
        ('04_top', 0.0, 80.0),
        ('05_rear', 180.0, 10.0)
    ]
    
    proj = get_projection_matrix()
    
    p3d_renders = {}
    tsr_renders = {}
    
    for tag, azim, elev in angles:
        view = get_view_matrix(dist=1.9, elev=elev, azim=azim)
        img_p3d = render_mesh(p3d_mesh_upright, view, proj, resolution=1024, is_pixal3d=True, texture_img=p3d_tex)
        img_p3d.save(f'standalone_pixal3d/renders/upright_pixal3d_{tag}.png')
        p3d_renders[tag] = img_p3d
        
        img_tsr = render_mesh(tsr_mesh_upright, view, proj, resolution=1024, is_pixal3d=False)
        img_tsr.save(f'standalone_pixal3d/renders/upright_triposr_{tag}.png')
        tsr_renders[tag] = img_tsr
        print(f'Rendered {tag}')
        
    # Build clean composite
    ref_img = Image.open('backend/cache/candidates/verified_4d28321d64f4.jpg').convert('RGB').resize((600, 600))
    w, h = 600, 600
    comp = Image.new('RGB', (w * 3, h * 3), (16, 18, 24))
    draw = ImageDraw.Draw(comp)
    
    # Row 0: Reference | TripoSR Front | Pixal3D Front
    comp.paste(ref_img, (0, 0))
    comp.paste(tsr_renders['01_front'].resize((w, h)), (w, 0))
    comp.paste(p3d_renders['01_front'].resize((w, h)), (w * 2, 0))
    
    # Row 1: Reference Crop / Side | TripoSR Iso | Pixal3D Iso
    comp.paste(tsr_renders['02_iso_front_left'].resize((w, h)), (w, h))
    comp.paste(p3d_renders['02_iso_front_left'].resize((w, h)), (w * 2, h))
    
    # Row 2: TripoSR Top | TripoSR Side | Pixal3D Top
    comp.paste(tsr_renders['03_side'].resize((w, h)), (0, h))
    comp.paste(p3d_renders['03_side'].resize((w, h)), (0, h * 2))
    comp.paste(tsr_renders['04_top'].resize((w, h)), (w, h * 2))
    comp.paste(p3d_renders['04_top'].resize((w, h)), (w * 2, h * 2))
    
    # Labels
    draw.text((25, 25), "REFERENCE INPUT (ViewSonic LS800HD)", fill=(255, 255, 255))
    draw.text((w + 25, 25), "TRIPOSR BASELINE - Front", fill=(255, 180, 80))
    draw.text((w * 2 + 25, 25), "OFFICIAL PIXAL3D 1536 - Front", fill=(80, 255, 140))
    
    draw.text((25, h + 25), "TRIPOSR - Side View", fill=(255, 180, 80))
    draw.text((w + 25, h + 25), "TRIPOSR BASELINE - Isometric 3/4", fill=(255, 180, 80))
    draw.text((w * 2 + 25, h + 25), "OFFICIAL PIXAL3D 1536 - Isometric 3/4", fill=(80, 255, 140))
    
    draw.text((25, h * 2 + 25), "PIXAL3D 1536 - Side View", fill=(80, 255, 140))
    draw.text((w + 25, h * 2 + 25), "TRIPOSR BASELINE - Top View", fill=(255, 180, 80))
    draw.text((w * 2 + 25, h * 2 + 25), "OFFICIAL PIXAL3D 1536 - Top View", fill=(80, 255, 140))
    
    out_matrix = 'standalone_pixal3d/renders/upright_comparison_matrix.png'
    comp.save(out_matrix)
    print(f'Saved upright comparison matrix to {out_matrix}')

if __name__ == '__main__':
    main()
