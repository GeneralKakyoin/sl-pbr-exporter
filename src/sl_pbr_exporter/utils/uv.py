"""UV validation, overlap detection, and mirrored UV island handling utilities."""

from typing import List, Tuple
import bpy


def has_active_uv_layer(obj: bpy.types.Object) -> bool:
    """Check if the object is a mesh with at least one UV layer."""
    if not obj or obj.type != "MESH" or not obj.data:
        return False
    return len(obj.data.uv_layers) > 0


def get_active_uv_name(obj: bpy.types.Object) -> str:
    """Return the active UV map name for the mesh object, or empty string."""
    if not has_active_uv_layer(obj):
        return ""
    active = obj.data.uv_layers.active
    return active.name if active else obj.data.uv_layers[0].name


def detect_mirrored_uv_faces(mesh: bpy.types.Mesh) -> List[int]:
    """Detect polygon indices in the active UV layer that have inverted winding order

    (negative 2D cross product area in UV space), indicating mirrored geometry.
    """
    if not mesh or not mesh.uv_layers:
        return []

    uv_layer = mesh.uv_layers.active or mesh.uv_layers[0]
    uv_data = uv_layer.data
    mirrored_faces: List[int] = []

    for poly_idx, poly in enumerate(mesh.polygons):
        if poly.loop_total < 3:
            continue

        # Get first 3 loop UV coordinates
        l0 = poly.loop_indices[0]
        l1 = poly.loop_indices[1]
        l2 = poly.loop_indices[2]

        u0, v0 = uv_data[l0].uv
        u1, v1 = uv_data[l1].uv
        u2, v2 = uv_data[l2].uv

        # 2D cross-product area
        cross = (u1 - u0) * (v2 - v0) - (v1 - v0) * (u2 - u0)
        if cross < -1e-6:
            mirrored_faces.append(poly_idx)

    return mirrored_faces


def offset_mirrored_uv_faces(mesh: bpy.types.Mesh, offset_u: float = 1.0) -> List[int]:
    """Temporarily shift UV coordinates of mirrored faces by offset_u (e.g. +1.0 in U)

    so that Cycles baking treats them as outside the active 0-1 bake tile,
    preventing self-overlap baking seams and blackened shadows.
    Returns list of modified loop indices.
    """
    mirrored_poly_indices = set(detect_mirrored_uv_faces(mesh))
    if not mirrored_poly_indices:
        return []

    uv_layer = mesh.uv_layers.active or mesh.uv_layers[0]
    uv_data = uv_layer.data
    modified_loops: List[int] = []

    for poly_idx in mirrored_poly_indices:
        poly = mesh.polygons[poly_idx]
        for loop_idx in poly.loop_indices:
            u, v = uv_data[loop_idx].uv
            uv_data[loop_idx].uv = (u + offset_u, v)
            modified_loops.append(loop_idx)

    return modified_loops


def restore_mirrored_uv_faces(
    mesh: bpy.types.Mesh, modified_loops: List[int], offset_u: float = 1.0
) -> None:
    """Restore previously shifted UV coordinates by subtracting offset_u."""
    if not mesh or not mesh.uv_layers or not modified_loops:
        return

    uv_layer = mesh.uv_layers.active or mesh.uv_layers[0]
    uv_data = uv_layer.data

    for loop_idx in modified_loops:
        if loop_idx < len(uv_data):
            u, v = uv_data[loop_idx].uv
            uv_data[loop_idx].uv = (u - offset_u, v)
