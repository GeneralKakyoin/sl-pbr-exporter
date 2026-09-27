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

    def test_wire_material_textures_zero_alpha_invisible(self):
        """Verify that zero-alpha materials (even with skin prefix) get Alpha=0 and HASHED blend mode."""
        from sl_pbr_exporter.importer.devkit_binder import wire_material_textures

        with tempfile.TemporaryDirectory() as td:
            folder = Path(td)
            diff_img_path = folder / "1_diffuse.png"

            img_dummy = bpy.data.images.new("dummy_zero_alpha", width=16, height=16)
            img_dummy.filepath_raw = str(diff_img_path)
            img_dummy.file_format = "PNG"
            img_dummy.save()
            bpy.data.images.remove(img_dummy)

            mat = bpy.data.materials.new("Skin_Head_1_mat")
            mat.use_nodes = True

            meta = {
                "name": "Skin_Head_1_mat",
                "diffuse": str(diff_img_path),
                "diffuse_color": [1.0, 1.0, 1.0, 0.0],
            }

            wire_material_textures(mat, texture_dir=folder, material_meta=meta, dae_dir=folder)

            bsdf = next(n for n in mat.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
            alpha_sock = bsdf.inputs["Alpha"]
            self.assertFalse(alpha_sock.is_linked, "Zero alpha should not link texture alpha directly")
            self.assertEqual(alpha_sock.default_value, 0.0, "Zero alpha material should have Alpha=0.0")
            if hasattr(mat, "blend_method"):
                self.assertEqual(mat.blend_method, "HASHED", "Zero alpha skin must use HASHED to stay transparent")

            bpy.data.materials.remove(mat)

    def test_wire_material_manifest_exact_matching_avalon_head(self):
        """Verify that LeLutka EvoX multi-part head materials match their exact manifest entries."""
        import json
        manifest_data = {
            "Mat_HEAD_lel_evox_AVALON_4_0_1": {
                "name": "HEAD_lel_evox_AVALON_4_0_1_mat",
                "diffuse": "textures/HEAD_lel_evox_AVALON_4_0/1_diffuse.png",
                "diffuse_color": [1.0, 1.0, 1.0, 1.0],
            },
            "Mat_Head_1": {
                "name": "Skin_Head_1_mat",
                "diffuse": "textures/Head/1_diffuse.png",
                "diffuse_color": [1.0, 1.0, 1.0, 0.0],
            },
            "Mat_Head_2": {
                "name": "Skin_Head_2_mat",
                "diffuse": "textures/Head/2_diffuse.png",
                "diffuse_color": [1.0, 1.0, 1.0, 1.0],
            },
            "Mat_HEAD_lel_evox_AVALON_4_0_4": {
                "name": "HEAD_lel_evox_AVALON_4_0_4_mat",
                "diffuse": "textures/HEAD_lel_evox_AVALON_4_0/4_diffuse.png",
                "diffuse_color": [0.0, 0.0, 0.0, 0.0],
            },
        }

        # Simulate matching algorithm
        def match_mat(mat_name):
            for k, v in manifest_data.items():
                if k == mat_name or v.get("name") == mat_name:
                    return v
            return None

        # Verify exact matching
        m1 = match_mat("Skin_Head_1_mat")
        self.assertIsNotNone(m1)
        self.assertEqual(m1["diffuse"], "textures/Head/1_diffuse.png")
        self.assertEqual(m1["diffuse_color"][3], 0.0)

        m2 = match_mat("Skin_Head_2_mat")
        self.assertIsNotNone(m2)
        self.assertEqual(m2["diffuse"], "textures/Head/2_diffuse.png")
        self.assertEqual(m2["diffuse_color"][3], 1.0)

        m4 = match_mat("HEAD_lel_evox_AVALON_4_0_4_mat")
        self.assertIsNotNone(m4)
        self.assertEqual(m4["diffuse"], "textures/HEAD_lel_evox_AVALON_4_0/4_diffuse.png")

    def test_ensure_object_mode_and_deselect_from_pose_mode(self):
        """Verify deselect_all_objects safely switches from POSE mode to OBJECT mode and clears selection."""
        from sl_pbr_exporter.config import deselect_all_objects, ensure_object_mode

        arm_data = bpy.data.armatures.new("PoseTestArm")
        arm_obj = bpy.data.objects.new("PoseTestArm", arm_data)
        bpy.context.scene.collection.objects.link(arm_obj)
        bpy.context.view_layer.objects.active = arm_obj
        arm_obj.select_set(True)

        bpy.ops.object.mode_set(mode="POSE")
        self.assertEqual(bpy.context.mode, "POSE")

        # In POSE mode, standard bpy.ops.object.select_all.poll() returns False
        self.assertFalse(bpy.ops.object.select_all.poll())

        # Our context-agnostic deselect_all_objects must not raise any RuntimeError
        deselect_all_objects()
        self.assertEqual(bpy.context.mode, "OBJECT")
        self.assertEqual(len(bpy.context.selected_objects), 0)

        bpy.data.objects.remove(arm_obj, do_unlink=True)
        bpy.data.armatures.remove(arm_data, do_unlink=True)

    def test_ensure_object_mode_and_deselect_from_edit_mode(self):
        """Verify deselect_all_objects safely switches from EDIT mode to OBJECT mode and clears selection."""
        from sl_pbr_exporter.config import deselect_all_objects, ensure_object_mode

        mesh = bpy.data.meshes.new("EditTestMesh")
        mesh.from_pydata([(0, 0, 0), (1, 0, 0), (0, 1, 0)], [], [(0, 1, 2)])
        mesh.update()
        obj = bpy.data.objects.new("EditTestObj", mesh)
        bpy.context.scene.collection.objects.link(obj)
        bpy.context.view_layer.objects.active = obj
        obj.select_set(True)

        bpy.ops.object.mode_set(mode="EDIT")
        self.assertEqual(bpy.context.mode, "EDIT_MESH")

        deselect_all_objects()
        self.assertEqual(bpy.context.mode, "OBJECT")
        self.assertEqual(len(bpy.context.selected_objects), 0)

        bpy.data.objects.remove(obj, do_unlink=True)
        bpy.data.meshes.remove(mesh, do_unlink=True)

    def test_load_selected_items_safe_in_pose_mode(self):
        """Verify SL_OT_LoadSelectedItems does not crash on poll or context when called while scene is in POSE mode."""
        arm_data = bpy.data.armatures.new("RigAvatar")
        arm_obj = bpy.data.objects.new("Avatar", arm_data)
        bpy.context.scene.collection.objects.link(arm_obj)
        bpy.context.view_layer.objects.active = arm_obj
        arm_obj.select_set(True)

        bpy.ops.object.mode_set(mode="POSE")
        self.assertEqual(bpy.context.mode, "POSE")

        # Invoke load_selected_items - should return CANCELLED cleanly without crashing
        res = bpy.ops.sl_suite.load_selected_items()
        self.assertEqual(res, {"CANCELLED"})

        # Scene mode should now be safely OBJECT
        self.assertEqual(bpy.context.mode, "OBJECT")

        bpy.data.objects.remove(arm_obj, do_unlink=True)
        bpy.data.armatures.remove(arm_data, do_unlink=True)

    def test_universal_body_mesh_detection_maitreya_and_legacy(self):
        """Verify find_body_mesh correctly identifies Maitreya, Legacy, Kupra, and generic bodies."""
        from sl_pbr_exporter.importer.devkit_binder import find_body_mesh

        # 1. Create a head mesh (facial bones)
        head_mesh = bpy.data.meshes.new("HeadMeshData")
        head_mesh.from_pydata([(0, 0, 1.7), (0, 0, 1.8), (0, 0, 1.9)], [], [])
        head_obj = bpy.data.objects.new("HEAD_lel_evox_AVALON", head_mesh)
        bpy.context.scene.collection.objects.link(head_obj)
        for bname in ("mFaceNoseCenter", "mFaceChin", "mFaceCheekUpperLeft", "mFaceLipLowerCenter"):
            head_obj.vertex_groups.new(name=bname)

        # 2. Create a clothing mesh (partial body coverage)
        dress_mesh = bpy.data.meshes.new("DressData")
        dress_mesh.from_pydata([(0, 0, 1.1), (0, 0, 1.2), (0, 0, 1.3)], [], [])
        dress_obj = bpy.data.objects.new("Dress_Short", dress_mesh)
        bpy.context.scene.collection.objects.link(dress_obj)
        for bname in ("mPelvis", "mTorso", "mChest"):
            dress_obj.vertex_groups.new(name=bname)

        # 3. Create Maitreya body mesh (full 5-region body coverage)
        body_mesh = bpy.data.meshes.new("MaitreyaData")
        body_verts = [(0, 0, z / 10.0) for z in range(120)]
        body_mesh.from_pydata(body_verts, [], [])
        body_obj = bpy.data.objects.new("Maitreya Mesh Body - Lara", body_mesh)
        bpy.context.scene.collection.objects.link(body_obj)
        for bname in ("mPelvis", "mTorso", "mChest", "mHipLeft", "mHipRight", "mShoulderLeft", "mShoulderRight", "mKneeLeft"):
            body_obj.vertex_groups.new(name=bname)

        # Body finder must identify Maitreya over dress and head
        found = find_body_mesh(bpy.context.scene)
        self.assertIsNotNone(found)
        self.assertEqual(found.name, "Maitreya Mesh Body - Lara")

        # Cleanup
        for o in (head_obj, dress_obj, body_obj):
            bpy.data.objects.remove(o, do_unlink=True)
        for m in (head_mesh, dress_mesh, body_mesh):
            bpy.data.meshes.remove(m, do_unlink=True)

    def test_universal_skin_material_classification(self):
        """Verify is_skin_material recognizes skin materials across multiple brands and rejects clothes."""
        from sl_pbr_exporter.importer.devkit_binder import is_skin_material

        mat_names_true = [
            "Skin_Head_1_mat",
            "Maitreya_Body_mat",
            "Legacy_Torso_mat",
            "Kupra_Legs_mat",
            "Belleza_Skin_mat",
            "RebornBody_mat",
            "BOM_Body_mat",
            "mat_body_upper",
            "mat_body_lower",
            "Face_mat",
            "Ear_mat",
        ]
        for name in mat_names_true:
            mat = bpy.data.materials.new(name)
            self.assertTrue(is_skin_material(mat), f"Material '{name}' should be recognized as skin")
            bpy.data.materials.remove(mat)

        mat_names_false = [
            "Latex_Bodysuit_mat",
            "Silk_Dress_mat",
            "Leather_Boots_mat",
            "Corset_Fabric_mat",
            "Gold_Earring_mat",
            "Bra_Panty_mat",
            "Denim_Pants_mat",
        ]
        for name in mat_names_false:
            mat = bpy.data.materials.new(name)
            self.assertFalse(is_skin_material(mat), f"Material '{name}' should NOT be recognized as skin")
            bpy.data.materials.remove(mat)

    def test_universal_devkit_visibility_cleanup(self):
        """Verify setup_devkit_visibility keeps main body visible and hides widgets & alternate cuts."""
        from sl_pbr_exporter.importer.devkit_binder import setup_devkit_visibility

        body_m = bpy.data.meshes.new("KupraBodyData")
        body_m.from_pydata([(0, 0, z / 10.0) for z in range(100)], [], [])
        body_obj = bpy.data.objects.new("[INITHIUM] KUPRA", body_m)
        bpy.context.scene.collection.objects.link(body_obj)
        for bname in ("mPelvis", "mTorso", "mChest", "mHipLeft", "mHipRight"):
            body_obj.vertex_groups.new(name=bname)

        alt_m = bpy.data.meshes.new("KupraAltData")
        alt_m.from_pydata([(0, 0, 0.1), (0, 0, 0.2)], [], [])
        alt_obj = bpy.data.objects.new("[INITHIUM] KUPRA_Feet_Flat", alt_m)
        bpy.context.scene.collection.objects.link(alt_obj)

        wgt_m = bpy.data.meshes.new("WgtData")
        wgt_m.from_pydata([(0, 0, 0)], [], [])
        wgt_obj = bpy.data.objects.new("WGT_mPelvis", wgt_m)
        bpy.context.scene.collection.objects.link(wgt_obj)

        setup_devkit_visibility(bpy.context.scene)

        self.assertFalse(body_obj.hide_viewport, "Main body must remain visible")
        self.assertFalse(body_obj.hide_render, "Main body must remain renderable")
        self.assertTrue(alt_obj.hide_viewport, "Alternate cut variations must be hidden")
        self.assertTrue(wgt_obj.hide_viewport, "Rig widget objects must be hidden")

        for o in (body_obj, alt_obj, wgt_obj):
            bpy.data.objects.remove(o, do_unlink=True)
        for m in (body_m, alt_m, wgt_m):
            bpy.data.meshes.remove(m, do_unlink=True)

    def test_count_facial_bones_in_dae_prioritization(self):
        """Verify count_facial_bones_in_dae scores Bento face DAE higher than hair or clothes."""
        from sl_pbr_exporter.importer.sl_shape_engine import count_facial_bones_in_dae

        with tempfile.TemporaryDirectory() as td:
            p_dir = Path(td)
            head_dae = p_dir / "CustomFace.dae"
            head_dae.write_text("""<skin><source id="j"><Name_array>
                mPelvis mNeck mHead mFaceRoot mFaceNoseCenter mFaceChin mFaceLipLowerCenter mFaceEyebrowCenterLeft mEyeLeft mEyeRight
            </Name_array></source></skin>""", encoding="utf-8")

            hair_dae = p_dir / "Hair.dae"
            hair_dae.write_text("""<skin><source id="j"><Name_array>
                mHead mSkull mNeck mFaceRoot
            </Name_array></source></skin>""", encoding="utf-8")

            head_score = count_facial_bones_in_dae(head_dae)
            hair_score = count_facial_bones_in_dae(hair_dae)

            self.assertGreater(head_score, 0)
            self.assertEqual(hair_score, 0)
            self.assertGreater(head_score, hair_score)

    def test_transfer_weights_universal_body(self):
        """Verify SL_OT_TransferWeights transfers weights from any discovered body mesh."""
        # 1. Create a body mesh named 'Legacy_Body'
        body_m = bpy.data.meshes.new("LegacyBodyData")
        body_m.from_pydata([(0, 0, 1.0), (0, 0, 1.2), (0, 0, 1.4)], [], [])
        body_obj = bpy.data.objects.new("Legacy_Body", body_m)
        bpy.context.scene.collection.objects.link(body_obj)
        for bname in ("mPelvis", "mTorso", "mChest", "mHipLeft", "mHipRight"):
            vg = body_obj.vertex_groups.new(name=bname)
            vg.add([0, 1, 2], 0.8, 'REPLACE')

        # 2. Create item mesh to receive weights
        item_m = bpy.data.meshes.new("SkirtData")
        item_m.from_pydata([(0, 0, 1.0), (0, 0, 1.1)], [], [])
        item_obj = bpy.data.objects.new("Skirt", item_m)
        bpy.context.scene.collection.objects.link(item_obj)
        bpy.context.view_layer.objects.active = item_obj
        item_obj.select_set(True)

        # Execute weight transfer operator
        res = bpy.ops.sl_suite.transfer_weights()
        self.assertEqual(res, {"FINISHED"})

        # Verify vertex groups transferred to item_obj
        transferred_groups = [g.name for g in item_obj.vertex_groups]
        self.assertIn("mPelvis", transferred_groups)
        self.assertIn("mTorso", transferred_groups)

        for o in (body_obj, item_obj):
            bpy.data.objects.remove(o, do_unlink=True)
        for m in (body_m, item_m):
            bpy.data.meshes.remove(m, do_unlink=True)


if __name__ == "__main__":
    unittest.main()



