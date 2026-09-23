"""Unit tests for Mesh & DevKit Importer, coordinate alignment, and shape XML parsing."""

from pathlib import Path
import tempfile
import unittest
import bpy

from sl_pbr_exporter.importer.devkit_binder import align_item_to_devkit, get_devkit_armature
from sl_pbr_exporter.importer.mesh_resolver import scan_directory_items
from sl_pbr_exporter.importer.shape_loader import parse_shape_xml


class TestImporter(unittest.TestCase):

    def setUp(self):
        for obj in list(bpy.data.objects):
            bpy.data.objects.remove(obj, do_unlink=True)
        for mesh in list(bpy.data.meshes):
            bpy.data.meshes.remove(mesh, do_unlink=True)
        for arm in list(bpy.data.armatures):
            bpy.data.armatures.remove(arm, do_unlink=True)

    def test_coordinate_alignment_rotation(self):
        """Verify that align_item_to_devkit rotates a mesh -90 degrees around Z,

        converting +X forward in Second Life to -Y forward in Blender/Avastar.
        """
        mesh = bpy.data.meshes.new("TestMesh")
        obj = bpy.data.objects.new("TestObj", mesh)
        bpy.context.scene.collection.objects.link(obj)

        # Point at (1.0, 0.0, 0.0)
        verts = [(1.0, 0.0, 0.0)]
        mesh.from_pydata(verts, [], [])
        mesh.update()

        align_item_to_devkit(obj)

        # After -90 deg Z rotation, (1, 0, 0) -> (0, -1, 0)
        v = mesh.vertices[0].co
        self.assertAlmostEqual(v.x, 0.0, places=3, msg="X should rotate to ~0")
        self.assertAlmostEqual(v.y, -1.0, places=3, msg="Y should rotate to -1.0")
        self.assertAlmostEqual(v.z, 0.0, places=3, msg="Z should remain 0")

    def test_devkit_armature_discovery(self):
        """Verify that get_devkit_armature locates the 'Avatar' rig in the scene."""
        arm_data = bpy.data.armatures.new("AvatarData")
        arm_obj = bpy.data.objects.new("Avatar", arm_data)
        bpy.context.scene.collection.objects.link(arm_obj)

        found = get_devkit_armature(bpy.context.scene)
        self.assertIsNotNone(found)
        self.assertEqual(found.name, "Avatar")

    def test_shape_xml_parsing(self):
        """Verify parsing of Linden Genepool shape XML sliders."""
        xml_content = """<?xml version="1.0" encoding="US-ASCII" standalone="yes"?>
<linden_genepool version="1.0">
    <archetype name="TestAvatar">
        <param id="33" name="height" display="Height" value="-0.350" u8="110"/>
        <param id="105" name="breast size" display="Breast Size" value="0.500" u8="128"/>
        <param id="37" name="hip width" display="Hip Width" value="0.400" u8="153"/>
    </archetype>
</linden_genepool>
"""
        with tempfile.NamedTemporaryFile("w", suffix="_shape.xml", delete=False, encoding="utf-8") as tf:
            tf.write(xml_content)
            temp_path = Path(tf.name)

        try:
            data = parse_shape_xml(temp_path)
            self.assertEqual(data["archetype"], "TestAvatar")
            self.assertIn("breast size", data["params"])
            self.assertAlmostEqual(data["params"]["breast size"], 0.500, places=3)
            self.assertEqual(data["u8"]["breast size"], 128)
            self.assertAlmostEqual(data["params"]["hip width"], 0.400, places=3)
        finally:
            temp_path.unlink(missing_ok=True)

    def test_directory_item_scanning(self):
        """Verify scanning of folder containing .dae and .xml items."""
        with tempfile.TemporaryDirectory() as td:
            folder = Path(td)
            (folder / "Shirt.dae").touch()
            (folder / "Pants.dae").touch()
            (folder / "Test_combined.dae").touch()  # Should be skipped
            (folder / "Boots.xml").touch()
            (folder / "Avatar_shape.xml").touch()  # Should be skipped

            items = scan_directory_items(folder)
            names = [it["name"] for it in items]

            self.assertIn("Shirt", names)
            self.assertIn("Pants", names)
            self.assertIn("Boots", names)
            self.assertNotIn("Test_combined", names)
            self.assertNotIn("Avatar_shape", names)


if __name__ == "__main__":
    unittest.main()
