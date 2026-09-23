import os
from pathlib import Path
from typing import Optional
import bpy

# Dynamic User Paths (decoupled from any hardcoded username)
DOCUMENTS_DIR = Path.home() / "Documents"
DEFAULT_SL_DOCS_DIR = DOCUMENTS_DIR / "SecondLife"
DEFAULT_DEVKIT_DIR = DEFAULT_SL_DOCS_DIR / "Kits"
DEFAULT_MESH_EXPORT_DIR = DEFAULT_SL_DOCS_DIR / "Exports" / "Mesh"
DEFAULT_PBR_EXPORT_DIR = DEFAULT_SL_DOCS_DIR / "Exports" / "PBR"

_local_appdata = os.environ.get("LOCALAPPDATA", "")
DEFAULT_FIRESTORM_CACHE = Path(_local_appdata) / "FirestormOS_x64" if _local_appdata else Path.home() / "AppData" / "Local" / "FirestormOS_x64"
DEFAULT_FIRESTORM_XML_DIR = Path(_local_appdata) / "Temp" / "Firestorm_MeshExport" if _local_appdata else Path.home() / "AppData" / "Local" / "Temp" / "Firestorm_MeshExport"


def get_default_devkit_blend_path() -> Optional[Path]:
    """Find the best matching Avastar DevKit .blend in the SecondLife/Kits directory."""
    if not DEFAULT_DEVKIT_DIR.exists():
        return None

    blend_files = list(DEFAULT_DEVKIT_DIR.glob("*.blend"))
    if not blend_files:
        return None

    # Version-specific preference
    b_version = bpy.app.version
    if b_version[0] == 3 and b_version[1] == 6:
        for f in blend_files:
            if "3.6" in f.name:
                return f
    elif b_version[0] >= 4:
        for f in blend_files:
            if "5." in f.name or "4." in f.name:
                return f

    # Fallback to the first available kit
    return blend_files[0]

# Second Life Hard Limits and Defaults
MAX_TEXTURE_RES = 2048
DEFAULT_TEXTURE_RES = 1024
SUPPORTED_RESOLUTIONS = (512, 1024, 2048)

# Second Life transparent 1x1 texture UUID
SL_TRANSPARENT_UUID = "8dcd4a48-2d37-4909-9f78-f7a9eb4ef903"

# Colorspace standard enforcers
COLORSPACE_SRGB = "sRGB"
COLORSPACE_NON_COLOR = "Non-Color"

# Pass identifiers
PASS_BASE_COLOR = "BASE_COLOR"
PASS_ROUGHNESS = "ROUGHNESS"
PASS_METALLIC = "METALLIC"
PASS_NORMAL = "NORMAL"
PASS_EMISSIVE = "EMISSIVE"
PASS_AO = "AO"
PASS_ORM = "ORM"

# File name suffixes for loose texture export
SUFFIX_BASE_COLOR = "_BaseColor.png"
SUFFIX_ORM = "_ORM.png"
SUFFIX_NORMAL = "_Normal.png"
SUFFIX_EMISSIVE = "_Emissive.png"

# Principled BSDF socket alias mapping across Blender 3.6 LTS and Blender 4.0+ / 5.x
PRINCIPLED_SOCKET_ALIASES = {
    "Base Color": ["Base Color"],
    "Roughness": ["Roughness"],
    "Metallic": ["Metallic"],
    "Normal": ["Normal"],
    "Alpha": ["Alpha"],
    "Emission": ["Emission Color", "Emission"],
    "Emission Color": ["Emission Color", "Emission"],
    "Emission Strength": ["Emission Strength"],
    "Specular": ["Specular IOR Level", "Specular"],
    "IOR": ["IOR"],
}


def get_blender_version() -> tuple:
    """Return bpy.app.version as a 3-tuple (major, minor, patch)."""
    return bpy.app.version


def get_principled_socket(node: bpy.types.Node, socket_name: str) -> Optional[bpy.types.NodeSocket]:
    """Retrieve an input socket on a Principled BSDF node safely across Blender 3.6 and 4.x/5.x."""
    if not node or not hasattr(node, "inputs"):
        return None

    # Check direct name first
    sock = node.inputs.get(socket_name)
    if sock is not None:
        return sock

    # Check known aliases
    aliases = PRINCIPLED_SOCKET_ALIASES.get(socket_name, [])
    for alias in aliases:
        sock = node.inputs.get(alias)
        if sock is not None:
            return sock

    return None


def get_material_blend_method(mat: bpy.types.Material) -> str:
    """Safely return material blend method across Blender 3.6, 4.x, and 5.x."""
    if not mat:
        return "OPAQUE"
    sl_tag = getattr(mat, "_sl_blend_mode", None) or (mat.get("_sl_blend_mode") if hasattr(mat, "get") else None)
    if sl_tag:
        return str(sl_tag)
    if hasattr(mat, "surface_render_method"):
        if mat.surface_render_method == "BLENDED":
            return "BLEND"
        elif mat.surface_render_method == "DITHERED":
            return "CLIP"
    if hasattr(mat, "blend_method"):
        return str(mat.blend_method)
    return "OPAQUE"


def set_material_blend_method(mat: bpy.types.Material, blend_method: str) -> None:
    """Safely set material blend method across Blender versions."""
    if not mat:
        return
    try:
        mat["_sl_blend_mode"] = blend_method
    except Exception:
        pass
    if hasattr(mat, "surface_render_method"):
        try:
            if blend_method == "CLIP":
                mat.surface_render_method = "DITHERED"
            elif blend_method == "BLEND":
                mat.surface_render_method = "BLENDED"
        except Exception:
            pass
    if hasattr(mat, "blend_method"):
        try:
            mat.blend_method = blend_method
        except (TypeError, ValueError):
            pass
