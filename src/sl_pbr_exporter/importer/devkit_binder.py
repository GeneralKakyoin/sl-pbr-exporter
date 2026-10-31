"""Avastar DevKit armature detection, auto-appending, coordinate alignment, and mesh binding."""

import math
from pathlib import Path
import re
from typing import List, Optional, Tuple
import bpy
import mathutils
import numpy as np

from ..config import (
    COLORSPACE_NON_COLOR,
    COLORSPACE_SRGB,
    deselect_all_objects,
    ensure_object_mode,
    get_principled_socket,
    set_material_blend_method,
)
from .sl_shape_engine import BENTO_FACIAL_FEATURE_BONES, BODY_TORSO_BONES


def get_devkit_armature(scene: Optional[bpy.types.Scene] = None) -> Optional[bpy.types.Object]:
    """Locate the DevKit / avatar armature in the scene."""
    sc = scene or bpy.context.scene

    # Check for exact 'Avatar' name first
    avatar_obj = sc.objects.get("Avatar")
    if avatar_obj and avatar_obj.type == "ARMATURE":
        return avatar_obj

    # Check for avastar in name
    for obj in sc.objects:
        if obj.type == "ARMATURE" and "avastar" in obj.name.lower():
            return obj

    # Fallback to any armature containing standard SL joints
    for obj in sc.objects:
        if obj.type == "ARMATURE" and obj.data:
            if any(b in obj.data.bones for b in ("mPelvis", "mHead", "mChest")):
                return obj

    # Fallback to any armature in the scene
    for obj in sc.objects:
        if obj.type == "ARMATURE":
            return obj

    return None


# The 7 anatomical body chains in the Second Life skeleton:
# Pelvis, Torso/Spine, Chest, Left Arm, Right Arm, Left Leg, Right Leg
ANATOMICAL_BODY_CHAINS = (
    ("pelvis", {"mPelvis", "PELVIS", "BUTT", "mGroin", "BELLY"}),
    ("torso", {"mTorso", "mSpine1", "mSpine2", "mSpine3", "mSpine4"}),
    ("chest", {"mChest", "CHEST", "UPPER_BACK", "LEFT_PEC", "RIGHT_PEC"}),
    ("left_arm", {"mCollarLeft", "mShoulderLeft", "mElbowLeft", "mWristLeft", "L_CLAVICLE", "L_UPPER_ARM", "L_LOWER_ARM", "L_HAND"}),
    ("right_arm", {"mCollarRight", "mShoulderRight", "mElbowRight", "mWristRight", "R_CLAVICLE", "R_UPPER_ARM", "R_LOWER_ARM", "R_HAND"}),
    ("left_leg", {"mHipLeft", "mKneeLeft", "mAnkleLeft", "mFootLeft", "L_UPPER_LEG", "L_LOWER_LEG", "L_FOOT"}),
    ("right_leg", {"mHipRight", "mKneeRight", "mAnkleRight", "mFootRight", "R_UPPER_LEG", "R_LOWER_LEG", "R_FOOT"}),
)

EXTREMITIES_BONES = {
    "mNeck", "NECK", "mWristLeft", "mWristRight", "L_HAND", "R_HAND",
    "mAnkleLeft", "mAnkleRight", "mFootLeft", "mFootRight", "mToeLeft", "mToeRight", "L_FOOT", "R_FOOT"
}


