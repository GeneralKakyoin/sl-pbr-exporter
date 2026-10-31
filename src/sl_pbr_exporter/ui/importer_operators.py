"""Operators and property groups for Mesh and DevKit batch importing, rigging, and weight transfer."""

from pathlib import Path
import re
from typing import Optional
import bpy
from bpy.props import (
    BoolProperty,
    CollectionProperty,
    EnumProperty,
    FloatProperty,
    IntProperty,
    PointerProperty,
    StringProperty,
)
from bpy.types import Operator, PropertyGroup, UIList

import mathutils

from ..config import (
    DEFAULT_DEVKIT_DIR,
    DEFAULT_MESH_EXPORT_DIR,
    deselect_all_objects,
    ensure_object_mode,
    get_default_devkit_blend_path,
)
from ..importer.devkit_binder import (
    align_item_to_devkit,
    append_devkit_from_blend,
    find_body_mesh,
    get_devkit_armature,
    hide_inactive_linkset_meshes,
    import_and_bind_item,
    setup_devkit_visibility,
)
from ..importer.mesh_resolver import scan_directory_items
from ..importer.shape_loader import apply_shape_xml, find_shape_xml, parse_shape_xml
from ..importer.sl_shape_engine import (
    apply_exact_sl_shape_to_meshes,
    apply_exact_sl_shape_to_rigged_hair,
    parse_shape_xml_bones,
    should_shield_from_avastar,
    FACIAL_BONE_NAMES,
    BENTO_FACIAL_FEATURE_BONES,
    BODY_TORSO_BONES,
    HEAD_ATTACHMENT_BONES,
)



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


