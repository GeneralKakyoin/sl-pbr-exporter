"""Operators and property groups for Mesh and DevKit batch importing, rigging, and weight transfer."""

from pathlib import Path
import re
from typing import Optional
import bpy
from bpy.props import BoolProperty, CollectionProperty, IntProperty, PointerProperty, StringProperty
from bpy.types import Operator, PropertyGroup, UIList

from ..config import DEFAULT_DEVKIT_DIR, DEFAULT_MESH_EXPORT_DIR, get_default_devkit_blend_path
from ..importer.devkit_binder import (
    align_item_to_devkit,
    append_devkit_from_blend,
    get_devkit_armature,
    import_and_bind_item,
)
from ..importer.mesh_resolver import scan_directory_items
from ..importer.shape_loader import apply_shape_xml, find_shape_xml


class SL_ItemChecklistItem(PropertyGroup):
    """Single item entry in the batch checklist."""
    name: StringProperty(name="Name", default="")
    path: StringProperty(name="Path", default="")
    item_type: StringProperty(name="Type", default="DAE")
    textures_dir: StringProperty(name="Textures", default="")
    selected: BoolProperty(name="", description="Check to include in import", default=True)


class SL_UL_ItemsList(UIList):
    """UI list displaying items with checkboxes for batch loading."""

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        row = layout.row(align=True)
        row.prop(item, "selected", text="")
        icon_type = "MESH_DATA" if item.item_type == "DAE" else "FILE_TEXT"
        row.label(text=item.name, icon=icon_type)
        row.label(text=f"({item.item_type})")


def update_scan_folder(self, context):
    """Auto-scan folder when folder path is changed."""
    bpy.ops.sl_suite.scan_items("EXEC_DEFAULT")


class SL_ImporterProperties(PropertyGroup):
    """Properties for Mesh & DevKit importer."""
    folder_path: StringProperty(
        name="Source Folder",
        description="Path to outfit or items folder containing .dae or .xml files",
        subtype="DIR_PATH",
        default=str(DEFAULT_MESH_EXPORT_DIR) if DEFAULT_MESH_EXPORT_DIR.exists() else "",
        update=update_scan_folder,
    )

    devkit_blend_path: StringProperty(
        name="DevKit .blend",
        description="Path to Avastar DevKit .blend file (e.g. eBODY Reborn)",
        subtype="FILE_PATH",
        default=str(get_default_devkit_blend_path() or ""),
    )

    auto_append_devkit: BoolProperty(
        name="Auto-Append DevKit",
        description="Automatically append Avastar rig & body if not already present in the scene",
        default=True,
    )

    apply_shape: BoolProperty(
        name="Apply Shape XML",
        description="Automatically apply avatar shape XML if found in the outfit folder",
        default=True,
    )

    items: CollectionProperty(type=SL_ItemChecklistItem)
    active_item_idx: IntProperty(default=0)
    detected_shape_name: StringProperty(name="Shape", default="")


class SL_OT_ScanItems(Operator):
    """Scan the selected folder for importable items."""
    bl_idname = "sl_suite.scan_items"
    bl_label = "Scan Folder"
    bl_description = "Scan directory for outfit items, .dae files, and Second Life XMLs"

    def execute(self, context):
        props = context.scene.sl_importer
        folder = Path(bpy.path.abspath(props.folder_path.strip())) if props.folder_path else None

        props.items.clear()
        props.detected_shape_name = ""

        if not folder or not folder.exists() or not folder.is_dir():
            self.report({"WARNING"}, "Please select a valid folder.")
            return {"CANCELLED"}

        found = scan_directory_items(folder)
        for entry in found:
            item = props.items.add()
            item.name = entry["name"]
            item.path = entry["path"]
            item.item_type = entry["type"]
            item.textures_dir = entry.get("textures_dir", "")
            item.selected = True

        shape_file = find_shape_xml(folder)
        if shape_file:
            props.detected_shape_name = shape_file.name

        self.report({"INFO"}, f"Found {len(found)} item(s) in folder.")
        return {"FINISHED"}


