"""N-panel sidebar UI for Second Life PBR Exporter."""

import bpy
from bpy.props import BoolProperty, EnumProperty, FloatProperty, IntProperty, StringProperty
from bpy.types import Panel, PropertyGroup

from ..config import DEFAULT_TEXTURE_RES


class SLPBR_SceneProperties(PropertyGroup):
    """Scene-level properties for PBR export configuration."""

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
        default="//exports/pbr/",
    )

    # Diagnostic inspection cache strings
    diag_material_name: StringProperty(name="Inspected Material", default="")
    diag_status: StringProperty(name="Status", default="Not inspected")
    diag_bakes: StringProperty(name="Required Bakes", default="")
    diag_warnings: StringProperty(name="Warnings", default="")


class SLPBR_PT_MainPanel(Panel):
    """Main Sidebar Panel for Second Life PBR Exporter."""

    bl_label = "Second Life PBR Exporter"
    bl_idname = "SLPBR_PT_main_panel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "SL PBR"

    def draw(self, context):
        layout = self.layout
        props = context.scene.sl_pbr

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