def update_custom_shape_path(self, context):
    """Auto-detect archetype when custom shape XML is updated."""
    p_str = self.custom_shape_path.strip()
    if p_str:
        p = Path(bpy.path.abspath(p_str))
        if p.exists() and p.is_file():
            try:
                data = parse_shape_xml(p)
                if data and "archetype" in data:
                    self.detected_custom_shape_name = data["archetype"]
                else:
                    self.detected_custom_shape_name = p.stem
            except Exception:
                self.detected_custom_shape_name = p.stem
            return
    self.detected_custom_shape_name = ""


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
        description="Path to Avastar DevKit .blend file (optional, for Avastar DevKits)",
        subtype="FILE_PATH",
        default=str(get_default_devkit_blend_path() or ""),
    )

    auto_append_devkit: BoolProperty(
        name="Auto-Append DevKit",
        description="Automatically append Avastar rig if not already present in the scene",
        default=True,
    )

    load_devkit_body: BoolProperty(
        name="Load DevKit Body",
        description="Load the avatar body mesh from the DevKit. Turn off to avoid loading the body mesh and bind items to the armature only",
        default=False,
    )

    use_custom_shape: BoolProperty(
        name="Load with Custom Shape",
        description="Load the DevKit with a custom avatar shape XML instead of the default shape",
        default=False,
    )

    custom_shape_path: StringProperty(
        name="Custom Shape XML",
        description="Path to custom Second Life shape XML file (.xml)",
        subtype="FILE_PATH",
        default="",
        update=update_custom_shape_path,
    )

    detected_custom_shape_name: StringProperty(
        name="Custom Shape",
        default="",
    )

    apply_shape: BoolProperty(
        name="Apply Shape XML",
        description="Automatically apply avatar shape XML if found in the outfit folder",
        default=True,
    )

    weight_transfer_method: EnumProperty(
        name="Weight Transfer Method",
        description="Weight projection method when transferring weights from body to item",
        items=[
            ("POLYINTERP_NEAREST", "Nearest Face Interpolated (Smooth)", "Interpolate smoothly across body faces - prevents tearing, spikes, and separation"),
            ("POLYINTERP_VNORPROJ", "Project Along Normals", "Project ray along vertex normals - ideal for tight wrap items"),
            ("NEAREST", "Nearest Vertex (Stepped)", "Snap to single nearest body vertex"),
        ],
        default="POLYINTERP_NEAREST",
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
    """Import selected items and bind them onto the avatar rig."""
    bl_idname = "sl_suite.load_selected_items"
    bl_label = "Load Selected Items onto DevKit"
    bl_description = "Import checked items, auto-append DevKit if missing, apply shape, and bind to rig"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        ensure_object_mode()
        props = context.scene.sl_importer
        selected = [it for it in props.items if it.selected]

        if not selected:
            self.report({"WARNING"}, "No items selected. Check at least one item to load.")
            return {"CANCELLED"}

        # 1. Resolve DevKit Armature & Body
        devkit_arm = get_devkit_armature(context.scene)
        devkit_body = None
        if not devkit_arm and props.auto_append_devkit:
            dk_path = Path(bpy.path.abspath(props.devkit_blend_path.strip())) if props.devkit_blend_path else None
            if dk_path and dk_path.exists():
                try:
                    devkit_arm, devkit_body = append_devkit_from_blend(
                        dk_path,
                        load_body=props.load_devkit_body,
                    )
                    if props.load_devkit_body:
                        self.report({"INFO"}, f"Appended DevKit rig & body from {dk_path.name}")
                    else:
                        self.report({"INFO"}, f"Appended DevKit armature only from {dk_path.name}")
                except Exception as e:
                    self.report({"WARNING"}, f"Could not append DevKit: {e}")

        # 2. Import and bind all checked items onto the rig
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
                    if not devkit_arm:
                        devkit_arm = get_devkit_armature(context.scene)
            except Exception as e:
                self.report({"ERROR"}, f"Error importing '{item.name}': {e}")

        # Clean devkit visibility (keep primary body visible, hide alternate cuts and widgets)
        if props.load_devkit_body:
            setup_devkit_visibility()
            body_mesh = devkit_body or find_body_mesh(context.scene)
        else:
            body_mesh = None

        # Inactive linkset meshes (< 30 verts or all zero alpha) are auto-hidden by import_and_bind_item,
        # but run explicitly here across all meshes to ensure complete consistency.
        hide_inactive_linkset_meshes(total_imported_meshes)

        # 3. Apply Shape (Hybrid Pipeline)
        shape_path = None
        folder = Path(bpy.path.abspath(props.folder_path.strip())) if props.folder_path else None
        if props.use_custom_shape and props.custom_shape_path:
            custom_p = Path(bpy.path.abspath(props.custom_shape_path.strip()))
            if custom_p.exists() and custom_p.is_file():
                shape_path = custom_p
        if not shape_path and props.apply_shape and folder:
            shape_path = find_shape_xml(folder)

        if shape_path and devkit_arm:
            delta_neck_z = 0.0
            unshaped_neck_z = None
            if body_mesh and body_mesh.data and len(body_mesh.data.vertices) > 0:
                neck_candidates_before = [v.co.z for v in body_mesh.data.vertices if v.co.z > 1.4]
                if neck_candidates_before:
                    unshaped_neck_z = max(neck_candidates_before)

            # Shield Bento facial items, hair, and unrigged meshes from Avastar slider mutation
            protected_meshes = []
            for obj in total_imported_meshes:
                if not obj or obj.type != "MESH":
                    continue
                if should_shield_from_avastar(obj):
                    mw = obj.matrix_world.copy()
                    obj.parent = None
                    obj.matrix_world = mw
                    arm_mod = next((m for m in obj.modifiers if m.type == "ARMATURE"), None)
                    arm_target = arm_mod.object if arm_mod else None
                    if arm_mod:
                        arm_mod.object = None
                    protected_meshes.append((obj, mw, arm_mod, arm_target))

            # Run Avastar body & clothing shape pass: shapes rest bones, RebornBody, and all attached rigged clothing
            if props.load_devkit_body and hasattr(bpy.ops, "avastar") and hasattr(bpy.ops.avastar, "import_shape"):
                try:
                    ensure_object_mode()
                    deselect_all_objects()
                    devkit_arm.select_set(True)
                    context.view_layer.objects.active = devkit_arm
                    bpy.ops.avastar.import_shape(filepath=str(shape_path))
                    context.view_layer.update()
                    self.report({"INFO"}, f"Applied DevKit body & clothing shape: {shape_path.name}")

                    # Measure neck vertical offset directly from body mesh vertex seam (step 423 reference),
                    # with deterministic fallback to mNeck bone head
                    if body_mesh and unshaped_neck_z is not None:
                        neck_candidates_after = [v.co.z for v in body_mesh.data.vertices if v.co.z > 1.4]
                        if neck_candidates_after:
                            delta_neck_z = max(neck_candidates_after) - unshaped_neck_z
                    elif devkit_arm.data and "mNeck" in devkit_arm.data.bones:
                        delta_neck_z = devkit_arm.data.bones["mNeck"].head_local.z - 1.607073
                    elif "mNeck" in devkit_arm.pose.bones:
                        delta_neck_z = devkit_arm.pose.bones["mNeck"].head.z - 1.607073
                except Exception as e:
                    self.report({"WARNING"}, f"DevKit body shape application warning: {e}")

            # Restore shielded meshes
            for obj, mw, arm_mod, arm_target in protected_meshes:
                obj.parent = devkit_arm
                obj.matrix_world = mw
                if arm_mod and arm_target:
                    arm_mod.object = arm_target

            # 4. Apply exact 1:1 SL shape to facial meshes
            selected_daes = [Path(item.path) for item in selected if item.item_type == "DAE" and Path(item.path).exists()]
            applied_count = apply_exact_sl_shape_to_meshes(
                meshes=total_imported_meshes,
                folder_path=folder,
                shape_xml_path=shape_path,
                delta_neck=delta_neck_z,
                dae_files=selected_daes,
            )
            if applied_count > 0:
                self.report({"INFO"}, f"Applied exact SL Bento face shape to {applied_count} mesh(es)")

            # 5. Apply exact 1:1 SL bone shape to rigged hair and head attachments
            shape_bones = parse_shape_xml_bones(shape_path)
            hair_count = apply_exact_sl_shape_to_rigged_hair(
                meshes=total_imported_meshes,
                devkit_arm=devkit_arm,
                shape_bones=shape_bones,
            )
            if hair_count > 0:
                self.report({"INFO"}, f"Applied exact SL bone shape to {hair_count} rigged hair/attachment mesh(es)")

            # Store slider parameters as custom scene properties
            data = parse_shape_xml(shape_path)
            if data and "params" in data:
                scene = context.scene
                scene["sl_shape_name"] = data.get("archetype", "Custom")
                for k, v in data["params"].items():
                    prop_key = f"sl_shape_{k.replace(' ', '_')}"
                    scene[prop_key] = v

        # Select all visible imported meshes
        deselect_all_objects()
        visible_imported = [m for m in total_imported_meshes if not m.hide_viewport]
        for m in visible_imported:
            m.select_set(True)
        if visible_imported:
            context.view_layer.objects.active = visible_imported[0]

        # Switch 3D Viewport shading to Material Preview so materials and textures are visible
        try:
            wm = getattr(context, "window_manager", None)
            if wm:
                for window in wm.windows:
                    for area in window.screen.areas:
                        if area.type == "VIEW_3D":
                            for space in area.spaces:
                                if space.type == "VIEW_3D":
                                    space.shading.type = "MATERIAL"
        except Exception:
            pass

        if not props.load_devkit_body:
            arm_label = f"'{devkit_arm.name}' armature (armature only)" if devkit_arm else "armature only"
        else:
            arm_label = f"'{devkit_arm.name}' rig & body" if devkit_arm else "avatar"
        self.report({"INFO"}, f"Successfully loaded {len(selected)} item(s) onto {arm_label} with textures!")
        return {"FINISHED"}


class SL_OT_ImportDevKit(Operator):
    """Import the DevKit armature and body mesh into the active scene, optionally applying a custom shape."""
    bl_idname = "sl_suite.import_devkit"
    bl_label = "Import DevKit Alone"
    bl_description = "Import DevKit rig (and optional body mesh) into scene, with option to apply a custom shape XML"
    bl_options = {"REGISTER", "UNDO"}

    devkit_blend_path: StringProperty(
        name="DevKit .blend",
        description="Path to DevKit .blend file (leave blank to use configured Kit .blend)",
        default="",
    )
    load_body: BoolProperty(
        name="Load DevKit Body",
        description="Load the avatar body mesh from the DevKit. Turn off for armature only",
        default=True,
    )
    use_custom_shape: BoolProperty(
        name="Load with Custom Shape",
        description="Apply a custom avatar shape XML when loading the DevKit",
        default=False,
    )
    custom_shape_path: StringProperty(
        name="Custom Shape XML",
        description="Path to custom Second Life shape XML file (.xml)",
        default="",
    )

    def execute(self, context):
        ensure_object_mode()
        props = context.scene.sl_importer

        # Determine settings: fallback to scene properties if not explicitly overridden on operator call
        dk_path_str = self.devkit_blend_path.strip() if self.properties.is_property_set("devkit_blend_path") and self.devkit_blend_path else props.devkit_blend_path.strip()
        load_body = self.load_body if self.properties.is_property_set("load_body") else props.load_devkit_body
        use_custom = self.use_custom_shape if self.properties.is_property_set("use_custom_shape") else props.use_custom_shape
        custom_shape_str = self.custom_shape_path.strip() if self.properties.is_property_set("custom_shape_path") and self.custom_shape_path else props.custom_shape_path.strip()

        dk_path = Path(bpy.path.abspath(dk_path_str)) if dk_path_str else None
        if not dk_path or not dk_path.exists():
            self.report({"ERROR"}, f"Please select a valid DevKit .blend file. Current path: '{dk_path_str or 'None'}'")
            return {"CANCELLED"}

        try:
            devkit_arm, devkit_body = append_devkit_from_blend(dk_path, load_body=load_body)
        except Exception as e:
            self.report({"ERROR"}, f"Could not append DevKit: {e}")
            return {"CANCELLED"}

        if not devkit_arm:
            self.report({"ERROR"}, f"No armature found in {dk_path.name}")
            return {"CANCELLED"}

        shape_applied = False
        shape_name = ""
        if use_custom:
            shape_file = None
            if custom_shape_str:
                p = Path(bpy.path.abspath(custom_shape_str))
                if p.exists() and p.is_file():
                    shape_file = p

            # Fallback to folder_path if custom shape not found
            if not shape_file and props.folder_path:
                f = Path(bpy.path.abspath(props.folder_path.strip()))
                if f.exists():
                    shape_file = find_shape_xml(f)

            if shape_file and shape_file.exists():
                shape_name = shape_file.name
                try:
                    apply_shape_xml(shape_file, devkit_arm=devkit_arm)
                    shape_applied = True
                except Exception as e:
                    self.report({"WARNING"}, f"Error applying custom shape: {e}")
            else:
                self.report({"WARNING"}, "Load with Custom Shape is enabled, but no valid shape XML file was found.")

        # Deselect everything and select newly loaded devkit objects
        deselect_all_objects()
        if devkit_arm:
            devkit_arm.select_set(True)
            context.view_layer.objects.active = devkit_arm
        if devkit_body:
            devkit_body.select_set(True)

        try:
            wm = getattr(context, "window_manager", None)
            if wm:
                for window in wm.windows:
                    for area in window.screen.areas:
                        if area.type == "VIEW_3D":
                            for space in area.spaces:
                                if space.type == "VIEW_3D":
                                    space.shading.type = "MATERIAL"
        except Exception:
            pass

        body_desc = f"with body '{devkit_body.name}'" if devkit_body else "(armature only)"
        if shape_applied:
            self.report({"INFO"}, f"Successfully imported DevKit '{devkit_arm.name}' {body_desc} with custom shape '{shape_name}'!")
        else:
            self.report({"INFO"}, f"Successfully imported DevKit '{devkit_arm.name}' {body_desc} (default shape)!")

        return {"FINISHED"}


class SL_OT_CreateArmatureOnlyDevKit(Operator):
    """Extract the armature from the active DevKit .blend and save an Armature-Only .blend file."""
    bl_idname = "sl_suite.create_armature_devkit"
    bl_label = "Create Armature-Only DevKit"
    bl_description = "Extract only the Avatar armature from the configured DevKit .blend and save it as a lightweight armature-only kit"
    bl_options = {"REGISTER"}

    def execute(self, context):
        props = context.scene.sl_importer
        dk_path = Path(bpy.path.abspath(props.devkit_blend_path.strip())) if props.devkit_blend_path else None
        if not dk_path or not dk_path.exists():
            self.report({"ERROR"}, "Valid DevKit .blend path required.")
            return {"CANCELLED"}

        out_path = dk_path.parent / f"{dk_path.stem} - Armature Only.blend"
        try:
            import subprocess
            py_code = (
                "import bpy\n"
                "from pathlib import Path\n"
                f"src = Path(r'{dk_path}')\n"
                f"dst = Path(r'{out_path}')\n"
                "for o in list(bpy.data.objects): bpy.data.objects.remove(o, do_unlink=True)\n"
                "with bpy.data.libraries.load(str(src), link=False) as (df, dt):\n"
                "    if 'Avatar' in df.objects: dt.objects = ['Avatar']\n"
                "    else: dt.objects = [n for n in df.objects if n not in ('Camera', 'Light')]\n"
                "for o in dt.objects:\n"
                "    if o and o.type == 'ARMATURE':\n"
                "        bpy.context.scene.collection.objects.link(o)\n"
                "        break\n"
                "bpy.ops.wm.save_as_mainfile(filepath=str(dst))\n"
            )
            subprocess.run([bpy.app.binary_path, "--background", "--python-expr", py_code], check=True, capture_output=True)
            props.devkit_blend_path = str(out_path)
            props.load_devkit_body = False
            self.report({"INFO"}, f"Created and selected armature-only DevKit: {out_path.name}")
            return {"FINISHED"}
        except Exception as e:
            self.report({"ERROR"}, f"Failed to create armature-only DevKit: {e}")
            return {"CANCELLED"}



class SL_OT_TransferWeights(Operator):
    """Transfer / Refit vertex weights from the avatar body mesh onto the active item."""
    bl_idname = "sl_suite.transfer_weights"
    bl_label = "Transfer Weights from Body"
    bl_description = "Project vertex weights from avatar body mesh to active item and clamp to 4 weights per vertex"
    bl_options = {"REGISTER", "UNDO"}

    mapping_method: EnumProperty(
        name="Method",
        description="Weight transfer algorithm from body to mesh",
        items=[
            ("POLYINTERP_NEAREST", "Nearest Face Interpolated", "Smooth interpolation across body faces (best for clothing/bands)"),
            ("POLYINTERP_VNORPROJ", "Project Along Normals", "Project ray along vertex normals (great for form-fitting shells)"),
            ("NEAREST", "Nearest Vertex", "Copy weights directly from closest body vertex (can cause stepped/jagged deformation)"),
        ],
        default="POLYINTERP_NEAREST",
    )
    clean_threshold: FloatProperty(
        name="Clean Threshold",
        description="Prune tiny residual weights before limiting to 4 bones (prevents wasting SL weight slots)",
        default=0.005,
        min=0.0,
        max=0.05,
    )

    @classmethod
    def poll(cls, context):
        if not context.active_object or context.active_object.type != "MESH":
            return False
        body = find_body_mesh(context.scene)
        return body is not None and context.active_object != body

    def invoke(self, context, event):
        props = getattr(context.scene, "sl_importer", None)
        if props and hasattr(props, "weight_transfer_method"):
            self.mapping_method = props.weight_transfer_method
        return self.execute(context)

    def execute(self, context):
        ensure_object_mode()
        active_mesh = context.active_object
        body = find_body_mesh(context.scene)

        if not body:
            self.report({"ERROR"}, "Avatar body mesh not found in current scene.")
            return {"CANCELLED"}

        # Generate target vertex groups on active mesh if not already present
        for src_group in body.vertex_groups:
            if src_group.name not in active_mesh.vertex_groups:
                active_mesh.vertex_groups.new(name=src_group.name)

        dt_mod = active_mesh.modifiers.new(name="WeightTransfer", type="DATA_TRANSFER")
        dt_mod.object = body
        dt_mod.use_vert_data = True
        dt_mod.data_types_verts = {"VGROUP_WEIGHTS"}
        dt_mod.vert_mapping = self.mapping_method

        context.view_layer.objects.active = active_mesh
        bpy.ops.object.modifier_apply(modifier=dt_mod.name)

        # Enforce Second Life 4-weight limit
        if active_mesh.vertex_groups:
            try:
                if self.clean_threshold > 0:
                    bpy.ops.object.vertex_group_clean(group_select_mode="ALL", limit=self.clean_threshold)
                bpy.ops.object.vertex_group_limit_total(group_select_mode="ALL", limit=4)
                bpy.ops.object.vertex_group_normalize_all(group_select_mode="ALL")
            except Exception as e:
                print(f"[TransferWeights] Warning during cleanup/normalize: {e}")

        self.report({"INFO"}, f"Transferred weights from '{body.name}' ({self.mapping_method}) to '{active_mesh.name}' (max 4 weights/vert).")
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
        ensure_object_mode()
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
        deselect_all_objects()
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
