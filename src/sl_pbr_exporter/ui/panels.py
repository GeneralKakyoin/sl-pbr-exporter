"""Unified N-panel sidebar UI for Second Life Creator Suite (Mesh & DevKit + PBR Exporter)."""

from pathlib import Path
import bpy
from bpy.props import BoolProperty, EnumProperty, FloatProperty, IntProperty, StringProperty
from bpy.types import Panel, PropertyGroup

from ..config import DEFAULT_PBR_EXPORT_DIR, DEFAULT_TEXTURE_RES
from ..importer.devkit_binder import get_devkit_armature


class SLPBR_SceneProperties(PropertyGroup):
    """Scene-level properties for Second Life Creator Suite configuration."""

    active_mode: EnumProperty(
        name="Suite Mode",
        description="Switch between Mesh & DevKit tools and PBR Material Exporter",
        items=[
            ("MESH", "Mesh & DevKit", "Import items, rig onto DevKit, transfer weights", "ARMATURE_DATA", 0),
            ("PBR", "PBR Material Exporter", "Bake, pack ORM, and export glTF PBR materials", "MATERIAL", 1),
        ],
        default="MESH",
    )

    export_target: EnumProperty(
        name="Target",
        description="Choose what to export",
        items=[
            ("BOTH", ".glb & Loose Textures", "Export both glTF material container and loose texture files"),
            ("GLB_ONLY", ".glb Material Only", "Export only the standalone .glb container"),
            ("TEXTURES_ONLY", "Loose Textures Only", "Export only the loose PNG texture maps"),
        ],
        default="BOTH",
    )

    export_scope: EnumProperty(
        name="Scope",
        description="Which materials to process",
        items=[
            ("ACTIVE", "Active Material", "Process active material on the active object"),
            ("SELECTED", "Selected Objects", "Process all materials across selected objects (deduplicated)"),
            ("ALL", "All Scene Materials", "Process all materials in the current blend file"),
        ],
        default="ACTIVE",
    )

    texture_resolution: EnumProperty(
        name="Resolution",
        description="Maximum texture dimension (Second Life hard limit is 2048)",
        items=[
            ("512", "512 x 512", "Low resolution - fast bake, small footprint"),
            ("1024", "1024 x 1024", "Standard resolution - balanced quality"),
            ("2048", "2048 x 2048", "High resolution - Second Life maximum cap"),
        ],
        default="1024",
    )

    bake_samples: IntProperty(
        name="Bake Samples",
        description="Cycles bake sample count per pass",
        default=16,
        min=1,
        max=512,
    )

    bake_ao: BoolProperty(
        name="Bake Cycles AO",
        description="Bake an Ambient Occlusion pass into the Red channel of the ORM map instead of pure white (1.0)",
        default=False,
    )

    offset_mirrored_uvs: BoolProperty(
        name="Offset Mirrored UVs",
        description="Temporarily offset mirrored UV islands (+1.0 in U) during bake to prevent self-overlap seam artifacts",
        default=True,
    )

    invert_normal_green: BoolProperty(
        name="Invert Normal Green (DirectX to OpenGL)",
        description="Invert the Green channel of the Normal map if source textures are DirectX format",
        default=False,
    )

    alpha_mode: EnumProperty(
        name="Alpha Mode",
        description="Second Life glTF transparency mode",
        items=[
            ("AUTO", "Auto Detect", "Detect from Principled BSDF alpha socket and blend mode"),
            ("OPAQUE", "Opaque", "Ignore transparency completely"),
            ("MASK", "Alpha Mask (Cutoff)", "1-bit clip transparency using alpha threshold (no sorting glitches)"),
            ("BLEND", "Alpha Blend", "Continuous transparency for glass, smoke, lace"),
        ],
        default="AUTO",
    )

    alpha_cutoff: FloatProperty(
        name="Alpha Cutoff",
        description="Threshold for Mask transparency",
        default=0.5,
        min=0.0,
        max=1.0,
    )

    output_dir: StringProperty(
        name="Output Directory",
        description="Folder where materials and textures will be written",
        subtype="DIR_PATH",
        default=str(DEFAULT_PBR_EXPORT_DIR),
    )

    # Diagnostic inspection cache strings
    diag_material_name: StringProperty(name="Inspected Material", default="")
    diag_status: StringProperty(name="Status", default="Not inspected")
    diag_bakes: StringProperty(name="Required Bakes", default="")
    diag_warnings: StringProperty(name="Warnings", default="")


