"""glTF 2.0 Material assembly, .glb packaging, and loose texture file exporter."""

from pathlib import Path
from typing import Dict, Optional
import bpy

from ..config import (
    COLORSPACE_NON_COLOR,
    COLORSPACE_SRGB,
    PASS_AO,
    PASS_BASE_COLOR,
    PASS_EMISSIVE,
    PASS_NORMAL,
    PASS_ORM,
    SUFFIX_BASE_COLOR,
    SUFFIX_EMISSIVE,
    SUFFIX_NORMAL,
    SUFFIX_ORM,
    get_principled_socket,
    set_material_blend_method,
)


def _create_separate_color_node(node_tree: bpy.types.NodeTree) -> tuple:
    """Create a color separation node compatible with Blender 3.6 (Separate RGB)

    and Blender 4.0+ / 5.x (Separate Color).
    Returns (node, red_socket, green_socket, blue_socket).
    """
    if hasattr(bpy.types, "ShaderNodeSeparateColor"):
        node = node_tree.nodes.new("ShaderNodeSeparateColor")
        return node, node.outputs["Red"], node.outputs["Green"], node.outputs["Blue"]
    else:
        node = node_tree.nodes.new("ShaderNodeSeparateRGB")
        return node, node.outputs["R"], node.outputs["G"], node.outputs["B"]


def _get_or_create_gltf_output_node(node_tree: bpy.types.NodeTree) -> Optional[bpy.types.Node]:
    """Find or create the glTF Material Output node group to feed Occlusion into glTF."""
    group_name = "glTF Material Output"
    group = bpy.data.node_groups.get(group_name)

    if not group:
        # Create node group
        group = bpy.data.node_groups.new(name=group_name, type="ShaderNodeTree")
        # Add Occlusion input socket
        if hasattr(group, "interface"):
            # Blender 4.0+
            group.interface.new_socket(name="Occlusion", in_out="INPUT", socket_type="NodeSocketFloat")
        else:
            # Blender 3.6
            group.inputs.new("NodeSocketFloat", "Occlusion")

    group_node = node_tree.nodes.new("ShaderNodeGroup")
    group_node.node_tree = group
    return group_node


def build_synthetic_gltf_material(
    name: str,
    base_color_img: Optional[bpy.types.Image] = None,
    orm_img: Optional[bpy.types.Image] = None,
    normal_img: Optional[bpy.types.Image] = None,
    emissive_img: Optional[bpy.types.Image] = None,
    alpha_mode: str = "OPAQUE",
    alpha_cutoff: float = 0.5,
) -> bpy.types.Material:
    """Construct a clean, synthetic Blender material linking the packed textures

    to standard Principled BSDF and glTF node structures.
    """
    mat_name = f"__synthetic_sl_{name}"
    if mat_name in bpy.data.materials:
        bpy.data.materials.remove(bpy.data.materials[mat_name], do_unlink=True)

    mat = bpy.data.materials.new(name=mat_name)
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()

    # 1. Output Material node
    output_node = nt.nodes.new("ShaderNodeOutputMaterial")
    output_node.location = (400, 0)

    # 2. Principled BSDF node
    principled = nt.nodes.new("ShaderNodeBsdfPrincipled")
    principled.location = (0, 0)
    nt.links.new(principled.outputs["BSDF"], output_node.inputs["Surface"])

    # 3. Base Color & Alpha
    if base_color_img:
        bc_node = nt.nodes.new("ShaderNodeTexImage")
        bc_node.location = (-400, 300)
        bc_node.image = base_color_img
        bc_node.image.colorspace_settings.name = COLORSPACE_SRGB

        bc_sock = get_principled_socket(principled, "Base Color")
        if bc_sock:
            nt.links.new(bc_node.outputs["Color"], bc_sock)

        if alpha_mode in ("MASK", "BLEND"):
            alpha_sock = get_principled_socket(principled, "Alpha")
            if alpha_sock:
                nt.links.new(bc_node.outputs["Alpha"], alpha_sock)

    # 4. ORM (Occlusion, Roughness, Metallic)
    if orm_img:
        orm_node = nt.nodes.new("ShaderNodeTexImage")
        orm_node.location = (-700, -100)
        orm_node.image = orm_img
        orm_node.image.colorspace_settings.name = COLORSPACE_NON_COLOR

        sep_node, out_r, out_g, out_b = _create_separate_color_node(nt)
        sep_node.location = (-400, -100)
        nt.links.new(orm_node.outputs["Color"], sep_node.inputs[0])

        # Link Roughness (Green)
        rough_sock = get_principled_socket(principled, "Roughness")
        if rough_sock:
            nt.links.new(out_g, rough_sock)

        # Link Metallic (Blue)
        metal_sock = get_principled_socket(principled, "Metallic")
        if metal_sock:
            nt.links.new(out_b, metal_sock)

        # Link Occlusion (Red) to glTF Material Output
        try:
            gltf_node = _get_or_create_gltf_output_node(nt)
            if gltf_node:
                gltf_node.location = (400, -200)
                occ_sock = gltf_node.inputs.get("Occlusion")
                if occ_sock:
                    nt.links.new(out_r, occ_sock)
        except Exception:
            pass

    # 5. Normal Map (OpenGL Tangent Space)
    if normal_img:
        norm_tex = nt.nodes.new("ShaderNodeTexImage")
        norm_tex.location = (-700, -400)
        norm_tex.image = normal_img
        norm_tex.image.colorspace_settings.name = COLORSPACE_NON_COLOR

        norm_map = nt.nodes.new("ShaderNodeNormalMap")
        norm_map.location = (-400, -400)
        norm_map.space = "TANGENT"
        nt.links.new(norm_tex.outputs["Color"], norm_map.inputs["Color"])

        norm_sock = get_principled_socket(principled, "Normal")
        if norm_sock:
            nt.links.new(norm_map.outputs["Normal"], norm_sock)

    # 6. Emissive
    if emissive_img:
        emit_tex = nt.nodes.new("ShaderNodeTexImage")
        emit_tex.location = (-400, -700)
        emit_tex.image = emissive_img
        emit_tex.image.colorspace_settings.name = COLORSPACE_SRGB

        emit_sock = get_principled_socket(principled, "Emission")
        if emit_sock:
            nt.links.new(emit_tex.outputs["Color"], emit_sock)

    # 7. Transparency Mode
    if alpha_mode == "MASK":
        set_material_blend_method(mat, "CLIP")
        if hasattr(mat, "alpha_threshold"):
            mat.alpha_threshold = alpha_cutoff
    elif alpha_mode == "BLEND":
        set_material_blend_method(mat, "BLEND")
    else:
        set_material_blend_method(mat, "OPAQUE")

    return mat


