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

    def test_wire_material_textures_with_manifest(self):
        """Verify that wire_material_textures correctly uses metadata from *_materials.json."""
        from sl_pbr_exporter.importer.devkit_binder import wire_material_textures

        with tempfile.TemporaryDirectory() as td:
            folder = Path(td)
            diff_img_path = folder / "1_diffuse.png"
            norm_img_path = folder / "1_normal.png"
            orm_img_path = folder / "1_orm.png"

            # Create dummy image files
            img_dummy = bpy.data.images.new("dummy", width=16, height=16)
            img_dummy.filepath_raw = str(diff_img_path)
            img_dummy.file_format = "PNG"
            img_dummy.save()
            img_dummy.filepath_raw = str(norm_img_path)
            img_dummy.save()
            img_dummy.filepath_raw = str(orm_img_path)
            img_dummy.save()
            bpy.data.images.remove(img_dummy)

            mat = bpy.data.materials.new("TestDress_1_mat")
            mat.use_nodes = True

            meta = {
                "name": "TestDress_1_mat",
                "diffuse": str(diff_img_path),
                "normal": str(norm_img_path),
                "orm": str(orm_img_path),
                "diffuse_color": [1.0, 0.8, 0.9, 1.0],
            }

            wire_material_textures(mat, texture_dir=folder, material_meta=meta, dae_dir=folder)

            # Assert node tree links
            bsdf = next(n for n in mat.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
            base_col_sock = bsdf.inputs["Base Color"]
            self.assertTrue(base_col_sock.is_linked, "Base Color should be linked")

            norm_sock = bsdf.inputs["Normal"]
            self.assertTrue(norm_sock.is_linked, "Normal should be linked via Normal Map")

            rough_sock = bsdf.inputs["Roughness"]
            self.assertTrue(rough_sock.is_linked, "Roughness should be linked from ORM")

            metal_sock = bsdf.inputs["Metallic"]
            self.assertTrue(metal_sock.is_linked, "Metallic should be linked from ORM")

            bpy.data.materials.remove(mat)

    def test_wire_material_textures_with_fallback_prefix(self):
        """Verify that wire_material_textures falls back to regex matching (e.g. 2_diffuse.png) without manifest."""
        from sl_pbr_exporter.importer.devkit_binder import wire_material_textures

        with tempfile.TemporaryDirectory() as td:
            folder = Path(td)
            diff_img_path = folder / "2_diffuse.png"

            img_dummy = bpy.data.images.new("dummy2", width=16, height=16)
            img_dummy.filepath_raw = str(diff_img_path)
            img_dummy.file_format = "PNG"
            img_dummy.save()
            bpy.data.images.remove(img_dummy)

            mat = bpy.data.materials.new("Boots_2_mat")
            mat.use_nodes = True

            wire_material_textures(mat, texture_dir=folder, material_meta=None, dae_dir=folder)

            bsdf = next(n for n in mat.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
            base_col_sock = bsdf.inputs["Base Color"]
            self.assertTrue(base_col_sock.is_linked, "Base Color should be linked from 2_diffuse.png")

            bpy.data.materials.remove(mat)


if __name__ == "__main__":
    unittest.main()

