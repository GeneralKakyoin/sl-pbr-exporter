"""Automated, state-managed Cycles baking runner using emission passthrough for raw PBR passes."""

from typing import Dict, List, Optional, Set
import bpy

from ..config import (
    COLORSPACE_NON_COLOR,
    COLORSPACE_SRGB,
    PASS_AO,
    PASS_BASE_COLOR,
    PASS_EMISSIVE,
    PASS_METALLIC,
    PASS_NORMAL,
    PASS_ROUGHNESS,
    get_principled_socket,
)
from ..utils.context import PreserveRenderSettings, TemporaryBakeMaterial
from ..utils.uv import offset_mirrored_uv_faces, restore_mirrored_uv_faces
from .inspector import MaterialAnalysis, find_principled_bsdf


class BakeSession:
    """Orchestrates headless Cycles baking for a specific material and target mesh."""

    def __init__(
        self,
        material: bpy.types.Material,
        target_object: bpy.types.Object,
        resolution: int = 1024,
        bake_samples: int = 16,
        bake_margin: int = 4,
        offset_mirrored_uvs: bool = True,
    ):
        self.material = material
        self.target_object = target_object
        self.resolution = resolution
        self.bake_samples = bake_samples
        self.bake_margin = bake_margin
        self.offset_mirrored_uvs = offset_mirrored_uvs

        self.baked_images: Dict[str, bpy.types.Image] = {}

    def _create_bake_image(self, name: str, is_color: bool = True) -> bpy.types.Image:
        """Create a clean 32-bit float RGBA image for baking."""
        image_name = f"__bake_{self.material.name}_{name}"
        # If existing image exists with same name, remove it
        if image_name in bpy.data.images:
            bpy.data.images.remove(bpy.data.images[image_name])

        img = bpy.data.images.new(
            name=image_name,
            width=self.resolution,
            height=self.resolution,
            alpha=True,
            float_buffer=False,
        )
        img.colorspace_settings.name = COLORSPACE_SRGB if is_color else COLORSPACE_NON_COLOR
        return img

    def _setup_bake_node(
        self, node_tree: bpy.types.NodeTree, target_image: bpy.types.Image
    ) -> bpy.types.Node:
        """Add and activate a temporary ShaderNodeTexImage in the node tree for Cycles to bake into."""
        tex_node = node_tree.nodes.new("ShaderNodeTexImage")
        tex_node.name = "__bake_target_node__"
        tex_node.image = target_image
        node_tree.nodes.active = tex_node
        tex_node.select = True
        return tex_node

    def bake_channel(
        self,
        analysis: MaterialAnalysis,
        pass_name: str,
    ) -> Optional[bpy.types.Image]:
        """Bake an individual channel (DIFFUSE, EMIT passthrough for roughness/metallic, NORMAL, AO)."""
        scene = bpy.context.scene

        # Ensure target object is active and selected
        bpy.ops.object.select_all(action="DESELECT")
        self.target_object.select_set(True)
        bpy.context.view_layer.objects.active = self.target_object

        is_color = pass_name in (PASS_BASE_COLOR, PASS_EMISSIVE)
        bake_img = self._create_bake_image(pass_name, is_color=is_color)

        # Handle mirrored UV offsets
        modified_loops = []
        if (
            self.offset_mirrored_uvs
            and self.target_object.type == "MESH"
            and analysis.mirrored_uv_faces_count > 0
        ):
            modified_loops = offset_mirrored_uv_faces(self.target_object.data)

        try:
            with TemporaryBakeMaterial(self.material) as temp_mat:
                # Assign temp material to object slot
                orig_mat = self.target_object.active_material
                self.target_object.active_material = temp_mat

                nt = temp_mat.node_tree
                bake_node = self._setup_bake_node(nt, bake_img)

                # Configure Cycles bake settings
                scene.render.engine = "CYCLES"
                if hasattr(scene, "cycles"):
                    scene.cycles.samples = self.bake_samples
                    # Use GPU if available
                    if bpy.context.preferences.addons.get("cycles"):
                        cprefs = bpy.context.preferences.addons["cycles"].preferences
                        if hasattr(cprefs, "compute_device_type") and cprefs.compute_device_type != "NONE":
                            scene.cycles.device = "GPU"
                        else:
                            scene.cycles.device = "CPU"

                scene.render.bake.margin = self.bake_margin

                principled = find_principled_bsdf(temp_mat)
                out_node = None
                for n in nt.nodes:
                    if n.type == "OUTPUT_MATERIAL":
                        out_node = n
                        break

                if pass_name == PASS_BASE_COLOR:
                    # Diffuse Color only (no direct/indirect lighting)
                    scene.render.bake.use_pass_direct = False
                    scene.render.bake.use_pass_indirect = False
                    scene.render.bake.use_pass_color = True
                    bpy.ops.object.bake(type="DIFFUSE")

                elif pass_name in (PASS_ROUGHNESS, PASS_METALLIC):
                    # Emission passthrough trick
                    if principled and out_node:
                        # Disconnect principled from output
                        for link in list(nt.links):
                            if link.to_node == out_node and link.to_socket.name == "Surface":
                                nt.links.remove(link)

                        emit_node = nt.nodes.new("ShaderNodeEmission")
                        nt.links.new(emit_node.outputs["Emission"], out_node.inputs["Surface"])

                        sock_name = "Roughness" if pass_name == PASS_ROUGHNESS else "Metallic"
                        source_sock = get_principled_socket(principled, sock_name)

                        if source_sock and source_sock.is_linked:
                            # Link input to emission color
                            nt.links.new(source_sock.links[0].from_socket, emit_node.inputs["Color"])
                        elif source_sock:
                            # Scalar constant
                            c_val = getattr(source_sock, "default_value", 0.5 if pass_name == PASS_ROUGHNESS else 0.0)
                            emit_node.inputs["Color"].default_value = (c_val, c_val, c_val, 1.0)

                    bpy.ops.object.bake(type="EMIT")

                elif pass_name == PASS_NORMAL:
                    # Tangent-space OpenGL normal
                    scene.render.bake.normal_space = "TANGENT"
                    bpy.ops.object.bake(type="NORMAL")

                elif pass_name == PASS_AO:
                    bpy.ops.object.bake(type="AO")

                elif pass_name == PASS_EMISSIVE:
                    bpy.ops.object.bake(type="EMIT")

                # Revert material slot on object
                self.target_object.active_material = orig_mat

        finally:
            if modified_loops and self.target_object.type == "MESH":
                restore_mirrored_uv_faces(self.target_object.data, modified_loops)

        self.baked_images[pass_name] = bake_img
        return bake_img

    def run_bakes(
        self,
        analysis: MaterialAnalysis,
        channels_to_bake: Optional[Set[str]] = None,
    ) -> Dict[str, bpy.types.Image]:
        """Execute all required bakes while preserving scene settings."""
        targets = channels_to_bake if channels_to_bake is not None else analysis.channels_to_bake
        if not targets:
            return {}

        with PreserveRenderSettings(bpy.context.scene):
            for channel in targets:
                self.bake_channel(analysis, channel)

        return self.baked_images
