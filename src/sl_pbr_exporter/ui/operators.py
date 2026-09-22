"""Operators for material inspection, batching, and non-blocking modal baking progress."""

from pathlib import Path
from typing import List, Optional, Set
import bpy
from bpy.types import Operator

from ..config import (
    DEFAULT_TEXTURE_RES,
    PASS_AO,
    PASS_BASE_COLOR,
    PASS_EMISSIVE,
    PASS_METALLIC,
    PASS_NORMAL,
    PASS_ROUGHNESS,
)
from ..core.baker import BakeSession
from ..core.exporter import (
    build_synthetic_gltf_material,
    export_standalone_glb,
    save_loose_textures,
)
from ..core.inspector import inspect_material
from ..core.packer import invert_normal_green_channel, pack_orm_image


def get_target_materials(context: bpy.types.Context, scope: str) -> List[tuple]:
    """Retrieve unique (material, associated_object) pairs based on export scope."""
    pairs = []
    seen_materials = set()

    if scope == "ACTIVE":
        obj = context.view_layer.objects.active
        if obj and obj.type == "MESH" and obj.active_material:
            pairs.append((obj.active_material, obj))

    elif scope == "SELECTED":
        for obj in context.selected_objects:
            if obj.type == "MESH":
                for slot in obj.material_slots:
                    if slot.material and slot.material not in seen_materials:
                        seen_materials.add(slot.material)
                        pairs.append((slot.material, obj))

    elif scope == "ALL":
        # Find any mesh object that uses the material, or fallback to active mesh
        active_mesh = context.view_layer.objects.active if context.view_layer.objects.active and context.view_layer.objects.active.type == "MESH" else None
        for mat in bpy.data.materials:
            if mat.use_nodes:
                # Find an object using it
                found_obj = None
                for obj in bpy.data.objects:
                    if obj.type == "MESH" and mat.name in obj.data.materials:
                        found_obj = obj
                        break
                pairs.append((mat, found_obj or active_mesh))

    return pairs


def execute_material_export(
    material: bpy.types.Material,
    target_object: Optional[bpy.types.Object],
    props,
) -> dict:
    """Core synchronous export routine for a single material."""
    res = int(props.texture_resolution)
    out_dir_raw = bpy.path.abspath(props.output_dir)
    out_dir = Path(out_dir_raw) if out_dir_raw else Path.cwd() / "exports" / "pbr"
    mat_folder = out_dir / material.name

    # 1. Inspect
    analysis = inspect_material(
        material=material,
        target_object=target_object,
        bake_ao=props.bake_ao,
        alpha_override=props.alpha_mode,
    )

    # 2. Bake needed channels
    baked_images = {}
    if analysis.requires_bake and target_object:
        baker = BakeSession(
            material=material,
            target_object=target_object,
            resolution=res,
            bake_samples=props.bake_samples,
            offset_mirrored_uvs=props.offset_mirrored_uvs,
        )
        baked_images = baker.run_bakes(analysis)

    # 3. Resolve Pass Images
    # Base Color
    base_color_img = baked_images.get(PASS_BASE_COLOR) or analysis.direct_textures.get(PASS_BASE_COLOR)

    # Roughness
    rough_source = baked_images.get(PASS_ROUGHNESS) or analysis.direct_textures.get(PASS_ROUGHNESS)
    if rough_source is None:
        rough_source = analysis.constant_values.get(PASS_ROUGHNESS, 0.5)

    # Metallic
    metal_source = baked_images.get(PASS_METALLIC) or analysis.direct_textures.get(PASS_METALLIC)
    if metal_source is None:
        metal_source = analysis.constant_values.get(PASS_METALLIC, 0.0)

    # AO
    ao_source = baked_images.get(PASS_AO)

    # Pack ORM
    orm_img = pack_orm_image(
        name=material.name,
        resolution=res,
        ao_source=ao_source,
        roughness_source=rough_source,
        metallic_source=metal_source,
    )

    # Normal
    normal_img = baked_images.get(PASS_NORMAL) or analysis.direct_textures.get(PASS_NORMAL)
    if normal_img and props.invert_normal_green:
        normal_img = invert_normal_green_channel(normal_img)

    # Emissive
    emissive_img = baked_images.get(PASS_EMISSIVE) or analysis.direct_textures.get(PASS_EMISSIVE)

    results = {"material": material.name, "glb": None, "textures": {}}

    # 4. Target A: glTF .glb Material
    if props.export_target in ("BOTH", "GLB_ONLY"):
        synth_mat = build_synthetic_gltf_material(
            name=material.name,
            base_color_img=base_color_img,
            orm_img=orm_img,
            normal_img=normal_img,
            emissive_img=emissive_img,
            alpha_mode=analysis.alpha_mode,
            alpha_cutoff=props.alpha_cutoff,
        )
        glb_file = mat_folder / f"{material.name}.glb"
        export_standalone_glb(material.name, synth_mat, glb_file)
        results["glb"] = glb_file

        # Clean synthetic material
        bpy.data.materials.remove(synth_mat, do_unlink=True)

    # 5. Target B: Loose Textures
    if props.export_target in ("BOTH", "TEXTURES_ONLY"):
        tex_dir = mat_folder / "textures"
        saved = save_loose_textures(
            material_name=material.name,
            textures_dir=tex_dir,
            base_color_img=base_color_img,
            orm_img=orm_img,
            normal_img=normal_img,
            emissive_img=emissive_img,
        )
        results["textures"] = saved

    return results