class SLSUITE_PT_MainPanel(Panel):
    """Main Sidebar Panel for Second Life Creator Suite."""

    bl_label = "Second Life Creator Suite"
    bl_idname = "SLSUITE_PT_main_panel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Second Life"

    def draw(self, context):
        layout = self.layout
        props = context.scene.sl_pbr
        importer_props = context.scene.sl_importer

        # Mode Switcher at top
        row_mode = layout.row(align=True)
        row_mode.scale_y = 1.3
        row_mode.prop(props, "active_mode", expand=True)

        layout.separator()

        # ===================================================================
        # MODE 1: MESH & DEVKIT
        # ===================================================================
        if props.active_mode == "MESH":
            # 1. DevKit Status Box
            box_dk = layout.box()
            box_dk.label(text="DevKit Rig Status", icon="OUTLINER_OB_ARMATURE")
            devkit_arm = get_devkit_armature(context.scene)
            if devkit_arm:
                box_dk.label(text=f"Active Rig: {devkit_arm.name}", icon="CHECKMARK")
            else:
                box_dk.label(text="No Rig in Scene (Will Auto-Append)", icon="INFO")

            has_avastar = hasattr(bpy.ops, "avastar")
            av_text = "Avastar Connected" if has_avastar else "Standard Armature"
            box_dk.label(text=av_text, icon="CHECKMARK" if has_avastar else "RADIOBUT_OFF")

            box_dk.prop(importer_props, "devkit_blend_path", text="Kit .blend")
            box_dk.prop(importer_props, "auto_append_devkit")

            # 2. Outfit / Items Loading Box
            box_items = layout.box()
            box_items.label(text="Load Outfit & Items", icon="IMPORT")
            row_folder = box_items.row(align=True)
            row_folder.prop(importer_props, "folder_path", text="Folder")
            row_folder.operator("sl_suite.scan_items", text="", icon="FILE_REFRESH")

            # Checklist of discovered items
            if len(importer_props.items) > 0:
                box_items.label(text=f"Detected Items ({len(importer_props.items)}):")
                box_items.template_list(
                    "SL_UL_ItemsList",
                    "",
                    importer_props,
                    "items",
                    importer_props,
                    "active_item_idx",
                    rows=min(5, len(importer_props.items)),
                )

                row_sel = box_items.row(align=True)
                row_sel.operator("sl_suite.select_all_items", text="Select All", icon="CHECKBOX_HLT")
                row_sel.operator("sl_suite.deselect_all_items", text="Deselect All", icon="CHECKBOX_DEHLT")

            if importer_props.detected_shape_name:
                row_shape = box_items.row()
                row_shape.label(text=f"Shape: {importer_props.detected_shape_name}", icon="USER")
                row_shape.prop(importer_props, "apply_shape", text="Apply")

            row_load = box_items.row()
            row_load.scale_y = 1.4
            row_load.operator("sl_suite.load_selected_items", text="Load Selected onto DevKit", icon="IMPORT")

            # 3. Fitting & Weight Tools
            box_fit = layout.box()
            box_fit.label(text="Fitting & Weight Tools", icon="WHEEL")
            box_fit.operator("sl_suite.align_to_devkit", text="Rotate -90° (Align with Body)", icon="DRIVER_ROTATIONAL_DIFFERENCE")
            box_fit.operator("sl_suite.transfer_weights", text="Transfer Weights from Body", icon="MOD_VERTEX_WEIGHT")

            # 4. Collada Export Box
            box_exp = layout.box()
            box_exp.label(text="Export for Second Life", icon="EXPORT")
            box_exp.operator("sl_suite.export_sl_collada", text="Export Item for SL (.dae)", icon="EXPORT")

        # ===================================================================
        # MODE 2: PBR MATERIAL EXPORTER
        # ===================================================================
        elif props.active_mode == "PBR":
            # Target & Scope
            box_targets = layout.box()
            box_targets.label(text="Export Setup", icon="EXPORT")
            box_targets.prop(props, "export_target")
            box_targets.prop(props, "export_scope")
            box_targets.prop(props, "output_dir")

            # Texture & Bake Settings
            box_settings = layout.box()
            box_settings.label(text="Bake & Resolution", icon="TEXTURE")
            box_settings.prop(props, "texture_resolution")
            box_settings.prop(props, "bake_samples")
            box_settings.prop(props, "bake_ao")
            box_settings.prop(props, "offset_mirrored_uvs")

            # Material Standards
            box_mat = layout.box()
            box_mat.label(text="PBR Standards", icon="MATERIAL")
            box_mat.prop(props, "invert_normal_green")
            box_mat.prop(props, "alpha_mode")
            if props.alpha_mode in ("MASK", "AUTO"):
                box_mat.prop(props, "alpha_cutoff")

            # Diagnostics & Pre-flight
            box_diag = layout.box()
            row = box_diag.row()
            row.label(text="Pre-Flight Diagnostics", icon="INFO")
            row.operator("sl_pbr.inspect_material", text="Inspect", icon="VIEWZOOM")

            if props.diag_material_name:
                box_diag.label(text=f"Material: {props.diag_material_name}")
                box_diag.label(text=f"Pipeline: {props.diag_status}")
                if props.diag_bakes:
                    box_diag.label(text=f"Bake Passes: {props.diag_bakes}")
                if props.diag_warnings:
                    box_diag.label(text=f"Warning: {props.diag_warnings}", icon="ERROR")

            # Export Action Button
            layout.separator()
            row_exec = layout.row()
            row_exec.scale_y = 1.6
            row_exec.operator("sl_pbr.export_modal", text="Export to Second Life PBR", icon="RESTRICT_RENDER_OFF")