class SL_OT_SelectAllItems(Operator):
    """Select all items in the checklist."""
    bl_idname = "sl_suite.select_all_items"
    bl_label = "Select All"

    def execute(self, context):
        props = context.scene.sl_importer
        for item in props.items:
            item.selected = True
        return {"FINISHED"}


class SL_OT_DeselectAllItems(Operator):
    """Deselect all items in the checklist."""
    bl_idname = "sl_suite.deselect_all_items"
    bl_label = "Deselect All"

    def execute(self, context):
        props = context.scene.sl_importer
        for item in props.items:
            item.selected = False
        return {"FINISHED"}


class SL_OT_LoadSelectedItems(Operator):
    """Import selected items and bind them onto the Avastar DevKit rig."""
    bl_idname = "sl_suite.load_selected_items"
    bl_label = "Load Selected Items onto DevKit"
    bl_description = "Import checked items, auto-append DevKit if missing, apply shape, and bind to rig"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        props = context.scene.sl_importer
        selected = [it for it in props.items if it.selected]

        if not selected:
            self.report({"WARNING"}, "No items selected. Check at least one item to load.")
            return {"CANCELLED"}

        # 1. Resolve DevKit Armature
        devkit_arm = get_devkit_armature(context.scene)
        if not devkit_arm and props.auto_append_devkit:
            dk_path = Path(bpy.path.abspath(props.devkit_blend_path.strip())) if props.devkit_blend_path else None
            if dk_path and dk_path.exists():
                try:
                    devkit_arm, _ = append_devkit_from_blend(dk_path)
                    self.report({"INFO"}, f"Appended DevKit from {dk_path.name}")
                except Exception as e:
                    self.report({"ERROR"}, f"Failed to append DevKit: {e}")
                    return {"CANCELLED"}

        if not devkit_arm:
            self.report({"ERROR"}, "No DevKit armature found in scene, and could not append one. Please check DevKit path.")
            return {"CANCELLED"}

        # 2. Import and bind checked items
        total_imported_meshes = []
        for item in selected:
            f_path = Path(item.path)
            if not f_path.exists():
                continue

            tex_dir = Path(item.textures_dir) if item.textures_dir else None
            try:
                if item.item_type == "DAE":
                    imported = import_and_bind_item(f_path, devkit_arm=devkit_arm, textures_dir=tex_dir)
                    total_imported_meshes.extend(imported)
            except Exception as e:
                self.report({"ERROR"}, f"Error importing '{item.name}': {e}")

        # 3. Apply Shape XML if requested
        if props.apply_shape:
            folder = Path(bpy.path.abspath(props.folder_path.strip())) if props.folder_path else None
            if folder:
                shape_path = find_shape_xml(folder)
                if shape_path:
                    applied = apply_shape_xml(shape_path, devkit_arm=devkit_arm)
                    if applied:
                        self.report({"INFO"}, f"Applied avatar shape: {shape_path.name}")

        # Select all imported meshes
        bpy.ops.object.select_all(action="DESELECT")
        for m in total_imported_meshes:
            m.select_set(True)
        if total_imported_meshes:
            context.view_layer.objects.active = total_imported_meshes[0]

        self.report({"INFO"}, f"Successfully loaded {len(selected)} item(s) onto '{devkit_arm.name}' rig!")
        return {"FINISHED"}


