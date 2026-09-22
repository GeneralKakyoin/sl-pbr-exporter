"""Unit tests for headless Cycles baking and state preservation."""

import unittest
import bpy

from sl_pbr_exporter.config import PASS_BASE_COLOR, PASS_ROUGHNESS, get_principled_socket
from sl_pbr_exporter.core.baker import BakeSession
from sl_pbr_exporter.core.inspector import inspect_material
from sl_pbr_exporter.utils.context import PreserveRenderSettings, TemporaryBakeMaterial


class TestBaker(unittest.TestCase):

    def setUp(self):
        for mat in list(bpy.data.materials):
            bpy.data.materials.remove(mat, do_unlink=True)
        for obj in list(bpy.data.objects):
            bpy.data.objects.remove(obj, do_unlink=True)
        for mesh in list(bpy.data.meshes):
            bpy.data.meshes.remove(mesh, do_unlink=True)
        for img in list(bpy.data.images):
            bpy.data.images.remove(img, do_unlink=True)

    def create_test_plane(self) -> bpy.types.Object:
        """Create a unit mesh plane with UV coordinates."""
        mesh = bpy.data.meshes.new("TestPlaneMesh")
        obj = bpy.data.objects.new("TestPlaneObj", mesh)
        bpy.context.scene.collection.objects.link(obj)

        verts = [(-1, -1, 0), (1, -1, 0), (1, 1, 0), (-1, 1, 0)]
        faces = [(0, 1, 2, 3)]
        mesh.from_pydata(verts, [], faces)
        mesh.update()

        uv_layer = mesh.uv_layers.new(name="UVMap")
        uvs = [(0, 0), (1, 0), (1, 1), (0, 1)]
        for i, loop in enumerate(mesh.loops):
            uv_layer.data[loop.index].uv = uvs[i]

        return obj

    def test_state_preservation(self):
        """Verify that scene render engine and settings are faithfully restored."""
        scene = bpy.context.scene
        # Determine initial engine
        initial_engine = "BLENDER_EEVEE_NEXT" if "BLENDER_EEVEE_NEXT" in [e.identifier for e in scene.render.bl_rna.properties["engine"].enum_items] else "BLENDER_EEVEE"
        scene.render.engine = initial_engine

        with PreserveRenderSettings(scene):
            scene.render.engine = "CYCLES"
            if hasattr(scene, "cycles"):
                scene.cycles.samples = 1

        self.assertEqual(
            scene.render.engine,
            initial_engine,
            "Scene render engine must be restored after PreserveRenderSettings exit",
        )

    def test_temporary_material_cleanup(self):
        """Verify that TemporaryBakeMaterial removes cloned material from bpy.data.materials."""
        mat = bpy.data.materials.new("UserMaterial")
        initial_mat_count = len(bpy.data.materials)

        with TemporaryBakeMaterial(mat) as temp_mat:
            self.assertEqual(len(bpy.data.materials), initial_mat_count + 1)
            self.assertTrue(temp_mat.name.startswith("__temp_bake_"))

        self.assertEqual(
            len(bpy.data.materials),
            initial_mat_count,
            "Temporary bake material must be removed from bpy.data.materials",
        )

    def test_headless_cycles_bake(self):
        """Verify that emission passthrough bake produces a valid image."""
        obj = self.create_test_plane()

        mat = bpy.data.materials.new("BakeMat")
        mat.use_nodes = True
        nt = mat.node_tree
        nt.nodes.clear()

        out_node = nt.nodes.new("ShaderNodeOutputMaterial")
        principled = nt.nodes.new("ShaderNodeBsdfPrincipled")
        nt.links.new(principled.outputs["BSDF"], out_node.inputs["Surface"])

        rough_sock = get_principled_socket(principled, "Roughness")
        if rough_sock:
            rough_sock.default_value = 0.8

        obj.data.materials.append(mat)
        bpy.context.view_layer.objects.active = obj
        obj.select_set(True)

        analysis = inspect_material(mat, target_object=obj)
        baker = BakeSession(
            material=mat,
            target_object=obj,
            resolution=32,
            bake_samples=1,
            bake_margin=1,
        )

        img = baker.bake_channel(analysis, PASS_ROUGHNESS)
        self.assertIsNotNone(img)
        self.assertEqual(img.size[0], 32)
        self.assertEqual(img.size[1], 32)


if __name__ == "__main__":
    unittest.main()
