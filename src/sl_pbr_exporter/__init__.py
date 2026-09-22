"""Second Life glTF 2.0 PBR Material Exporter.

Seamlessly compatible with Blender 3.6 LTS through Blender 4.2+ & 5.x Extensions.
"""

bl_info = {
    "name": "Second Life PBR Exporter",
    "author": "Antigravity",
    "version": (0, 1, 0),
    "blender": (3, 6, 0),
    "location": "View3D > Sidebar > SL PBR",
    "description": "Automated node inspection, Cycles baking, NumPy ORM packing, and Second Life glTF PBR material export",
    "warning": "",
    "doc_url": "https://github.com/GeneralKakyoin/sl-pbr-exporter",
    "tracker_url": "https://github.com/GeneralKakyoin/sl-pbr-exporter/issues",
    "category": "Import-Export",
}

import importlib
import sys

# Support live reloading of submodules in Blender via F3 -> Reload Scripts
_submodules = [
    "config",
    "utils.context",
    "utils.uv",
    "core.inspector",
    "core.packer",
    "core.baker",
    "core.exporter",
    "ui.panels",
    "ui.operators",
]

if "bpy" in locals():
    for submod in _submodules:
        mod_name = f"{__name__}.{submod}"
        if mod_name in sys.modules:
            importlib.reload(sys.modules[mod_name])

import bpy
from bpy.props import PointerProperty

from .ui.operators import SLPBR_OT_ExportModal, SLPBR_OT_InspectMaterial
from .ui.panels import SLPBR_PT_MainPanel, SLPBR_SceneProperties

classes = (
    SLPBR_SceneProperties,
    SLPBR_OT_InspectMaterial,
    SLPBR_OT_ExportModal,
    SLPBR_PT_MainPanel,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.sl_pbr = PointerProperty(type=SLPBR_SceneProperties)


def unregister():
    if hasattr(bpy.types.Scene, "sl_pbr"):
        del bpy.types.Scene.sl_pbr
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