class SLPBR_OT_InspectMaterial(Operator):
    """Inspect active material and report Second Life PBR compatibility."""

    bl_idname = "sl_pbr.inspect_material"
    bl_label = "Inspect Material"
    bl_description = "Analyze material node tree and geometry to determine bake requirements"

    def execute(self, context):
        props = context.scene.sl_pbr
        obj = context.view_layer.objects.active
        mat = obj.active_material if (obj and obj.type == "MESH") else None

        if not mat:
            self.report({"WARNING"}, "No active mesh material selected.")
            props.diag_material_name = ""
            props.diag_status = "No active material"
            props.diag_bakes = ""
            props.diag_warnings = "Select a mesh object with an assigned material."
            return {"CANCELLED"}

        analysis = inspect_material(
            material=mat,
            target_object=obj,
            bake_ao=props.bake_ao,
            alpha_override=props.alpha_mode,
        )

        props.diag_material_name = mat.name
        props.diag_status = "Bake Required" if analysis.requires_bake else "Zero-Bake Fast Path"
        props.diag_bakes = ", ".join(sorted(analysis.channels_to_bake)) if analysis.channels_to_bake else "None"
        props.diag_warnings = "; ".join(analysis.warnings) if analysis.warnings else ""

        self.report(
            {"INFO"},
            f"Inspection of '{mat.name}': {props.diag_status} | Passes: {props.diag_bakes}",
        )
        return {"FINISHED"}


class SLPBR_OT_ExportModal(Operator):
    """Export materials to Second Life PBR with non-blocking modal progress."""

    bl_idname = "sl_pbr.export_modal"
    bl_label = "Export Second Life PBR"
    bl_description = "Inspect, bake, pack ORM, and export .glb materials and textures"

    _timer = None
    _queue = []
    _total_items = 0
    _current_idx = 0

    def modal(self, context, event):
        if event.type == "ESC":
            self.cancel(context)
            self.report({"WARNING"}, "PBR Export cancelled by user.")
            return {"CANCELLED"}

        if event.type == "TIMER":
            if not self._queue:
                self.finish(context)
                return {"FINISHED"}

            mat, obj = self._queue.pop(0)
            self._current_idx += 1
            progress = (self._current_idx / self._total_items) * 100

            # Update status message
            msg = f"SL PBR [{self._current_idx}/{self._total_items}] Exporting '{mat.name}' ({progress:.0f}%)..."
            if hasattr(context.workspace, "status_text_set"):
                context.workspace.status_text_set(msg)

            try:
                execute_material_export(mat, obj, context.scene.sl_pbr)
            except Exception as e:
                self.report({"ERROR"}, f"Error exporting '{mat.name}': {str(e)}")

        return {"PASS_THROUGH"}

    def execute(self, context):
        props = context.scene.sl_pbr
        items = get_target_materials(context, props.export_scope)

        if not items:
            self.report({"WARNING"}, "No valid materials found in the selected scope.")
            return {"CANCELLED"}

        # If headless / background execution, run synchronously
        if bpy.app.background:
            for mat, obj in items:
                execute_material_export(mat, obj, props)
            self.report({"INFO"}, f"Successfully exported {len(items)} materials.")
            return {"FINISHED"}

        self._queue = items
        self._total_items = len(items)
        self._current_idx = 0

        wm = context.window_manager
        self._timer = wm.event_timer_add(0.05, window=context.window)
        wm.modal_handler_add(self)
        return {"RUNNING_MODAL"}

    def finish(self, context):
        if self._timer:
            context.window_manager.event_timer_remove(self._timer)
            self._timer = None
        if hasattr(context.workspace, "status_text_set"):
            context.workspace.status_text_set(None)
        self.report({"INFO"}, f"Successfully exported {self._total_items} materials.")

    def cancel(self, context):
        if self._timer:
            context.window_manager.event_timer_remove(self._timer)
            self._timer = None
        if hasattr(context.workspace, "status_text_set"):
            context.workspace.status_text_set(None)