def find_body_mesh(
    scene: Optional[bpy.types.Scene] = None,
    candidates: Optional[List[bpy.types.Object]] = None,
) -> Optional[bpy.types.Object]:
    """Locate the primary avatar body mesh purely via Second Life skeleton topology and 3D bounds.

    100% name-agnostic and brand-agnostic: evaluates bone weight coverage across the 7
    anatomical chains of the Linden/Bento skeleton, extremities coverage (neck, wrists, ankles),
    vertical height span (Delta Z), and vertex count. Zero name keywords.
    """
    sc = scene or bpy.context.scene
    pool = candidates if candidates is not None else [o for o in sc.objects if o.type == "MESH"]

    # Collect rig widget custom shapes to ignore
    rig_widgets = {
        pb.custom_shape
        for obj in sc.objects
        if obj.type == "ARMATURE" and obj.pose
        for pb in obj.pose.bones
        if pb.custom_shape
    }

    scored_candidates = []

    for obj in pool:
        if not obj or obj.type != "MESH" or not obj.data:
            continue
        if obj in rig_widgets:
            continue
        v_count = len(obj.data.vertices)
        if v_count < 30:  # Collision hulls / dummy bounding boxes
            continue
        if not obj.vertex_groups:
            continue

        vnames_set = {g.name for g in obj.vertex_groups}

        # Must be bound to at least one Second Life body deformation bone
        body_bones_present = vnames_set.intersection(BODY_TORSO_BONES)
        if not body_bones_present:
            continue

        # Bento facial filter: if predominantly facial bones with minimal body bones, it is a head
        facial_bones_present = vnames_set.intersection(BENTO_FACIAL_FEATURE_BONES)
        if len(facial_bones_present) > 10 and len(body_bones_present) < 3:
            continue

        # 1. Anatomical chain coverage (0 to 7)
        chains_covered = sum(1 for _, chain_bones in ANATOMICAL_BODY_CHAINS if vnames_set & chain_bones)

        # 2. Extremities coverage (neck, wrists/hands, ankles/feet)
        extremities_covered = len(vnames_set & EXTREMITIES_BONES)

        # 3. 3D Bounding Box vertical span (Delta Z)
        try:
            z_coords = [v.co.z for v in obj.data.vertices]
            span_z = max(z_coords) - min(z_coords)
        except Exception:
            span_z = 0.0

        # Composite anatomical score:
        # Full body covers 5-7 chains, reaches extremities, spans > 1.0m height
        score = (
            (chains_covered * 200)
            + (min(extremities_covered, 6) * 40)
            + int(span_z * 200)
            + min(v_count // 50, 100)
        )

        scored_candidates.append((score, obj))

    if scored_candidates:
        scored_candidates.sort(key=lambda x: x[0], reverse=True)
        return scored_candidates[0][1]

    return None


def align_armature_to_blender_space(arm_obj: bpy.types.Object) -> None:
    """Rotate imported Second Life Collada armature -90 degrees around Z to face Blender Front (-Y).

    Bakes rotation into rest bones and resets matrix_world to Identity.
    """
    if not arm_obj or arm_obj.type != "ARMATURE":
        return
    if arm_obj.get("sl_aligned_to_devkit", False):
        return

    R = mathutils.Matrix.Rotation(math.radians(-90.0), 4, "Z")
    arm_obj.matrix_world = R @ arm_obj.matrix_world
    ensure_object_mode()
    deselect_all_objects()
    arm_obj.select_set(True)
    bpy.context.view_layer.objects.active = arm_obj
    try:
        bpy.ops.object.transform_apply(location=False, rotation=True, scale=False)
    except Exception as e:
        print(f"[Importer] Warning applying rotation to armature: {e}")
    arm_obj["sl_aligned_to_devkit"] = True
    deselect_all_objects()


def append_devkit_from_blend(
    blend_path: Path,
    load_body: bool = True,
) -> Tuple[Optional[bpy.types.Object], Optional[bpy.types.Object]]:
    """Append the DevKit armature and body mesh from a .blend file into the active scene.

    If load_body is False, only the armature is appended; body meshes, cuts,
    and helper geometry are omitted.

    Returns (armature_obj, body_obj).
    """
    if not blend_path.exists():
        raise FileNotFoundError(f"DevKit .blend file not found: {blend_path}")

    scene = bpy.context.scene
    target_coll = scene.collection

    loaded_objects = []
    with bpy.data.libraries.load(str(blend_path), link=False) as (data_from, data_to):
        if not load_body and "Avatar" in data_from.objects:
            data_to.objects = ["Avatar"]
        else:
            # Exclude lights and cameras, load potential avatar objects
            target_names = [name for name in data_from.objects if name not in ("Camera", "Light")]
            data_to.objects = target_names

    armature_obj = None

    for obj in data_to.objects:
        if not obj:
            continue
        if not load_body and obj.type != "ARMATURE":
            bpy.data.objects.remove(obj, do_unlink=True)
            continue
        if obj.name not in scene.objects:
            target_coll.objects.link(obj)
        loaded_objects.append(obj)

        if obj.type == "ARMATURE" and not armature_obj:
            armature_obj = obj

    body_obj = None
    if load_body:
        # Universal body mesh discovery among loaded objects
        body_obj = find_body_mesh(scene, candidates=loaded_objects)
        if body_obj:
            body_obj.hide_viewport = False
            body_obj.hide_render = False

        setup_devkit_visibility(scene)

    return armature_obj, body_obj


def setup_devkit_visibility(scene: Optional[bpy.types.Scene] = None) -> None:
    """Clean up avatar and devkit visibility in a 100% name-agnostic manner:
    - Keep primary body mesh visible.
    - Hide bone custom shape widgets referenced by pose bones (pb.custom_shape).
    - Hide collision hulls / dummy bounding boxes (< 30 verts).
    - Never hide any user-imported mesh based on name strings.
    """
    sc = scene or bpy.context.scene
    body = find_body_mesh(sc)
    if body:
        body.hide_viewport = False
        body.hide_render = False

    # Collect rig widget custom shapes from all armatures directly via RNA object pointer
    rig_widgets = set()
    for obj in sc.objects:
        if obj.type == "ARMATURE" and obj.pose:
            for pb in obj.pose.bones:
                if pb.custom_shape:
                    rig_widgets.add(pb.custom_shape)

    for obj in sc.objects:
        if obj == body:
            continue
        if obj in rig_widgets:
            obj.hide_viewport = True
            obj.hide_render = True
            continue

        # Hide collision hulls / dummy boxes (< 30 vertices)
        if obj.type == "MESH" and obj.data and len(obj.data.vertices) < 30:
            obj.hide_viewport = True
            obj.hide_render = True
            continue


def align_item_to_devkit(mesh_obj: bpy.types.Object) -> None:
    """Rotate imported mesh -90 degrees around Z to convert from Second Life space

    (+X forward, +Y left) to Blender/Avastar space (-Y forward, +X left),
    and bake the rotation into vertex coordinates.
    """
    if not mesh_obj or mesh_obj.type != "MESH":
        return

    R = mathutils.Matrix.Rotation(math.radians(-90.0), 4, "Z")
    mesh_obj.matrix_world = R @ mesh_obj.matrix_world
    mesh_obj.data.transform(mesh_obj.matrix_world)
    mesh_obj.matrix_world = mathutils.Matrix.Identity(4)
    mesh_obj["sl_aligned_to_devkit"] = True
    mesh_obj.data.update()


def image_has_transparency(img: bpy.types.Image) -> bool:
    """Determine if an image texture contains active transparent or semi-transparent pixels.

    100% data-driven: samples pixel alpha channel directly using vectorized NumPy.
    Zero name matching or string keywords.
    """
    if not img or img.channels < 4:
        return False
    w, h = img.size
    if w == 0 or h == 0:
        return False
    # Dummy 1x1 or low-res placeholder textures (< 32x32)
    if w <= 32 and h <= 32:
        return True
    try:
        px = np.empty(w * h * 4, dtype=np.float32)
        img.pixels.foreach_get(px)
        alpha = px[3::4]
        return bool(np.any(alpha < 0.98))
    except Exception:
        return False


def is_skin_material(mat: bpy.types.Material) -> bool:
    """Deprecated keyword stub retained for backward compatibility."""
    return False


def wire_material_textures(
    mat: bpy.types.Material,
    texture_dir: Optional[Path] = None,
    material_meta: Optional[dict] = None,
    dae_dir: Optional[Path] = None,
) -> None:
    """Wire diffuse, ORM, normal, specular, and emissive textures into Principled BSDF.

    Uses metadata from *_materials.json if provided, with robust regex and glob fallbacks.
    """
    if not mat or not mat.use_nodes or not mat.node_tree:
        return

    nt = mat.node_tree
    nodes = nt.nodes
    links = nt.links

    # 1. Locate or create Principled BSDF & Material Output
    principled = next((n for n in nodes if n.type == "BSDF_PRINCIPLED"), None)
    out_node = next((n for n in nodes if n.type == "OUTPUT_MATERIAL"), None)

    if not principled:
        principled = nodes.new("ShaderNodeBsdfPrincipled")
        principled.location = (0, 300)

    if not out_node:
        out_node = nodes.new("ShaderNodeOutputMaterial")
        out_node.location = (300, 300)
        links.new(principled.outputs["BSDF"], out_node.inputs["Surface"])

    # Clean legacy stray importer nodes from Collada import (keep BSDF & Output)
    for n in list(nodes):
        if n not in (principled, out_node):
            nodes.remove(n)

    # 2. Resolve texture file paths
    clean_mat_name = re.sub(r"[^a-zA-Z0-9_\-]", "_", mat.name).strip("_")

    meta_folder = material_meta.get("folder") if material_meta else None

    def resolve_meta_path(path_val: Optional[str]) -> Optional[Path]:
        if not path_val:
            return None
        p = Path(path_val)
        if p.is_absolute() and p.exists():
            return p
        search_roots = [
            r
            for r in (
                dae_dir,
                dae_dir / "textures" if dae_dir else None,
                dae_dir / "textures" / meta_folder if (dae_dir and meta_folder) else None,
                texture_dir,
                texture_dir / meta_folder if (texture_dir and meta_folder) else None,
                texture_dir.parent if texture_dir else None,
                texture_dir.parent / meta_folder if (texture_dir and meta_folder) else None,
                texture_dir.parent / "textures" / meta_folder if (texture_dir and meta_folder) else None,
            )
            if r
        ]
        for root in search_roots:
            cand = root / path_val
            if cand.exists():
                return cand
        return None

    m_diff = resolve_meta_path(material_meta.get("diffuse")) if material_meta else None
    m_norm = resolve_meta_path(material_meta.get("normal")) if material_meta else None
    m_orm = resolve_meta_path(material_meta.get("orm")) if material_meta else None
    m_rough = resolve_meta_path(material_meta.get("roughness")) if material_meta else None
    m_spec = resolve_meta_path(material_meta.get("specular")) if material_meta else None
    m_emissive = resolve_meta_path(material_meta.get("emissive")) if material_meta else None
    m_color = material_meta.get("diffuse_color") if material_meta else None
    m_roughness = material_meta.get("roughness_val") if material_meta else None
    m_metallic = material_meta.get("metallic_val") if material_meta else None

    # Fallback texture discovery if not specified in manifest
    def find_texture(role: str) -> Optional[Path]:
        search_dirs = []
        if meta_folder and dae_dir:
            search_dirs.append(dae_dir / "textures" / meta_folder)
        if meta_folder and texture_dir:
            search_dirs.append(texture_dir / meta_folder)
            search_dirs.append(texture_dir.parent / meta_folder)
            search_dirs.append(texture_dir.parent / "textures" / meta_folder)
        if texture_dir:
            search_dirs.append(texture_dir)
        search_dirs = [d for d in search_dirs if d and d.exists() and d.is_dir()]
        if not search_dirs:
            return None

        m_idx = re.search(r"_(\d+)_mat$", clean_mat_name)
        mat_prefix = f"{m_idx.group(1)}_" if m_idx else ""

        for s_dir in search_dirs:
            # Priority 1: prefix + role (e.g. 1_diffuse.png)
            if mat_prefix:
                c1 = s_dir / f"{mat_prefix}{role}.png"
                if c1.exists():
                    return c1
                for f in s_dir.glob(f"{mat_prefix}*{role}*.png"):
                    return f

            # Priority 2: clean_name + role
            for f in s_dir.glob(f"*{clean_mat_name}*{role}*.png"):
                return f

            # Priority 3: role.png
            c2 = s_dir / f"{role}.png"
            if c2.exists():
                return c2
            for f in s_dir.glob(f"*{role}*.png"):
                return f
        return None

    diff_file = m_diff or find_texture("diffuse") or find_texture("basecolor")
    norm_file = m_norm or find_texture("normal")
    orm_file = m_orm or find_texture("orm")
    rough_file = m_rough or find_texture("roughness")
    spec_file = m_spec or find_texture("specular")
    emissive_file = m_emissive or find_texture("emissive")

    col_x = -750
    row_y = 300

    # 3. Wire Diffuse / Base Color
    diff_color = m_color or getattr(mat, "diffuse_color", [1.0, 1.0, 1.0, 1.0])

    if diff_file and diff_file.exists():
        img = bpy.data.images.load(str(diff_file), check_existing=True)
        img.colorspace_settings.name = COLORSPACE_SRGB
        t_node = nodes.new("ShaderNodeTexImage")
        t_node.image = img
        t_node.location = (col_x, row_y)

        bc_sock = get_principled_socket(principled, "Base Color")
        if bc_sock:
            # If tint is non-white, multiply diffuse texture with tint color
            if any(abs(c - 1.0) > 0.04 for c in diff_color[:3]):
                mix_node = nodes.new("ShaderNodeMix")
                mix_node.data_type = "RGBA"
                mix_node.blend_type = "MULTIPLY"
                mix_node.inputs[0].default_value = 1.0
                mix_node.inputs[7].default_value = diff_color
                mix_node.location = (col_x + 300, row_y)
                links.new(t_node.outputs["Color"], mix_node.inputs[6])
                links.new(mix_node.outputs[2], bc_sock)
            else:
                links.new(t_node.outputs["Color"], bc_sock)

        # Alpha wiring: data-driven inspection of actual image pixels
        has_trans = image_has_transparency(img)
        is_dummy = hasattr(img, "size") and img.size[0] <= 32 and img.size[1] <= 32

        if diff_color[3] == 0.0 and (is_dummy or not has_trans):
            # Inactive/dummy linkset shell: force alpha 0
            if "Alpha" in principled.inputs:
                principled.inputs["Alpha"].default_value = 0.0
            set_material_blend_method(mat, "HASHED")
        elif not has_trans and diff_color[3] >= 0.95:
            # Image is 100% opaque across all pixels (skin, opaque clothing, denim, leather)
            if "Alpha" in principled.inputs:
                principled.inputs["Alpha"].default_value = 1.0
            set_material_blend_method(mat, "OPAQUE")
        else:
            # Image contains active transparency (hair strands, lashes, lace, tattoos, mesh cutouts)
            if "Alpha" in t_node.outputs and "Alpha" in principled.inputs:
                if 0.0 < diff_color[3] < 0.96:
                    math_node = nodes.new("ShaderNodeMath")
                    math_node.operation = "MULTIPLY"
                    math_node.inputs[1].default_value = diff_color[3]
                    math_node.location = (col_x + 300, row_y - 100)
                    links.new(t_node.outputs["Alpha"], math_node.inputs[0])
                    links.new(math_node.outputs["Value"], principled.inputs["Alpha"])
                else:
                    links.new(t_node.outputs["Alpha"], principled.inputs["Alpha"])
            set_material_blend_method(mat, "HASHED")
        row_y -= 280
    else:
        # Solid diffuse color
        bc_sock = get_principled_socket(principled, "Base Color")
        if bc_sock:
            bc_sock.default_value = (diff_color[0], diff_color[1], diff_color[2], 1.0)
        if diff_color[3] == 0.0 and "Alpha" in principled.inputs:
            principled.inputs["Alpha"].default_value = 0.0
            set_material_blend_method(mat, "HASHED")
        else:
            set_material_blend_method(mat, "OPAQUE" if diff_color[3] >= 0.95 else "HASHED")

    # 4. Wire Normal Map
    if norm_file and norm_file.exists():
        norm_img = bpy.data.images.load(str(norm_file), check_existing=True)
        norm_img.colorspace_settings.name = COLORSPACE_NON_COLOR
        t_norm = nodes.new("ShaderNodeTexImage")
        t_norm.image = norm_img
        t_norm.location = (col_x, row_y)

        norm_map = nodes.new("ShaderNodeNormalMap")
        norm_map.location = (col_x + 300, row_y)
        links.new(t_norm.outputs["Color"], norm_map.inputs["Color"])

        norm_sock = get_principled_socket(principled, "Normal")
        if norm_sock:
            links.new(norm_map.outputs["Normal"], norm_sock)
        row_y -= 280

    # 5. Wire ORM / Roughness / Metallic (PBR)
    if orm_file and orm_file.exists():
        orm_img = bpy.data.images.load(str(orm_file), check_existing=True)
        orm_img.colorspace_settings.name = COLORSPACE_NON_COLOR
        t_orm = nodes.new("ShaderNodeTexImage")
        t_orm.image = orm_img
        t_orm.location = (col_x, row_y)

        if hasattr(bpy.types, "ShaderNodeSeparateColor"):
            sep = nodes.new("ShaderNodeSeparateColor")
            out_g = sep.outputs["Green"]
            out_b = sep.outputs["Blue"]
        else:
            sep = nodes.new("ShaderNodeSeparateRGB")
            out_g = sep.outputs["G"]
            out_b = sep.outputs["B"]

        sep.location = (col_x + 300, row_y)
        links.new(t_orm.outputs["Color"], sep.inputs[0])

        rough_sock = get_principled_socket(principled, "Roughness")
        if m_roughness is not None and rough_sock:
            rough_sock.default_value = float(m_roughness)
        elif rough_sock:
            links.new(out_g, rough_sock)

        metal_sock = get_principled_socket(principled, "Metallic")
        if m_metallic is not None and metal_sock:
            metal_sock.default_value = float(m_metallic)
        elif metal_sock:
            links.new(out_b, metal_sock)
        row_y -= 280
    elif rough_file and rough_file.exists():
        r_img = bpy.data.images.load(str(rough_file), check_existing=True)
        r_img.colorspace_settings.name = COLORSPACE_NON_COLOR
        t_rough = nodes.new("ShaderNodeTexImage")
        t_rough.image = r_img
        t_rough.location = (col_x, row_y)

        rough_sock = get_principled_socket(principled, "Roughness")
        if rough_sock:
            links.new(t_rough.outputs["Color"], rough_sock)
        row_y -= 280
    else:
        rough_sock = get_principled_socket(principled, "Roughness")
        if m_roughness is not None and rough_sock:
            rough_sock.default_value = float(m_roughness)
        metal_sock = get_principled_socket(principled, "Metallic")
        if m_metallic is not None and metal_sock:
            metal_sock.default_value = float(m_metallic)

    # 6. Wire Specular
    if spec_file and spec_file.exists():
        spec_img = bpy.data.images.load(str(spec_file), check_existing=True)
        spec_img.colorspace_settings.name = COLORSPACE_NON_COLOR
        t_spec = nodes.new("ShaderNodeTexImage")
        t_spec.image = spec_img
        t_spec.location = (col_x, row_y)

        spec_sock = get_principled_socket(principled, "Specular") or get_principled_socket(principled, "Specular IOR Level")
        if spec_sock:
            links.new(t_spec.outputs["Color"], spec_sock)
        row_y -= 280

    # 7. Wire Emissive
    if emissive_file and emissive_file.exists():
        em_img = bpy.data.images.load(str(emissive_file), check_existing=True)
        em_img.colorspace_settings.name = COLORSPACE_SRGB
        t_em = nodes.new("ShaderNodeTexImage")
        t_em.image = em_img
        t_em.location = (col_x, row_y)

        em_sock = get_principled_socket(principled, "Emission Color") or get_principled_socket(principled, "Emission")
        if em_sock:
            links.new(t_em.outputs["Color"], em_sock)
        row_y -= 280

    # 8. Material tweaks for latex/vinyl/leather
    mat_lower = mat.name.lower()
    if any(k in mat_lower for k in ("latex", "rubber", "vinyl", "leather")):
        rough_sock = get_principled_socket(principled, "Roughness")
        if rough_sock and not rough_sock.is_linked and m_roughness is None:
            rough_sock.default_value = 0.08
        spec_sock = get_principled_socket(principled, "Specular") or get_principled_socket(principled, "Specular IOR Level")
        if spec_sock and not spec_sock.is_linked:
            spec_sock.default_value = 0.9


def hide_inactive_linkset_meshes(meshes: List[bpy.types.Object]) -> None:
    """Hide dummy collision hulls (< 30 verts) and inactive/zero-alpha linkset submeshes (e.g. legacy head UVs)."""
    for mesh_obj in meshes:
        if not mesh_obj or mesh_obj.type != "MESH" or not mesh_obj.data:
            continue
        if len(mesh_obj.data.vertices) < 30:
            mesh_obj.hide_viewport = True
            mesh_obj.hide_render = True
            continue

        valid_slots = [s for s in mesh_obj.material_slots if s.material]
        if not valid_slots:
            continue

        is_all_transparent = True
        for s in valid_slots:
            m = s.material
            alpha = 1.0
            if m.use_nodes and m.node_tree:
                bsdf = next((n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED"), None)
                if bsdf and "Alpha" in bsdf.inputs:
                    if bsdf.inputs["Alpha"].is_linked:
                        is_all_transparent = False
                        break
                    alpha = bsdf.inputs["Alpha"].default_value
            elif hasattr(m, "diffuse_color"):
                alpha = m.diffuse_color[3]

            if alpha > 0.01:
                is_all_transparent = False
                break

        if is_all_transparent:
            mesh_obj.hide_viewport = True
            mesh_obj.hide_render = True


def import_and_bind_item(
    dae_path: Path,
    devkit_arm: Optional[bpy.types.Object] = None,
    textures_dir: Optional[Path] = None,
) -> List[bpy.types.Object]:
    """Import a Collada DAE item, align -90° Z, parent to DevKit armature, and wire materials."""
    if not dae_path.exists():
        raise FileNotFoundError(f"DAE file not found: {dae_path}")

    pre_names = set(bpy.data.objects.keys())
    bpy.ops.wm.collada_import(filepath=str(dae_path))
    post_names = set(bpy.data.objects.keys())
    new_names = list(post_names - pre_names)

    imported_meshes: List[bpy.types.Object] = []
    stray_armatures: List[bpy.types.Object] = []

    for name in new_names:
        obj = bpy.data.objects.get(name)
        if not obj:
            continue
        if obj.type == "MESH":
            imported_meshes.append(obj)
        elif obj.type == "ARMATURE":
            if devkit_arm and obj == devkit_arm:
                continue
            stray_armatures.append(obj)

    # If no devkit_arm was provided, adopt the first imported armature as the avatar armature
    target_arm = devkit_arm
    if not target_arm and stray_armatures:
        target_arm = stray_armatures.pop(0)
        target_arm.name = "Avatar"
        align_armature_to_blender_space(target_arm)

    # Collection setup
    item_stem = dae_path.stem
    coll_name = f"Imported - {item_stem[:25]}"
    target_coll = bpy.data.collections.get(coll_name)
    if not target_coll:
        target_coll = bpy.data.collections.new(coll_name)
        bpy.context.scene.collection.children.link(target_coll)

    for mesh_obj in imported_meshes:
        align_item_to_devkit(mesh_obj)

        # Move to dedicated collection
        for c in list(mesh_obj.users_collection):
            c.objects.unlink(mesh_obj)
        target_coll.objects.link(mesh_obj)

        # Add or update Armature modifier if target_arm provided
        if target_arm:
            arm_mod = next((m for m in mesh_obj.modifiers if m.type == "ARMATURE"), None)
            if not arm_mod:
                arm_mod = mesh_obj.modifiers.new(name="Armature", type="ARMATURE")
            arm_mod.object = target_arm
            mesh_obj.parent = target_arm

    # Remove extra duplicate armatures from this DAE import
    if target_arm:
        for arm in stray_armatures:
            bpy.data.objects.remove(arm, do_unlink=True)

    # -----------------------------------------------------------------------
    # Wire materials with manifest and texture folder detection
    # -----------------------------------------------------------------------
    # 1. Load materials metadata from *_materials.json if present
    materials_manifest: dict = {}
    manifest_candidates = [
        dae_path.parent / f"{item_stem}_materials.json",
        dae_path.parent / f"{item_stem.replace('_combined', '')}_materials.json",
    ]
    for cand in manifest_candidates:
        if cand.exists():
            try:
                import json
                with open(cand, "r", encoding="utf-8") as mf:
                    mf_data = json.load(mf)
                    materials_manifest = mf_data.get("materials", {})
                    break
            except Exception:
                pass

    if not materials_manifest:
        # Check all *_materials.json in folder
        for cand in sorted(dae_path.parent.glob("*_materials.json")):
            try:
                import json
                with open(cand, "r", encoding="utf-8") as mf:
                    mf_data = json.load(mf)
                    materials_manifest.update(mf_data.get("materials", {}))
            except Exception:
                pass

    # 2. Determine effective texture directory
    clean_stem = re.sub(r"[^a-zA-Z0-9_\-]", "_", item_stem)
    candidate_tex_dirs = [
        textures_dir,
        dae_path.parent / "textures" / clean_stem,
        dae_path.parent / "textures" / item_stem,
        dae_path.parent / clean_stem,
        dae_path.parent / "textures",
        dae_path.parent,
    ]
    effective_tex_dir = None
    for cand_dir in candidate_tex_dirs:
        if cand_dir and cand_dir.exists() and cand_dir.is_dir():
            if any(cand_dir.glob("*.png")):
                effective_tex_dir = cand_dir
                break
    if not effective_tex_dir and (dae_path.parent / "textures").exists():
        effective_tex_dir = dae_path.parent / "textures"

    # 3. Wire each unique material once
    processed_materials = set()
    for mesh_obj in imported_meshes:
        for slot in mesh_obj.material_slots:
            mat = slot.material
            if not mat or mat.name in processed_materials:
                continue
            processed_materials.add(mat.name)

            # Match metadata from manifest with strict priority order
            meta = None
            if materials_manifest:
                # 1. Exact match on manifest key or v["name"]
                for k, v in materials_manifest.items():
                    if k == mat.name or v.get("name") == mat.name:
                        meta = v
                        break
                # 2. Case-insensitive exact match
                if not meta:
                    for k, v in materials_manifest.items():
                        if k.lower() == mat.name.lower() or v.get("name", "").lower() == mat.name.lower():
                            meta = v
                            break
                # 3. Normalized match (stripping leading mat_ / Mat_ and trailing _mat)
                if not meta:
                    norm_mat = re.sub(r"^mat_", "", mat.name.lower())
                    norm_mat = re.sub(r"_mat$", "", norm_mat)
                    for k, v in materials_manifest.items():
                        norm_k = re.sub(r"^mat_", "", re.sub(r"_mat$", "", k.lower()))
                        norm_v = re.sub(r"^mat_", "", re.sub(r"_mat$", "", v.get("name", "").lower()))
                        if norm_mat in (norm_k, norm_v):
                            meta = v
                            break
                # 4. Fallback: match on exact material slot number suffix (e.g. _1_mat -> ends with _1)
                if not meta:
                    m_idx = re.search(r"_(\d+)_mat$", mat.name)
                    if m_idx:
                        slot_str = m_idx.group(1)
                        for k, v in materials_manifest.items():
                            v_name = v.get("name", "")
                            if (
                                k.endswith(f"_{slot_str}")
                                or k.endswith(f"_{slot_str}_mat")
                                or v_name.endswith(f"_{slot_str}_mat")
                            ):
                                meta = v
                                break

            wire_material_textures(
                mat,
                texture_dir=effective_tex_dir,
                material_meta=meta,
                dae_dir=dae_path.parent,
            )

    # Hide zero-alpha helper shells & cutouts (< 30 verts or all zero alpha)
    hide_inactive_linkset_meshes(imported_meshes)

    return imported_meshes


