"""Context managers for safe scene state preservation and temporary material lifecycles."""

from typing import Generator, List, Optional
import bpy


class PreserveRenderSettings:
    """Context manager to guarantee scene render settings, engine, samples, and selection

    are faithfully restored even if baking encounters an unhandled error or crashes.
    """

    def __init__(self, scene: bpy.types.Scene, context: Optional[bpy.types.Context] = None):
        self.scene = scene
        self.context = context or bpy.context

        # Cached properties
        self._engine: str = scene.render.engine
        self._cycles_device: Optional[str] = None
        self._cycles_samples: Optional[int] = None
        self._bake_type: Optional[str] = None
        self._use_pass_direct: Optional[bool] = None
        self._use_pass_indirect: Optional[bool] = None
        self._use_pass_color: Optional[bool] = None
        self._bake_margin: Optional[int] = None
        self._active_obj: Optional[bpy.types.Object] = None
        self._selected_objs: List[bpy.types.Object] = []

    def __enter__(self) -> "PreserveRenderSettings":
        # Cache Cycles-specific settings if present
        if hasattr(self.scene, "cycles"):
            try:
                self._cycles_device = self.scene.cycles.device
                self._cycles_samples = self.scene.cycles.samples
                self._bake_type = self.scene.cycles.bake_type
            except AttributeError:
                pass

        # Cache Bake settings
        if hasattr(self.scene.render, "bake"):
            bake = self.scene.render.bake
            self._use_pass_direct = getattr(bake, "use_pass_direct", None)
            self._use_pass_indirect = getattr(bake, "use_pass_indirect", None)
            self._use_pass_color = getattr(bake, "use_pass_color", None)
            self._bake_margin = getattr(bake, "margin", None)

        # Cache Selection
        try:
            self._active_obj = self.context.view_layer.objects.active
            self._selected_objs = list(self.context.selected_objects)
        except Exception:
            pass

        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        # Restore Render Engine
        try:
            self.scene.render.engine = self._engine
        except Exception:
            pass

        # Restore Cycles settings
        if hasattr(self.scene, "cycles"):
            try:
                if self._cycles_device is not None:
                    self.scene.cycles.device = self._cycles_device
                if self._cycles_samples is not None:
                    self.scene.cycles.samples = self._cycles_samples
                if self._bake_type is not None:
                    self.scene.cycles.bake_type = self._bake_type
            except Exception:
                pass

        # Restore Bake settings
        if hasattr(self.scene.render, "bake"):
            bake = self.scene.render.bake
            try:
                if self._use_pass_direct is not None:
                    bake.use_pass_direct = self._use_pass_direct
                if self._use_pass_indirect is not None:
                    bake.use_pass_indirect = self._use_pass_indirect
                if self._use_pass_color is not None:
                    bake.use_pass_color = self._use_pass_color
                if self._bake_margin is not None:
                    bake.margin = self._bake_margin
            except Exception:
                pass

        # Restore Selection
        try:
            if self.context and hasattr(self.context, "view_layer"):
                for obj in self.context.selected_objects:
                    obj.select_set(False)
                for obj in self._selected_objs:
                    if obj and obj.name in self.scene.objects:
                        obj.select_set(True)
                if self._active_obj and self._active_obj.name in self.scene.objects:
                    self.context.view_layer.objects.active = self._active_obj
        except Exception:
            pass


class TemporaryBakeMaterial:
    """Creates a deep copy of a material to run bake operations on without mutating

    the artist's original shader node tree, and safely removes the copy on exit.
    """

    def __init__(self, original_material: bpy.types.Material):
        self.original_material = original_material
        self.temp_material: Optional[bpy.types.Material] = None

    def __enter__(self) -> bpy.types.Material:
        if not self.original_material:
            raise ValueError("No material provided to TemporaryBakeMaterial")

        # Duplicate material
        self.temp_material = self.original_material.copy()
        self.temp_material.name = f"__temp_bake_{self.original_material.name}"
        return self.temp_material

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        if self.temp_material:
            try:
                bpy.data.materials.remove(self.temp_material, do_unlink=True)
            except Exception:
                pass
            self.temp_material = None