class SL_OT_TransferWeights(Operator):
    """Transfer / Refit vertex weights from the Reborn body mesh onto the active item."""
    bl_idname = "sl_suite.transfer_weights"
    bl_label = "Transfer Weights from Body"
    bl_description = "Project vertex weights from RebornBody to active item and clamp to 4 weights per vertex"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return (
            context.active_object
            and context.active_object.type == "MESH"
            and context.active_object.name != "RebornBody"
        )

    def execute(self, context):
        active_mesh = context.active_object
        reborn_body = context.scene.objects.get("RebornBody")
        if not reborn_body:
            # Fallback to any body mesh in scene
            for o in context.scene.objects:
                if o.type == "MESH" and "body" in o.name.lower() and o != active_mesh:
                    reborn_body = o
                    break

        if not reborn_body:
            self.report({"ERROR"}, "Source mesh 'RebornBody' not found in current scene.")
            return {"CANCELLED"}

        dt_mod = active_mesh.modifiers.new(name="WeightTransfer", type="DATA_TRANSFER")
        dt_mod.object = reborn_body
        dt_mod.use_vert_data = True
        dt_mod.data_types_verts = {"VGROUP_WEIGHTS"}
        dt_mod.vert_mapping = "NEAREST"

        context.view_layer.objects.active = active_mesh
        bpy.ops.object.modifier_apply(modifier=dt_mod.name)

        # Enforce Second Life 4-weight limit
        bpy.ops.object.vertex_group_limit_total(group_select_mode="ALL", limit=4)
        bpy.ops.object.vertex_group_normalize_all(group_select_mode="ALL")

        self.report({"INFO"}, f"Transferred weights from '{reborn_body.name}' to '{active_mesh.name}' (max 4 weights/vert).")
        return {"FINISHED"}


class SL_OT_AlignToDevkit(Operator):
    """Rotate the selected item -90 degrees around Z to align with the Avastar skeleton."""
    bl_idname = "sl_suite.align_to_devkit"
    bl_label = "Rotate -90° (Align with Body)"
    bl_description = "Rotate mesh -90° around Z to align Second Life coordinates to Avastar"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return context.active_object and context.active_object.type == "MESH"

    def execute(self, context):
        align_item_to_devkit(context.active_object)
        self.report({"INFO"}, f"Rotated '{context.active_object.name}' -90° to align with Avastar.")
        return {"FINISHED"}


class SL_OT_ExportItemDAE(Operator):
    """Export selected item mesh for Second Life using Avastar Collada preset."""
    bl_idname = "sl_suite.export_sl_collada"
    bl_label = "Export Item for SL (.dae)"
    bl_description = "Export selected mesh to .dae ready for Second Life mesh upload"
    bl_options = {"REGISTER"}

    @classmethod
    def poll(cls, context):
        return any(o.type == "MESH" for o in context.selected_objects)

    def execute(self, context):
        devkit_arm = get_devkit_armature(context.scene)
        selected_meshes = [o for o in context.selected_objects if o.type == "MESH"]

        if not selected_meshes:
            self.report({"ERROR"}, "Please select at least one mesh to export.")
            return {"CANCELLED"}

        props = context.scene.sl_importer
        folder = Path(bpy.path.abspath(props.folder_path.strip())) if props.folder_path else Path(bpy.data.filepath).parent
        item_name = selected_meshes[0].name
        clean_name = re.sub(r"[^a-zA-Z0-9_\-]", "_", item_name).strip("_")
        out_file = folder / f"{clean_name}_SL.dae"

        # Ensure max 4 weights per vertex for Second Life upload
        for m in selected_meshes:
            context.view_layer.objects.active = m
            bpy.ops.object.vertex_group_limit_total(group_select_mode="ALL", limit=4)
            bpy.ops.object.vertex_group_normalize_all(group_select_mode="ALL")

        # Select meshes and rig
        bpy.ops.object.select_all(action="DESELECT")
        if devkit_arm:
            devkit_arm.select_set(True)
        for m in selected_meshes:
            m.select_set(True)
        context.view_layer.objects.active = selected_meshes[0]

        try:
            if hasattr(bpy.ops, "avastar") and hasattr(bpy.ops.avastar, "export_sl_collada"):
                bpy.ops.avastar.export_sl_collada("EXEC_DEFAULT", filepath=str(out_file))
            else:
                bpy.ops.wm.collada_export(
                    filepath=str(out_file),
                    selected=True,
                    include_armatures=True,
                    deform_bones_only=True,
                )
            self.report({"INFO"}, f"Exported: {out_file.name} ready for Second Life upload!")
            return {"FINISHED"}
        except Exception as e:
            self.report({"ERROR"}, f"Export failed: {e}")
            return {"CANCELLED"}
