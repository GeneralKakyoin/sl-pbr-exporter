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


if __name__ == "__main__":
    unittest.main()
