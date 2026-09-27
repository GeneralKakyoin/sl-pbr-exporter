"""
Unit tests for sl_shape_engine: Second Life avatar shape deformation and bone scale inversion.
"""

from pathlib import Path
import tempfile
import unittest
import numpy as np
import bpy

from sl_pbr_exporter.importer.sl_shape_engine import (
    SL_SKELETON_HIERARCHY,
    parse_shape_xml_bones,
    parse_dae_skin_info,
    compute_shaped_skeleton,
    apply_exact_sl_shape_to_meshes,
    apply_exact_sl_shape_to_rigged_hair,
    is_rigged_hair_or_attachment,
    should_shield_from_avastar,
)


class TestShapeEngine(unittest.TestCase):
    """Test suite for SL shape deformation math and bone scale inversion."""

    def test_skeleton_hierarchy_completeness(self):
        """Verify that standard SL skeleton hierarchy contains critical joints."""
        self.assertIn('mPelvis', SL_SKELETON_HIERARCHY)
        self.assertIn('mNeck', SL_SKELETON_HIERARCHY)
        self.assertIn('mHead', SL_SKELETON_HIERARCHY)
        self.assertIn('mFaceRoot', SL_SKELETON_HIERARCHY)
        self.assertIn('mFaceNoseCenter', SL_SKELETON_HIERARCHY)
        self.assertIn('mFaceChin', SL_SKELETON_HIERARCHY)

        # Verify parent chain of nose center
        parent, _ = SL_SKELETON_HIERARCHY['mFaceNoseCenter']
        self.assertEqual(parent, 'mFaceRoot')
        parent_root, _ = SL_SKELETON_HIERARCHY['mFaceRoot']
        self.assertEqual(parent_root, 'mHead')
        parent_head, _ = SL_SKELETON_HIERARCHY['mHead']
        self.assertEqual(parent_head, 'mNeck')

    def test_parse_shape_xml_bones(self):
        """Verify parsing of bone positions and scales from shape XML."""
        xml_content = """<?xml version="1.0" encoding="UTF-8"?>
<linden_genepool version="1.0">
    <archetype name="TestShape">
        <bone name="mFaceNoseCenter" position="0.104730 0.000000 -0.000604" scale="1.268499 1.181750 0.843000"/>
        <bone name="mNeck" position="-0.010000 0.000000 0.251000" scale="0.810670 0.786210 0.854000"/>
    </archetype>
</linden_genepool>"""

        with tempfile.NamedTemporaryFile("w", suffix="_shape.xml", delete=False) as f:
            f.write(xml_content)
            temp_path = Path(f.name)

        try:
            bones = parse_shape_xml_bones(temp_path)
            self.assertIn("mFaceNoseCenter", bones)
            self.assertIn("mNeck", bones)

            nose_scale = bones["mFaceNoseCenter"]["scale"]
            np.testing.assert_allclose(nose_scale, [1.268499, 1.181750, 0.843000], rtol=1e-5)

            neck_pos = bones["mNeck"]["pos"]
            np.testing.assert_allclose(neck_pos, [-0.010, 0.0, 0.251], rtol=1e-5)
        finally:
            if temp_path.exists():
                temp_path.unlink()

    def test_bone_scale_inversion_math(self):
        """
        Verify that effective scale S_eff = S_shape / S_bind correctly inverts
        the creator's oversized baked bind scale.
        """
        shape_bones = {
            'mFaceNoseCenter': {
                'scale': np.array([1.2685, 1.1818, 0.8430], dtype=np.float32),
                'pos': np.array([0.1047, 0.0, -0.0006], dtype=np.float32),
            },
            'mNeck': {
                'scale': np.array([0.8107, 0.7862, 0.8540], dtype=np.float32),
                'pos': np.array([-0.01, 0.0, 0.251], dtype=np.float32),
            },
        }

        # Mock LeLutka Kaya bind scales: nose was sculpted at 1.70x width
        dae_skin_info = {
            'bind_scales': {
                'mFaceNoseCenter': np.array([1.5780, 1.6972, 1.2105], dtype=np.float32),
                'mNeck': np.array([1.0, 1.0, 1.0], dtype=np.float32),
            },
            'bind_world_pos': {
                'mFaceNoseCenter': np.array([0.1026, 0.0, 1.7267], dtype=np.float32),
                'mNeck': np.array([-0.0249, 0.0, 1.6071], dtype=np.float32),
            },
        }

        eff_scales, shaped_pos = compute_shaped_skeleton(shape_bones, dae_skin_info, anchor_bone='mNeck')

        # Effective nose width must shrink to ~0.6963 (30.4% narrower than raw sculpt)
        eff_nose_width = eff_scales['mFaceNoseCenter'][1]
        expected_width = 1.1818 / 1.6972
        self.assertAlmostEqual(eff_nose_width, expected_width, places=3)
        self.assertLess(eff_nose_width, 1.0)

    def test_apply_sl_shape_to_mesh(self):
        """Verify that apply_exact_sl_shape_to_meshes creates SL_Avatar_Shape shape key on a Blender mesh."""
        # Create a test cube mesh
        mesh = bpy.data.meshes.new("TestHeadMesh")
        obj = bpy.data.objects.new("TestHeadObj", mesh)
        bpy.context.scene.collection.objects.link(obj)

        import bmesh
        bm = bmesh.new()
        bmesh.ops.create_cube(bm, size=0.2)
        bm.to_mesh(mesh)
        bm.free()

        # Add vertex group for mFaceNoseCenter
        vg = obj.vertex_groups.new(name="mFaceNoseCenter")
        for v in mesh.vertices:
            vg.add([v.index], 1.0, 'REPLACE')

        # Create temporary shape XML and folder
        with tempfile.TemporaryDirectory() as tmpdir:
            folder = Path(tmpdir)
            shape_file = folder / "avatar_shape.xml"
            shape_file.write_text("""<?xml version="1.0" encoding="UTF-8"?>
<linden_genepool version="1.0">
    <archetype name="Test">
        <bone name="mFaceNoseCenter" position="0.10 0.0 0.0" scale="0.70 0.70 0.70"/>
        <bone name="mNeck" position="0.0 0.0 0.25" scale="1.0 1.0 1.0"/>
    </archetype>
</linden_genepool>""")

            count = apply_exact_sl_shape_to_meshes(
                meshes=[obj],
                folder_path=folder,
                shape_xml_path=shape_file,
            )

            self.assertEqual(count, 1)
            self.assertIsNotNone(mesh.shape_keys)
            self.assertIn("Basis", mesh.shape_keys.key_blocks)
            self.assertIn("SL_Avatar_Shape", mesh.shape_keys.key_blocks)

            sk = mesh.shape_keys.key_blocks["SL_Avatar_Shape"]
            self.assertEqual(sk.value, 1.0)

        # Cleanup test object
        bpy.data.objects.remove(obj, do_unlink=True)
        bpy.data.meshes.remove(mesh, do_unlink=True)

    def test_apply_sl_shape_to_avastar_aligned_mesh(self):
        """Verify that apply_exact_sl_shape_to_meshes correctly converts coordinates for Avastar-aligned meshes."""
        mesh = bpy.data.meshes.new("TestAvaHeadMesh")
        obj = bpy.data.objects.new("TestAvaHeadObj", mesh)
        bpy.context.scene.collection.objects.link(obj)

        import bmesh
        bm = bmesh.new()
        bmesh.ops.create_cube(bm, size=0.2)
        bm.to_mesh(mesh)
        bm.free()

        # Tag as aligned to devkit
        obj["sl_aligned_to_devkit"] = True

        # Add vertex group for mFaceNoseCenter
        vg = obj.vertex_groups.new(name="mFaceNoseCenter")
        for v in mesh.vertices:
            vg.add([v.index], 1.0, 'REPLACE')

        with tempfile.TemporaryDirectory() as tmpdir:
            folder = Path(tmpdir)
            shape_file = folder / "avatar_shape.xml"
            shape_file.write_text("""<?xml version="1.0" encoding="UTF-8"?>
<linden_genepool version="1.0">
    <archetype name="Test">
        <bone name="mFaceNoseCenter" position="0.10 0.0 0.0" scale="0.70 0.70 0.70"/>
        <bone name="mNeck" position="0.0 0.0 0.25" scale="1.0 1.0 1.0"/>
    </archetype>
</linden_genepool>""")

            count = apply_exact_sl_shape_to_meshes(
                meshes=[obj],
                folder_path=folder,
                shape_xml_path=shape_file,
            )

            self.assertEqual(count, 1)
            self.assertIsNotNone(mesh.shape_keys)
            self.assertIn("SL_Avatar_Shape", mesh.shape_keys.key_blocks)
            sk = mesh.shape_keys.key_blocks["SL_Avatar_Shape"]
            self.assertEqual(sk.value, 1.0)

        bpy.data.objects.remove(obj, do_unlink=True)
        bpy.data.meshes.remove(mesh, do_unlink=True)

    def test_apply_sl_shape_with_delta_neck(self):
        """Verify that delta_neck offset shifts deformed vertices along Z to match shaped neck."""
        mesh = bpy.data.meshes.new("TestNeckMesh")
        obj = bpy.data.objects.new("TestNeckObj", mesh)
        bpy.context.scene.collection.objects.link(obj)

        import bmesh
        bm = bmesh.new()
        bmesh.ops.create_cube(bm, size=0.2)
        bm.to_mesh(mesh)
        bm.free()

        vg = obj.vertex_groups.new(name="mFaceNoseCenter")
        for v in mesh.vertices:
            vg.add([v.index], 1.0, 'REPLACE')

        with tempfile.TemporaryDirectory() as tmpdir:
            folder = Path(tmpdir)
            shape_file = folder / "avatar_shape.xml"
            shape_file.write_text("""<?xml version="1.0" encoding="UTF-8"?>
<linden_genepool version="1.0">
    <archetype name="Test">
        <bone name="mFaceNoseCenter" position="0.10 0.0 0.0" scale="1.0 1.0 1.0"/>
        <bone name="mNeck" position="0.0 0.0 0.25" scale="1.0 1.0 1.0"/>
    </archetype>
</linden_genepool>""")

            # Apply without delta_neck first
            apply_exact_sl_shape_to_meshes(
                meshes=[obj],
                folder_path=folder,
                shape_xml_path=shape_file,
                delta_neck=0.0,
            )
            sk0 = [p.co.copy() for p in mesh.shape_keys.key_blocks["SL_Avatar_Shape"].data]

            # Apply with delta_neck = -0.05
            count = apply_exact_sl_shape_to_meshes(
                meshes=[obj],
                folder_path=folder,
                shape_xml_path=shape_file,
                delta_neck=-0.05,
            )

            self.assertEqual(count, 1)
            sk1 = [p.co.copy() for p in mesh.shape_keys.key_blocks["SL_Avatar_Shape"].data]

            # Verify all shape key coordinates were lowered by exactly 0.05 along Z
            for p0, p1 in zip(sk0, sk1):
                self.assertAlmostEqual(p0.z - p1.z, 0.05, places=4)

        bpy.data.objects.remove(obj, do_unlink=True)
        bpy.data.meshes.remove(mesh, do_unlink=True)

    def test_hair_and_body_exclusion_from_facial_shape(self):
        """Verify that hair (weighted to mFaceRoot or UPPER_BACK) and body meshes are excluded from SL_Avatar_Shape."""
        import bmesh

        # Mesh 1: Hair mesh weighted to mFaceRoot only
        hair_mesh = bpy.data.meshes.new("TestHairMesh")
        hair_obj = bpy.data.objects.new("TestHairObj", hair_mesh)
        bpy.context.scene.collection.objects.link(hair_obj)
        bm = bmesh.new()
        bmesh.ops.create_cube(bm, size=0.2)
        bm.to_mesh(hair_mesh)
        bm.free()
        vg_root = hair_obj.vertex_groups.new(name="mFaceRoot")
        for v in hair_mesh.vertices:
            vg_root.add([v.index], 1.0, 'REPLACE')

        # Mesh 2: Body mesh weighted to mChest and UPPER_BACK
        body_mesh = bpy.data.meshes.new("TestBodyMesh")
        body_obj = bpy.data.objects.new("TestBodyObj", body_mesh)
        bpy.context.scene.collection.objects.link(body_obj)
        bm2 = bmesh.new()
        bmesh.ops.create_cube(bm2, size=0.2)
        bm2.to_mesh(body_mesh)
        bm2.free()
        vg_chest = body_obj.vertex_groups.new(name="mChest")
        vg_back = body_obj.vertex_groups.new(name="UPPER_BACK")
        for v in body_mesh.vertices:
            vg_chest.add([v.index], 0.5, 'REPLACE')
            vg_back.add([v.index], 0.5, 'REPLACE')

        with tempfile.TemporaryDirectory() as tmpdir:
            folder = Path(tmpdir)
            shape_file = folder / "avatar_shape.xml"
            shape_file.write_text("""<?xml version="1.0" encoding="UTF-8"?>
<linden_genepool version="1.0">
    <archetype name="Test">
        <bone name="mFaceNoseCenter" position="0.10 0.0 0.0" scale="0.70 0.70 0.70"/>
        <bone name="mNeck" position="0.0 0.0 0.25" scale="1.0 1.0 1.0"/>
    </archetype>
</linden_genepool>""")

            count = apply_exact_sl_shape_to_meshes(
                meshes=[hair_obj, body_obj],
                folder_path=folder,
                shape_xml_path=shape_file,
            )
            # Neither hair nor body should be deformed
            self.assertEqual(count, 0)
            self.assertIsNone(hair_mesh.shape_keys)
            self.assertIsNone(body_mesh.shape_keys)

        bpy.data.objects.remove(hair_obj, do_unlink=True)
        bpy.data.meshes.remove(hair_mesh, do_unlink=True)
        bpy.data.objects.remove(body_obj, do_unlink=True)
        bpy.data.meshes.remove(body_mesh, do_unlink=True)

    def test_neck_anchor_preserves_horizontal_coordinates(self):
        """Verify that mNeck anchor vertices preserve horizontal (X, Y) coordinates without pinching distortion."""
        import bmesh
        mesh = bpy.data.meshes.new("TestNeckAnchorMesh")
        obj = bpy.data.objects.new("TestNeckAnchorObj", mesh)
        bpy.context.scene.collection.objects.link(obj)

        bm = bmesh.new()
        bmesh.ops.create_cube(bm, size=0.2)
        bm.to_mesh(mesh)
        bm.free()

        # Qualify as a facial mesh with mFaceJaw on the last vertex, and mNeck on the others
        vg_neck = obj.vertex_groups.new(name="mNeck")
        vg_jaw = obj.vertex_groups.new(name="mFaceJaw")
        for idx, v in enumerate(mesh.vertices):
            if idx == len(mesh.vertices) - 1:
                vg_jaw.add([v.index], 1.0, 'REPLACE')
            else:
                vg_neck.add([v.index], 1.0, 'REPLACE')

        with tempfile.TemporaryDirectory() as tmpdir:
            folder = Path(tmpdir)
            shape_file = folder / "avatar_shape.xml"
            # Neck scaled down in XML, but anchor vertices should preserve horizontal geometry
            shape_file.write_text("""<?xml version="1.0" encoding="UTF-8"?>
<linden_genepool version="1.0">
    <archetype name="Test">
        <bone name="mNeck" position="-0.01 0.0 0.251" scale="0.75 0.80 1.0"/>
        <bone name="mFaceJaw" position="0.0 0.0 0.0" scale="1.0 1.0 1.0"/>
    </archetype>
</linden_genepool>""")

            count = apply_exact_sl_shape_to_meshes(
                meshes=[obj],
                folder_path=folder,
                shape_xml_path=shape_file,
                delta_neck=-0.05,
            )
            self.assertEqual(count, 1)
            sk = mesh.shape_keys.key_blocks["SL_Avatar_Shape"]
            # Verify that X and Y coordinates of mNeck vertices scale horizontally by s_eff around neck anchor,
            # and Z shifts by delta_neck
            for idx in range(len(mesh.vertices) - 1):
                orig_v = mesh.vertices[idx]
                sk_v = sk.data[idx]
                # In SL space (for non-aligned test obj: X forward, Y left, Z up)
                # dx = orig_v.x - (-0.0249), dy = orig_v.y - 0.0
                expected_x = -0.024875 + 0.75 * (orig_v.co.x - (-0.024875))
                expected_y = 0.80 * orig_v.co.y
                self.assertAlmostEqual(sk_v.co.x, expected_x, places=4)
                self.assertAlmostEqual(sk_v.co.y, expected_y, places=4)
                self.assertAlmostEqual(sk_v.co.z - orig_v.co.z, -0.05, places=4)

        bpy.data.objects.remove(obj, do_unlink=True)
        bpy.data.meshes.remove(mesh, do_unlink=True)

    def test_is_rigged_hair_or_attachment_classification(self):
        """Verify that rigged hair is recognized, while unrigged meshes and facial meshes are excluded."""
        import bmesh

        # 1. Unrigged mesh (0 vertex groups)
        unrigged_mesh = bpy.data.meshes.new("UnriggedMesh")
        unrigged_obj = bpy.data.objects.new("UnriggedObj", unrigged_mesh)
        bpy.context.scene.collection.objects.link(unrigged_obj)
        bm = bmesh.new()
        bmesh.ops.create_cube(bm, size=0.1)
        bm.to_mesh(unrigged_mesh)
        bm.free()

        self.assertFalse(is_rigged_hair_or_attachment(unrigged_obj))

        # 2. Bento facial mesh (has mFaceNoseCenter)
        face_mesh = bpy.data.meshes.new("FaceMesh")
        face_obj = bpy.data.objects.new("FaceObj", face_mesh)
        bpy.context.scene.collection.objects.link(face_obj)
        bm = bmesh.new()
        bmesh.ops.create_cube(bm, size=0.1)
        bm.to_mesh(face_mesh)
        bm.free()
        vg_face = face_obj.vertex_groups.new(name="mFaceNoseCenter")
        vg_face.add([0], 1.0, 'REPLACE')

        self.assertFalse(is_rigged_hair_or_attachment(face_obj))

        # 3. Rigged hair mesh (weighted to HEAD and mHead, no facial bones)
        hair_mesh = bpy.data.meshes.new("HairMesh")
        hair_obj = bpy.data.objects.new("HairObj", hair_mesh)
        bpy.context.scene.collection.objects.link(hair_obj)
        bm = bmesh.new()
        bmesh.ops.create_cube(bm, size=0.1)
        bm.to_mesh(hair_mesh)
        bm.free()
        vg_head = hair_obj.vertex_groups.new(name="HEAD")
        vg_head.add([0], 1.0, 'REPLACE')

        self.assertTrue(is_rigged_hair_or_attachment(hair_obj))

        # Clean up
        for o, m in [(unrigged_obj, unrigged_mesh), (face_obj, face_mesh), (hair_obj, hair_mesh)]:
            bpy.data.objects.remove(o, do_unlink=True)
            bpy.data.meshes.remove(m, do_unlink=True)

    def test_apply_exact_sl_shape_to_rigged_hair(self):
        """Verify that rigged hair is deformed using exact bone position and scale, while unrigged is untouched."""
        import bmesh

        # Create rigged hair cube at head level (Z = 1.75)
        hair_mesh = bpy.data.meshes.new("HairMesh")
        hair_obj = bpy.data.objects.new("HairObj", hair_mesh)
        bpy.context.scene.collection.objects.link(hair_obj)
        bm = bmesh.new()
        bmesh.ops.create_cube(bm, size=0.1)
        for v in bm.verts:
            v.co.z += 1.75
        bm.to_mesh(hair_mesh)
        bm.free()
        vg = hair_obj.vertex_groups.new(name="HEAD")
        for v in hair_mesh.vertices:
            vg.add([v.index], 1.0, 'REPLACE')

        # Create unrigged accessory cube
        unrigged_mesh = bpy.data.meshes.new("UnriggedMesh")
        unrigged_obj = bpy.data.objects.new("UnriggedObj", unrigged_mesh)
        bpy.context.scene.collection.objects.link(unrigged_obj)
        bm2 = bmesh.new()
        bmesh.ops.create_cube(bm2, size=0.1)
        bm2.to_mesh(unrigged_mesh)
        bm2.free()

        # Create mock armature with HEAD bone lowered to 1.58 (as on shaped avatar)
        arm_data = bpy.data.armatures.new("MockAvatar")
        arm_obj = bpy.data.objects.new("MockAvatar", arm_data)
        bpy.context.scene.collection.objects.link(arm_obj)
        bpy.context.view_layer.objects.active = arm_obj
        bpy.ops.object.mode_set(mode='EDIT')
        b = arm_data.edit_bones.new("HEAD")
        b.head = (0.0, 0.0051, 1.5822)
        b.tail = (0.0, 0.0051, 1.6822)
        bpy.ops.object.mode_set(mode='OBJECT')

        shape_bones = {
            'mHead': {'scale': np.array([0.89, 0.89, 0.89], dtype=np.float32), 'pos': np.zeros(3, dtype=np.float32)}
        }

        count = apply_exact_sl_shape_to_rigged_hair(
            meshes=[hair_obj, unrigged_obj],
            devkit_arm=arm_obj,
            shape_bones=shape_bones,
        )

        # Only rigged hair should be deformed
        self.assertEqual(count, 1)
        self.assertIsNotNone(hair_mesh.shape_keys)
        self.assertIn("SL_Avatar_Shape", hair_mesh.shape_keys.key_blocks)
        self.assertIsNone(unrigged_mesh.shape_keys)

        # Verify hair was lowered and scaled down properly (from ~1.75 down to ~1.58)
        sk_head = hair_mesh.shape_keys.key_blocks["SL_Avatar_Shape"]
        for p in sk_head.data:
            self.assertLess(p.co.z, 1.70)
            self.assertGreater(p.co.z, 1.45)

        # Clean up
        for o, m in [(hair_obj, hair_mesh), (unrigged_obj, unrigged_mesh)]:
            bpy.data.objects.remove(o, do_unlink=True)
            bpy.data.meshes.remove(m, do_unlink=True)
        bpy.data.objects.remove(arm_obj, do_unlink=True)
        bpy.data.armatures.remove(arm_data, do_unlink=True)

    def test_should_shield_from_avastar(self):
        """Verify mesh classification for Avastar shape shielding."""
        # Non-mesh or None
        self.assertFalse(should_shield_from_avastar(None))

        # 1. Unrigged mesh (0 vertex groups) -> Shielded (True)
        mesh_unrigged = bpy.data.meshes.new("UnriggedMesh")
        obj_unrigged = bpy.data.objects.new("UnriggedObj", mesh_unrigged)
        mesh_unrigged.from_pydata([(0, 0, 0)], [], [])
        self.assertTrue(should_shield_from_avastar(obj_unrigged))

        # 2. Bento head / facial mesh (weighted to mFaceNoseCenter) -> Shielded (True)
        mesh_bento = bpy.data.meshes.new("BentoMesh")
        obj_bento = bpy.data.objects.new("BentoObj", mesh_bento)
        mesh_bento.from_pydata([(0, 0, 1.7)], [], [])
        vg_bento = obj_bento.vertex_groups.new(name="mFaceNoseCenter")
        vg_bento.add([0], 1.0, 'REPLACE')
        self.assertTrue(should_shield_from_avastar(obj_bento))

        # 3. Rigged hair (weighted to mHead/HEAD, even with chest/upper back contact) -> Shielded (True)
        mesh_hair = bpy.data.meshes.new("HairMesh")
        obj_hair = bpy.data.objects.new("HairObj", mesh_hair)
        mesh_hair.from_pydata([(0, 0, 1.7), (0, 0.1, 1.4)], [], [])
        vg_hair_head = obj_hair.vertex_groups.new(name="mHead")
        vg_hair_head.add([0], 1.0, 'REPLACE')
        vg_hair_back = obj_hair.vertex_groups.new(name="UPPER_BACK")
        vg_hair_back.add([1], 0.5, 'REPLACE')
        self.assertTrue(should_shield_from_avastar(obj_hair))

        # 4. Rigged clothing (catsuit / pants / boots weighted to mPelvis and collision volumes) -> NOT shielded (False)
        mesh_cloth = bpy.data.meshes.new("ClothMesh")
        obj_cloth = bpy.data.objects.new("ClothObj", mesh_cloth)
        mesh_cloth.from_pydata([(0, 0, 1.0)], [], [])
        vg_cloth = obj_cloth.vertex_groups.new(name="mPelvis")
        vg_cloth.add([0], 1.0, 'REPLACE')
        self.assertFalse(should_shield_from_avastar(obj_cloth))

        # 5. Rigged mittens/gloves (weighted to mWristLeft / mHandLeft) -> NOT shielded (False)
        mesh_mitten = bpy.data.meshes.new("MittenMesh")
        obj_mitten = bpy.data.objects.new("MittenObj", mesh_mitten)
        mesh_mitten.from_pydata([(0.5, 0, 1.2)], [], [])
        vg_mitten = obj_mitten.vertex_groups.new(name="mWristLeft")
        vg_mitten.add([0], 1.0, 'REPLACE')
        self.assertFalse(should_shield_from_avastar(obj_mitten))

        # 6. Rigged collar / choker (weighted to mNeck, CHEST, and incidental mFaceJaw) -> NOT shielded (False)
        mesh_collar = bpy.data.meshes.new("CollarMesh")
        obj_collar = bpy.data.objects.new("CollarObj", mesh_collar)
        mesh_collar.from_pydata([(0, 0, 1.6)], [], [])
        vg_collar_neck = obj_collar.vertex_groups.new(name="mNeck")
        vg_collar_neck.add([0], 0.5, 'REPLACE')
        vg_collar_chest = obj_collar.vertex_groups.new(name="CHEST")
        vg_collar_chest.add([0], 0.3, 'REPLACE')
        vg_collar_jaw = obj_collar.vertex_groups.new(name="mFaceJaw")
        vg_collar_jaw.add([0], 0.2, 'REPLACE')
        self.assertFalse(should_shield_from_avastar(obj_collar))

        # Clean up
        for o, m in [
            (obj_unrigged, mesh_unrigged),
            (obj_bento, mesh_bento),
            (obj_hair, mesh_hair),
            (obj_cloth, mesh_cloth),
            (obj_mitten, mesh_mitten),
            (obj_collar, mesh_collar),
        ]:
            bpy.data.objects.remove(o, do_unlink=True)
            bpy.data.meshes.remove(m, do_unlink=True)


if __name__ == "__main__":
    unittest.main()


