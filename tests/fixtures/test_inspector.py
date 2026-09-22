"""Unit tests for Material Node Tree Inspector."""

import unittest
import bpy

from sl_pbr_exporter.config import (
    PASS_BASE_COLOR,
    PASS_NORMAL,
    PASS_ROUGHNESS,
    get_principled_socket,
    set_material_blend_method,
)
from sl_pbr_exporter.core.inspector import (
    CLASS_COMPLEX_PROCEDURAL,
    CLASS_DIRECT_IMAGE,
    classify_socket_input,
    inspect_material,
)


class TestInspector(unittest.TestCase):

    def setUp(self):
        for m in list(bpy.data.materials):
            bpy.data.materials.remove(m, do_unlink=True)
        for img in list(bpy.data.images):
            bpy.data.images.remove(img, do_unlink=True)

    def create_base_material(self, name: str) -> tuple:
        """Helper to create a fresh node material with Output and Principled BSDF."""
        mat = bpy.data.materials.new(name=name)
        mat.use_nodes = True
        nt = mat.node_tree
        nt.nodes.clear()

        out_node = nt.nodes.new("ShaderNodeOutputMaterial")
        principled = nt.nodes.new("ShaderNodeBsdfPrincipled")
        nt.links.new(principled.outputs["BSDF"], out_node.inputs["Surface"])
        return mat, principled

    def test_direct_image_classification(self):
        """Verify that a simple image texture is classified as DIRECT_IMAGE and does not require diffuse bake."""
        mat, principled = self.create_base_material("Mat_DirectImage")
        nt = mat.node_tree

        img = bpy.data.images.new(name="TestDiffuse", width=64, height=64)
        tex_node = nt.nodes.new("ShaderNodeTexImage")
        tex_node.image = img

        bc_sock = get_principled_socket(principled, "Base Color")
        self.assertIsNotNone(bc_sock)
        nt.links.new(tex_node.outputs["Color"], bc_sock)

        analysis = inspect_material(mat)
        self.assertIn(PASS_BASE_COLOR, analysis.direct_textures)
        self.assertEqual(analysis.direct_textures[PASS_BASE_COLOR], img)
        self.assertNotIn(PASS_BASE_COLOR, analysis.channels_to_bake)

    def test_procedural_noise_requires_bake(self):
        """Verify that procedural noise texture triggers diffuse baking."""
        mat, principled = self.create_base_material("Mat_Procedural")
        nt = mat.node_tree

        noise_node = nt.nodes.new("ShaderNodeTexNoise")
        ramp_node = nt.nodes.new("ShaderNodeValToRGB")
        nt.links.new(noise_node.outputs["Fac"], ramp_node.inputs["Fac"])

        bc_sock = get_principled_socket(principled, "Base Color")
        nt.links.new(ramp_node.outputs["Color"], bc_sock)

        analysis = inspect_material(mat)
        self.assertTrue(analysis.requires_bake)
        self.assertIn(PASS_BASE_COLOR, analysis.channels_to_bake)

    def test_bump_node_requires_normal_bake(self):
        """Verify that ShaderNodeBump triggers normal map baking."""
        mat, principled = self.create_base_material("Mat_Bump")
        nt = mat.node_tree

        bump_node = nt.nodes.new("ShaderNodeBump")
        norm_sock = get_principled_socket(principled, "Normal")
        self.assertIsNotNone(norm_sock)
        nt.links.new(bump_node.outputs["Normal"], norm_sock)

        analysis = inspect_material(mat)
        self.assertTrue(analysis.requires_bake)
        self.assertIn(PASS_NORMAL, analysis.channels_to_bake)

    def test_alpha_mode_detection(self):
        """Verify that material blend modes (CLIP, BLEND) are detected as MASK and BLEND."""
        mat, principled = self.create_base_material("Mat_AlphaClip")
        set_material_blend_method(mat, "CLIP")
        analysis = inspect_material(mat)
        self.assertEqual(analysis.alpha_mode, "MASK")

        set_material_blend_method(mat, "BLEND")
        analysis = inspect_material(mat)
        self.assertEqual(analysis.alpha_mode, "BLEND")


if __name__ == "__main__":
    unittest.main()
