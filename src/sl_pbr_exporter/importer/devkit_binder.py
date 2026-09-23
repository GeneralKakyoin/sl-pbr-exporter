"""Avastar DevKit armature detection, auto-appending, coordinate alignment, and mesh binding."""

import math
from pathlib import Path
import re
from typing import List, Optional, Tuple
import bpy
import mathutils

from ..config import (
    COLORSPACE_NON_COLOR,
    COLORSPACE_SRGB,
    get_principled_socket,
    set_material_blend_method,
)


def get_devkit_armature(scene: Optional[bpy.types.Scene] = None) -> Optional[bpy.types.Object]:
    """Locate the DevKit Avastar armature ('Avatar' or rig containing 'avastar') in the scene."""
    sc = scene or bpy.context.scene

    # Check for exact 'Avatar' name first
    avatar_obj = sc.objects.get("Avatar")
    if avatar_obj and avatar_obj.type == "ARMATURE":
        return avatar_obj

    # Check for avastar in name
    for obj in sc.objects:
        if obj.type == "ARMATURE" and "avastar" in obj.name.lower():
            return obj

    # Fallback to any armature in the scene
    for obj in sc.objects:
        if obj.type == "ARMATURE":
            return obj

    return None


def append_devkit_from_blend(blend_path: Path) -> Tuple[Optional[bpy.types.Object], Optional[bpy.types.Object]]:
    """Append the DevKit armature and body mesh from a .blend file into the active scene.

    Returns (armature_obj, body_obj).
    """
    if not blend_path.exists():
        raise FileNotFoundError(f"DevKit .blend file not found: {blend_path}")

    scene = bpy.context.scene
    target_coll = scene.collection

    loaded_objects = []
    with bpy.data.libraries.load(str(blend_path), link=False) as (data_from, data_to):
        # Prefer specific DevKit objects if present
        needed = {"Avatar", "RebornBody"}
        target_names = [name for name in data_from.objects if name in needed]
        if not target_names:
            # If named differently, take all objects in the dev kit
            target_names = [name for name in data_from.objects if name not in ("Camera", "Light")]
        data_to.objects = target_names

    armature_obj = None
    body_obj = None

    for obj in data_to.objects:
        if not obj:
            continue
        if obj.name not in scene.objects:
            target_coll.objects.link(obj)
        loaded_objects.append(obj)

        if obj.type == "ARMATURE" and not armature_obj:
            armature_obj = obj
        elif "body" in obj.name.lower() or obj.name == "RebornBody":
            body_obj = obj
            obj.hide_viewport = False
            obj.hide_render = False

    return armature_obj, body_obj


def setup_devkit_visibility() -> None:
    """Clean up devkit visibility: keep RebornBody visible, hide alternate body variations."""
    body = bpy.data.objects.get("RebornBody")
    if body:
        body.hide_viewport = False
        body.hide_render = False

    hide_prefixes = ("RebornBody+", "RebornFeet_", "CustomShape_")
    for obj in bpy.data.objects:
        if any(obj.name.startswith(p) for p in hide_prefixes) and obj != body:
            obj.hide_viewport = True


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
    mesh_obj.data.update()


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

    def resolve_meta_path(path_val: Optional[str]) -> Optional[Path]:
        if not path_val:
            return None
        p = Path(path_val)
        if p.is_absolute() and p.exists():
            return p
        search_roots = [r for r in (dae_dir, texture_dir, texture_dir.parent if texture_dir else None) if r]
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
        if not texture_dir or not texture_dir.exists():
            return None
        m_idx = re.search(r"_(\d+)_mat$", clean_mat_name)
        mat_prefix = f"{m_idx.group(1)}_" if m_idx else ""

        # Priority 1: prefix + role (e.g. 1_diffuse.png)
        if mat_prefix:
            c1 = texture_dir / f"{mat_prefix}{role}.png"
            if c1.exists():
                return c1
            for f in texture_dir.glob(f"{mat_prefix}*{role}*.png"):
                return f

        # Priority 2: clean_name + role
        for f in texture_dir.glob(f"*{clean_mat_name}*{role}*.png"):
            return f

        # Priority 3: role.png
        c2 = texture_dir / f"{role}.png"
        if c2.exists():
            return c2
        for f in texture_dir.glob(f"*{role}*.png"):
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
    is_skin = any(
        mat.name.lower().startswith(p)
        for p in (
            "skin_",
            "mat_skin_",
            "mat_body_upper",
            "mat_body_lower",
            "mat_head",
            "body_upper",
            "body_lower",
            "head_mat",
            "rebornbody",
        )
    )

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

        # Alpha wiring
        if is_skin:
            set_material_blend_method(mat, "OPAQUE")
        else:
            if "Alpha" in t_node.outputs and "Alpha" in principled.inputs:
                if diff_color[3] < 0.96 and diff_color[3] > 0.0:
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
        set_material_blend_method(mat, "OPAQUE" if is_skin else "HASHED")

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

    # 7. Wire Emissive (only if non-skin)
    if emissive_file and emissive_file.exists() and not is_skin:
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


def import_and_bind_item(
    dae_path: Path,
    devkit_arm: bpy.types.Object,
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
        elif obj.type == "ARMATURE" and obj != devkit_arm:
            stray_armatures.append(obj)

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

        # Add or update Armature modifier
        arm_mod = next((m for m in mesh_obj.modifiers if m.type == "ARMATURE"), None)
        if not arm_mod:
            arm_mod = mesh_obj.modifiers.new(name="Armature", type="ARMATURE")
        arm_mod.object = devkit_arm
        mesh_obj.parent = devkit_arm

    # Remove stray Collada armature from DAE import
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

            # Match metadata from manifest
            meta = None
            if materials_manifest:
                for k, v in materials_manifest.items():
                    v_name = v.get("name", "")
                    if k == mat.name or v_name == mat.name or mat.name.startswith(k) or k.startswith(mat.name):
                        meta = v
                        break
                    m_idx = re.search(r"_(\d+)_mat$", mat.name)
                    if m_idx and (f"_{m_idx.group(1)}" in k or f"_{m_idx.group(1)}_mat" in v_name):
                        meta = v
                        break

            wire_material_textures(
                mat,
                texture_dir=effective_tex_dir,
                material_meta=meta,
                dae_dir=dae_path.parent,
            )

        # Hide zero-alpha helper shells
        if len(mesh_obj.data.vertices) <= 4:
            mesh_obj.hide_viewport = True
            mesh_obj.hide_render = True

    return imported_meshes
