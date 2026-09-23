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


def wire_material_textures(mat: bpy.types.Material, texture_dir: Path) -> None:
    """Wire diffuse, ORM, and normal textures from texture_dir into Principled BSDF."""
    if not mat or not mat.use_nodes or not texture_dir.exists():
        return

    nt = mat.node_tree
    principled = None
    for n in nt.nodes:
        if n.type == "BSDF_PRINCIPLED":
            principled = n
            break

    if not principled:
        return

    clean_name = re.sub(r"[^a-zA-Z0-9_\-]", "_", mat.name).strip("_")

    def find_texture(role: str) -> Optional[Path]:
        for pattern in (f"*{clean_name}*{role}*.png", f"*{role}*.png"):
            matches = list(texture_dir.glob(pattern))
            if matches:
                return matches[0]
        return None

    diff_file = find_texture("diffuse") or find_texture("basecolor") or find_texture("BaseColor")
    orm_file = find_texture("orm") or find_texture("ORM")
    norm_file = find_texture("normal") or find_texture("Normal")

    col_x = -700
    row_y = 300

    # 1. Diffuse / Base Color
    if diff_file:
        img = bpy.data.images.load(str(diff_file), check_existing=True)
        img.colorspace_settings.name = COLORSPACE_SRGB
        t_node = nt.nodes.new("ShaderNodeTexImage")
        t_node.image = img
        t_node.location = (col_x, row_y)

        bc_sock = get_principled_socket(principled, "Base Color")
        if bc_sock:
            nt.links.new(t_node.outputs["Color"], bc_sock)

        if "Alpha" in t_node.outputs:
            alpha_sock = get_principled_socket(principled, "Alpha")
            if alpha_sock:
                nt.links.new(t_node.outputs["Alpha"], alpha_sock)
                set_material_blend_method(mat, "BLEND")
        row_y -= 260

    # 2. ORM
    if orm_file:
        orm_img = bpy.data.images.load(str(orm_file), check_existing=True)
        orm_img.colorspace_settings.name = COLORSPACE_NON_COLOR
        t_orm = nt.nodes.new("ShaderNodeTexImage")
        t_orm.image = orm_img
        t_orm.location = (col_x, row_y)

        # Separate Color / RGB
        if hasattr(bpy.types, "ShaderNodeSeparateColor"):
            sep = nt.nodes.new("ShaderNodeSeparateColor")
            out_g = sep.outputs["Green"]
            out_b = sep.outputs["Blue"]
        else:
            sep = nt.nodes.new("ShaderNodeSeparateRGB")
            out_g = sep.outputs["G"]
            out_b = sep.outputs["B"]

        sep.location = (col_x + 300, row_y)
        nt.links.new(t_orm.outputs["Color"], sep.inputs[0])

        rough_sock = get_principled_socket(principled, "Roughness")
        if rough_sock:
            nt.links.new(out_g, rough_sock)

        metal_sock = get_principled_socket(principled, "Metallic")
        if metal_sock:
            nt.links.new(out_b, metal_sock)
        row_y -= 260

    # 3. Normal
    if norm_file:
        norm_img = bpy.data.images.load(str(norm_file), check_existing=True)
        norm_img.colorspace_settings.name = COLORSPACE_NON_COLOR
        t_norm = nt.nodes.new("ShaderNodeTexImage")
        t_norm.image = norm_img
        t_norm.location = (col_x, row_y)

        norm_map = nt.nodes.new("ShaderNodeNormalMap")
        norm_map.location = (col_x + 300, row_y)
        nt.links.new(t_norm.outputs["Color"], norm_map.inputs["Color"])

        norm_sock = get_principled_socket(principled, "Normal")
        if norm_sock:
            nt.links.new(norm_map.outputs["Normal"], norm_sock)


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

    # Wire materials
    effective_tex_dir = textures_dir or (dae_path.parent / "textures")
    if effective_tex_dir.exists():
        for mesh_obj in imported_meshes:
            for slot in mesh_obj.material_slots:
                if slot.material:
                    wire_material_textures(slot.material, effective_tex_dir)

    return imported_meshes
