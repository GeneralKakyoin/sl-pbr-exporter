"""Second Life shape XML parser and Avastar shape loader integration."""

from pathlib import Path
from typing import Any, Dict, List, Optional
import xml.etree.ElementTree as ET
import bpy

from ..config import deselect_all_objects, ensure_object_mode


def find_shape_xml(search_dir: Path) -> Optional[Path]:
    """Search for a Second Life shape XML file in the given directory or its parent."""
    if not search_dir.exists():
        return None

    # Check direct directory
    candidates = list(search_dir.glob("*_shape.xml")) + list(search_dir.glob("shape.xml"))
    if candidates:
        return candidates[0]

    # Check parent directory
    if search_dir.parent.exists():
        parent_candidates = list(search_dir.parent.glob("*_shape.xml"))
        if parent_candidates:
            return parent_candidates[0]

    return None


def parse_shape_xml(shape_xml_path: Path) -> Dict[str, Any]:
    """Parse Linden Genepool shape XML into structured slider parameters."""
    if not shape_xml_path.exists():
        return {}

    tree = ET.parse(shape_xml_path)
    root = tree.getroot()

    archetype = root.find("archetype")
    archetype_name = archetype.get("name", "Unknown") if archetype is not None else "Unknown"

    params = {}
    u8_values = {}

    for param in root.iter("param"):
        name = param.get("name")
        display = param.get("display") or name
        val_str = param.get("value")
        u8_str = param.get("u8")

        if name:
            try:
                params[name] = float(val_str) if val_str else 0.0
            except ValueError:
                params[name] = 0.0

            try:
                u8_values[name] = int(u8_str) if u8_str else 0
            except ValueError:
                u8_values[name] = 0

    return {
        "archetype": archetype_name,
        "params": params,
        "u8": u8_values,
        "file": str(shape_xml_path),
    }


from .sl_shape_engine import (
    apply_exact_sl_shape_to_meshes,
    FACIAL_BONE_NAMES,
    BENTO_FACIAL_FEATURE_BONES,
    BODY_TORSO_BONES,
    HEAD_ATTACHMENT_BONES,
)


def apply_shape_xml(
    shape_xml_path: Path,
    devkit_arm: Optional[bpy.types.Object] = None,
    objects: Optional[List[bpy.types.Object]] = None,
) -> bool:
    """Apply a Second Life shape XML to the scene using Avastar for body/armature and the 1:1 SL shape engine for face."""
    if not shape_xml_path.exists():
        return False

    success = False
    delta_neck_z = 0.0

    # 1. If devkit_arm is provided or present, shape the DevKit armature & body with Avastar
    if devkit_arm is None:
        for obj in bpy.context.scene.objects:
            if obj.type == "ARMATURE" and ("avatar" in obj.name.lower() or "avastar" in obj.name.lower()):
                devkit_arm = obj
                break

    if devkit_arm and hasattr(bpy.ops, "avastar") and hasattr(bpy.ops.avastar, "import_shape"):
        try:
            # Find body mesh to protect attached meshes
            body_mesh = bpy.context.scene.objects.get("RebornBody")
            if not body_mesh:
                for o in bpy.context.scene.objects:
                    if o.type == "MESH" and "body" in o.name.lower() and o.data and len(o.data.vertices) > 0:
                        body_mesh = o
                        break

            # Protect attached meshes from Avastar's slider vertex mutation and parenting displacement
            protected_modifiers = []
            protected_parents = []
            for obj in bpy.context.scene.objects:
                if obj == devkit_arm or obj == body_mesh:
                    continue

                if obj.parent == devkit_arm:
                    mw = obj.matrix_world.copy()
                    obj.parent = None
                    obj.matrix_world = mw
                    protected_parents.append((obj, mw))

                if obj.type == "MESH" and obj.modifiers:
                    for mod in obj.modifiers:
                        if mod.type == "ARMATURE" and mod.object == devkit_arm:
                            mod.object = None
                            protected_modifiers.append((mod, devkit_arm))

            # Apply shape to DevKit armature & body via Avastar
            ensure_object_mode()
            deselect_all_objects()
            devkit_arm.select_set(True)
            bpy.context.view_layer.objects.active = devkit_arm
            bpy.ops.avastar.import_shape(filepath=str(shape_xml_path))
            bpy.context.view_layer.update()
            success = True

            # Restore protected modifiers
            for mod, arm in protected_modifiers:
                mod.object = arm

            # Restore protected parents
            for obj, mw in protected_parents:
                obj.parent = devkit_arm
                obj.matrix_world = mw

            # Measure neck vertical offset deterministically from mNeck bone head
            # 1.607073 is Second Life reference Bento height for mNeck
            if devkit_arm.data and "mNeck" in devkit_arm.data.bones:
                delta_neck_z = devkit_arm.data.bones["mNeck"].head_local.z - 1.607073
            elif "mNeck" in devkit_arm.pose.bones:
                delta_neck_z = devkit_arm.pose.bones["mNeck"].head.z - 1.607073
        except Exception as e:
            print(f"[ShapeLoader] Avastar import_shape warning: {e}")

    # 2. Apply exact 1:1 Second Life GPU skinning and bone-scale inversion to facial meshes
    target_meshes = objects if objects is not None else [o for o in bpy.context.scene.objects if o.type == 'MESH']
    deformed_count = apply_exact_sl_shape_to_meshes(
        meshes=target_meshes,
        folder_path=shape_xml_path.parent,
        shape_xml_path=shape_xml_path,
        delta_neck=delta_neck_z,
    )
    if deformed_count > 0:
        success = True

    # 3. Shift hair / head attachments to track neck height
    if abs(delta_neck_z) > 1e-5:
        import mathutils
        for obj in target_meshes:
            if obj.type != "MESH" or not obj.data or not obj.vertex_groups:
                continue
            vnames = {g.index: g.name for g in obj.vertex_groups}
            has_head = any(
                vnames.get(g.group) in HEAD_ATTACHMENT_BONES
                for v in obj.data.vertices for g in v.groups if g.weight > 0.05
            )
            has_facial = any(
                vnames.get(g.group) in BENTO_FACIAL_FEATURE_BONES
                for v in obj.data.vertices for g in v.groups if g.weight > 0.05
            )
            has_body = any(
                vnames.get(g.group) in BODY_TORSO_BONES
                for v in obj.data.vertices for g in v.groups if g.weight > 0.05
            )
            is_facial_mesh = has_facial and not has_body

            if has_head and not is_facial_mesh:
                curr_delta = obj.get("sl_neck_delta_applied", 0.0)
                delta_to_apply = delta_neck_z - curr_delta
                if abs(delta_to_apply) > 1e-5:
                    T = mathutils.Matrix.Translation((0.0, 0.0, delta_to_apply))
                    obj.data.transform(T)
                    obj["sl_neck_delta_applied"] = delta_neck_z
                    obj.data.update()

    # 4. Store slider parameters as custom scene properties
    data = parse_shape_xml(shape_xml_path)
    if data and "params" in data:
        scene = bpy.context.scene
        scene["sl_shape_name"] = data.get("archetype", "Custom")
        for k, v in data["params"].items():
            prop_key = f"sl_shape_{k.replace(' ', '_')}"
            scene[prop_key] = v
        success = True

    return success