def export_standalone_glb(
    material_name: str,
    synthetic_mat: bpy.types.Material,
    output_filepath: Path,
) -> bool:
    """Export the synthetic material applied to a temporary unit plane into a standalone .glb container."""
    output_filepath.parent.mkdir(parents=True, exist_ok=True)

    # Create temporary unit mesh plane
    mesh = bpy.data.meshes.new(name=f"__temp_sl_{material_name}")
    obj = bpy.data.objects.new(name=f"__temp_sl_{material_name}", object_data=mesh)

    # Add 1 quad with UV coordinates
    verts = [(-0.5, -0.5, 0.0), (0.5, -0.5, 0.0), (0.5, 0.5, 0.0), (-0.5, 0.5, 0.0)]
    faces = [(0, 1, 2, 3)]
    mesh.from_pydata(verts, [], faces)
    mesh.update()

    # Add UV layer
    uv_layer = mesh.uv_layers.new(name="UVMap")
    uvs = [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)]
    for i, loop in enumerate(mesh.loops):
        uv_layer.data[loop.index].uv = uvs[i]

    # Assign synthetic material
    mesh.materials.append(synthetic_mat)

    # Link object to active collection
    scene = bpy.context.scene
    scene.collection.objects.link(obj)

    try:
        # Select exclusively
        bpy.ops.object.select_all(action="DESELECT")
        obj.select_set(True)
        bpy.context.view_layer.objects.active = obj

        # glTF export options
        gltf_kwargs = {
            "filepath": str(output_filepath),
            "export_format": "GLB",
            "use_selection": True,
            "export_materials": "EXPORT",
            "export_apply": True,
            "export_image_format": "AUTO",
        }

        # Handle version differences in glTF operator arguments
        bpy.ops.export_scene.gltf(**gltf_kwargs)
        return True

    finally:
        # Clean up temporary plane
        try:
            scene.collection.objects.unlink(obj)
        except Exception:
            pass
        bpy.data.objects.remove(obj, do_unlink=True)
        bpy.data.meshes.remove(mesh, do_unlink=True)


def save_loose_textures(
    material_name: str,
    textures_dir: Path,
    base_color_img: Optional[bpy.types.Image] = None,
    orm_img: Optional[bpy.types.Image] = None,
    normal_img: Optional[bpy.types.Image] = None,
    emissive_img: Optional[bpy.types.Image] = None,
) -> Dict[str, Path]:
    """Save loose PNG texture files to {output_dir}/{MaterialName}/textures/."""
    textures_dir.mkdir(parents=True, exist_ok=True)
    saved_paths: Dict[str, Path] = {}

    texture_map = [
        (base_color_img, f"{material_name}{SUFFIX_BASE_COLOR}", PASS_BASE_COLOR),
        (orm_img, f"{material_name}{SUFFIX_ORM}", "ORM"),
        (normal_img, f"{material_name}{SUFFIX_NORMAL}", PASS_NORMAL),
        (emissive_img, f"{material_name}{SUFFIX_EMISSIVE}", PASS_EMISSIVE),
    ]

    for img, filename, pass_key in texture_map:
        if not img:
            continue
        target_path = textures_dir / filename
        # Save image via Blender image save
        old_filepath = img.filepath_raw
        old_format = img.file_format
        try:
            img.filepath_raw = str(target_path)
            img.file_format = "PNG"
            img.save()
            saved_paths[pass_key] = target_path
        finally:
            img.filepath_raw = old_filepath
            img.file_format = old_format

    return saved_paths
