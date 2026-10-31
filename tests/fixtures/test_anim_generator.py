"""Unit tests for Second Life .anim and .bvh Deformer Animation Generator.

Verifies:
- Byte-accurate .anim v1.0 binary serialization and deserialization
- Float32 to uint16 quantization precision within SL error bounds
- Quaternion compression (LLQuaternion::packToVector3)
- Modular channel isolation (Position, Rotation, Scale independence)
- Symmetrical bilateral joint transformations for Thighs
- Batch generation and manifest integrity
"""

import math
import shutil
import tempfile
import unittest
from pathlib import Path

from sl_pbr_exporter.core.anim_writer import (
    SLAnimWriter,
    euler_deg_to_quat,
    f32_to_u16,
    quat_to_vec3,
    u16_to_f32,
    vec3_to_quat,
)
from sl_pbr_exporter.core.deformer_anim_generator import DeformerAnimGenerator


class TestAnimGenerator(unittest.TestCase):
    """Test suite for Second Life animation generator."""

    def test_quantization_roundtrip(self):
        """Verify float32 quantization to uint16 across SL coordinate domains."""
        # Exact zero preservation
        self.assertEqual(u16_to_f32(f32_to_u16(0.0, -5.0, 5.0), -5.0, 5.0), 0.0)
        self.assertEqual(u16_to_f32(f32_to_u16(0.0, -1.0, 1.0), -1.0, 1.0), 0.0)

        # Boundary values
        self.assertAlmostEqual(u16_to_f32(f32_to_u16(-5.0, -5.0, 5.0), -5.0, 5.0), -5.0, places=3)
        self.assertAlmostEqual(u16_to_f32(f32_to_u16(5.0, -5.0, 5.0), -5.0, 5.0), 5.0, places=3)

        # Typical deformation displacements (1cm to 5cm)
        for offset in [0.005, 0.015, 0.025, -0.010, -0.030]:
            recovered = u16_to_f32(f32_to_u16(offset, -5.0, 5.0), -5.0, 5.0)
            self.assertLess(abs(recovered - offset), 0.0003)

    def test_quaternion_vector3_compression(self):
        """Verify LLQuaternion packToVector3 and unpackFromVector3 roundtrip."""
        angles = [5.0, 15.0, -25.0, 45.0]
        for deg in angles:
            q = euler_deg_to_quat(0.0, 0.0, deg)
            v = quat_to_vec3(*q)
            rec_q = vec3_to_quat(*v)

            # Reconstructed angle from qw
            rec_deg = math.degrees(2.0 * math.acos(max(-1.0, min(1.0, rec_q[3]))))
            self.assertAlmostEqual(abs(deg), rec_deg, places=3)

    def test_anim_binary_roundtrip(self):
        """Verify .anim binary stream serialization matches LLKeyframeMotion::deserialize."""
        joints = [
            {
                "name": "mHipLeft",
                "priority": 5,
                "rot_keys": [],
                "pos_keys": [
                    (0.0, (0.010, 0.020, 0.0)),
                    (0.0666667, (0.010, 0.020, 0.0))
                ]
            },
            {
                "name": "mHipRight",
                "priority": 5,
                "rot_keys": [],
                "pos_keys": [
                    (0.0, (0.010, -0.020, 0.0)),
                    (0.0666667, (0.010, -0.020, 0.0))
                ]
            }
        ]

        raw_anim = SLAnimWriter.serialize_anim(
            joints=joints,
            duration=0.0666667,
            base_priority=5,
            loop=True,
            ease_in=0.0,
            ease_out=0.0
        )

        parsed = SLAnimWriter.deserialize_anim(raw_anim)

        self.assertEqual(parsed["version"], 1)
        self.assertEqual(parsed["sub_version"], 0)
        self.assertEqual(parsed["base_priority"], 5)
        self.assertTrue(parsed["loop"])
        self.assertEqual(parsed["ease_in"], 0.0)
        self.assertEqual(parsed["ease_out"], 0.0)
        self.assertEqual(len(parsed["joints"]), 2)
        self.assertEqual(parsed["joints"][0]["name"], "mHipLeft")
        self.assertEqual(len(parsed["joints"][0]["rot_keys"]), 0)
        self.assertEqual(len(parsed["joints"][0]["pos_keys"]), 2)
        self.assertEqual(parsed["num_constraints"], 0)

        # Check unpacked position accuracy
        p0 = parsed["joints"][0]["pos_keys"][0][1]
        self.assertAlmostEqual(p0[0], 0.010, places=3)
        self.assertAlmostEqual(p0[1], 0.020, places=3)

    def test_modular_channel_isolation(self):
        """Verify Position anims have 0 rot keys and Rotation anims have 0 pos keys."""
        generator = DeformerAnimGenerator(region="thighs", num_steps=2)

        # Position channel
        pos_joints, _ = generator._build_thigh_joints("position", "Y", 0.015)
        self.assertEqual(len(pos_joints), 2)
        for j in pos_joints:
            self.assertEqual(len(j["rot_keys"]), 0, "Position anim must have 0 rotation keys!")
            self.assertEqual(len(j["pos_keys"]), 2, "Position anim must have 2 position keys!")

        # Rotation channel
        rot_joints, _ = generator._build_thigh_joints("rotation", "Z", 10.0)
        self.assertEqual(len(rot_joints), 2)
        for j in rot_joints:
            self.assertEqual(len(j["pos_keys"]), 0, "Rotation anim must have 0 position keys!")
            self.assertEqual(len(j["rot_keys"]), 2, "Rotation anim must have 2 rotation keys!")

    def test_thigh_symmetry_rules(self):
        """Verify bilateral symmetry and mirroring for Thigh transformations."""
        generator = DeformerAnimGenerator(region="thighs", num_steps=2)

        # Lateral thigh gap (Y): Left is +Y, Right is -Y
        pos_y_joints, _ = generator._build_thigh_joints("position", "Y", 0.020)
        left_pos = pos_y_joints[0]["pos_keys"][0][1]
        right_pos = pos_y_joints[1]["pos_keys"][0][1]
        self.assertAlmostEqual(left_pos[1], 0.020)
        self.assertAlmostEqual(right_pos[1], -0.020)

        # Anterior/Posterior (X): Both move +X
        pos_x_joints, _ = generator._build_thigh_joints("position", "X", 0.010)
        self.assertAlmostEqual(pos_x_joints[0]["pos_keys"][0][1][0], 0.010)
        self.assertAlmostEqual(pos_x_joints[1]["pos_keys"][0][1][0], 0.010)

        # Volume expansion: Targets L_UPPER_LEG and R_UPPER_LEG collision bones
        vol_joints, _ = generator._build_thigh_joints("scale", "Vol", 0.010)
        bone_names = {j["name"] for j in vol_joints}
        self.assertEqual(bone_names, {"L_UPPER_LEG", "R_UPPER_LEG"})

        # Length expansion: Targets mKneeLeft and mKneeRight
        len_joints, _ = generator._build_thigh_joints("scale", "Len", 0.015)
        len_bones = {j["name"] for j in len_joints}
        self.assertEqual(len_bones, {"mKneeLeft", "mKneeRight"})
        self.assertAlmostEqual(len_joints[0]["pos_keys"][0][1][2], -0.015)

    def test_bvh_generation(self):
        """Verify standard BVH hierarchy output for rotation channels."""
        bvh_rots = {
            "mHipLeft": (0.0, 0.0, 10.0),
            "mHipRight": (0.0, 0.0, -10.0)
        }
        bvh_text = SLAnimWriter.serialize_bvh(bvh_rots, fps=30.0, num_frames=2)
        self.assertIn("HIERARCHY", bvh_text)
        self.assertIn("ROOT hip", bvh_text)
        self.assertIn("JOINT mHipLeft", bvh_text)
        self.assertIn("JOINT mHipRight", bvh_text)
        self.assertIn("Frames: 2", bvh_text)
        self.assertIn("Frame Time: 0.033333", bvh_text)

    def test_batch_generator_execution(self):
        """Verify full generation pipeline produces all folders, files, and manifest."""
        temp_dir = tempfile.mkdtemp(prefix="sl_anim_test_")
        try:
            generator = DeformerAnimGenerator(
                region="thighs",
                num_steps=3,
                pos_snap=0.005,
                rot_snap=5.0,
                scale_snap=0.005
            )
            manifest = generator.generate_all(temp_dir, export_bvh=True)

            self.assertIn("total_files_generated", manifest)
            self.assertGreater(manifest["total_files_generated"], 0)

            # Check manifest file exists
            manifest_path = Path(temp_dir) / "manifest.json"
            self.assertTrue(manifest_path.exists())

            # Check LSL script exists
            lsl_path = Path(temp_dir) / "modular_deformer_hud.lsl"
            self.assertTrue(lsl_path.exists())

            # Verify a sample file
            sample_file = Path(temp_dir) / "position_y" / "Thigh_Pos_Y_p01.anim"
            self.assertTrue(sample_file.exists())
            self.assertGreater(sample_file.stat().st_size, 0)

        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
