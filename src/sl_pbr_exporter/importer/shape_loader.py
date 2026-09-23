"""Second Life shape XML parser and Avastar shape loader integration."""

from pathlib import Path
from typing import Any, Dict, Optional
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


def apply_shape_xml(
    shape_xml_path: Path,
    devkit_arm: Optional[bpy.types.Object] = None,
) -> bool:
    """Apply a Second Life shape XML to the scene using Avastar or slider parameters."""
    if not shape_xml_path.exists():
        return False

    # 1. Use Avastar native import_shape operator if available
    if hasattr(bpy.ops, "avastar") and hasattr(bpy.ops.avastar, "import_shape"):
        try:
            # If armature given, select it
            if devkit_arm and devkit_arm.name in bpy.context.scene.objects:
                ensure_object_mode()
                deselect_all_objects()
                devkit_arm.select_set(True)
                bpy.context.view_layer.objects.active = devkit_arm

            bpy.ops.avastar.import_shape(filepath=str(shape_xml_path))
            return True
        except Exception as e:
            print(f"[ShapeLoader] Avastar import_shape warning: {e}")

    # 2. Fallback: Parse and store parameters as custom scene properties
    data = parse_shape_xml(shape_xml_path)
    if data and "params" in data:
        scene = bpy.context.scene
        scene["sl_shape_name"] = data.get("archetype", "Custom")
        for k, v in data["params"].items():
            prop_key = f"sl_shape_{k.replace(' ', '_')}"
            scene[prop_key] = v
        return True

    return False
