"""Second Life Creator Suite (Mesh & DevKit Importer + PBR Material Exporter).

Seamlessly compatible with Blender 3.6 LTS through Blender 4.2+ & 5.x Extensions.
"""

bl_info = {
    "name": "Second Life Creator Suite (Mesh & PBR)",
    "author": "Antigravity & GeneralKakyoin",
    "version": (0, 2, 0),
    "blender": (3, 6, 0),
    "location": "View3D > Sidebar > Second Life",
    "description": "Unified Second Life suite: Mesh & DevKit batch loader, Avastar auto-binding, shape XML, and PBR Material Exporter",
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
    "importer.devkit_binder",
    "importer.shape_loader",
    "importer.mesh_resolver",
    "ui.importer_operators",
    "ui.operators",
    "ui.panels",
]

if "bpy" in locals():
    for submod in _submodules:
        mod_name = f"{__name__}.{submod}"
        if mod_name in sys.modules:
            importlib.reload(sys.modules[mod_name])

import bpy
from bpy.props import PointerProperty

from .ui.importer_operators import (
    SL_ItemChecklistItem,
    SL_ImporterProperties,
    SL_OT_AlignToDevkit,
    SL_OT_DeselectAllItems,
    SL_OT_ExportItemDAE,
    SL_OT_LoadSelectedItems,
    SL_OT_ScanItems,
    SL_OT_SelectAllItems,
    SL_OT_TransferWeights,
    SL_UL_ItemsList,
)
from .ui.operators import SLPBR_OT_ExportModal, SLPBR_OT_InspectMaterial
from .ui.panels import SLPBR_SceneProperties, SLSUITE_PT_MainPanel

classes = (
    SL_ItemChecklistItem,
    SL_UL_ItemsList,
    SL_ImporterProperties,
    SLPBR_SceneProperties,
    SL_OT_ScanItems,
    SL_OT_SelectAllItems,
    SL_OT_DeselectAllItems,
    SL_OT_LoadSelectedItems,
    SL_OT_TransferWeights,
    SL_OT_AlignToDevkit,
    SL_OT_ExportItemDAE,
    SLPBR_OT_InspectMaterial,
    SLPBR_OT_ExportModal,
    SLSUITE_PT_MainPanel,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.sl_pbr = PointerProperty(type=SLPBR_SceneProperties)
    bpy.types.Scene.sl_importer = PointerProperty(type=SL_ImporterProperties)


def unregister():
    if hasattr(bpy.types.Scene, "sl_importer"):
        del bpy.types.Scene.sl_importer
    if hasattr(bpy.types.Scene, "sl_pbr"):
        del bpy.types.Scene.sl_pbr
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
