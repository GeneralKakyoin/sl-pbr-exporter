"""Unit tests for Second Life .anim and .bvh Deformer Animation Generator.

Verifies:
- Byte-accurate .anim v1.0 binary serialization and deserialization
- Float32 to uint16 quantization precision within SL error bounds
- Quaternion compression (LLQuaternion::packToVector3)
- Modular channel isolation (Position, Rotation, Scale independence)
- Symmetrical bilateral joint transformations for all 7 anatomical regions
- Master multi-region batch generation and manifest integrity
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
from sl_pbr_exporter.core.deformer_anim_generator import DeformerAnimGenerator, REGIONS_CONFIG


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

    def test_all_7_regions_joint_transforms(self):
        """Verify joint transforms across all 16 channels in 7 anatomical regions."""
        generator = DeformerAnimGenerator(region="all", num_steps=2)

        total_channels = 0
        for reg_name, channels in REGIONS_CONFIG.items():
            for ch in channels:
                total_channels += 1
                joints, bvh_rots = generator._build_joint_transforms(reg_name, ch.name, 0.020)
                self.assertGreater(len(joints), 0, f"Channel {ch.name} produced 0 joints!")

                if ch.category in ("position", "scale"):
                    for j in joints:
                        self.assertEqual(len(j["rot_keys"]), 0, f"{ch.name} must have 0 rot keys!")
                        self.assertEqual(len(j["pos_keys"]), 2, f"{ch.name} must have 2 pos keys!")
                elif ch.category == "rotation":
                    for j in joints:
                        self.assertEqual(len(j["pos_keys"]), 0, f"{ch.name} must have 0 pos keys!")
                        self.assertEqual(len(j["rot_keys"]), 2, f"{ch.name} must have 2 rot keys!")
                    self.assertIn("mTorso", bvh_rots)

        self.assertEqual(total_channels, 16, "Master configuration must define exactly 16 channels.")

    def test_butt_lift_and_pushup_diagonal_vectors(self):
        """Verify 45-degree diagonal shelf projection for Butt_Lift and Breast_PushUp."""
        generator = DeformerAnimGenerator(region="all")

        # Butt_Lift: posterior (-X) and superior (+Z)
        butt_joints, _ = generator._build_joint_transforms("butt", "Butt_Lift", 0.010)
        self.assertEqual(len(butt_joints), 1)
        self.assertEqual(butt_joints[0]["name"], "BUTT")
        pos = butt_joints[0]["pos_keys"][0][1]
        self.assertAlmostEqual(pos[0], -0.010 * 0.70710678, places=4)
        self.assertAlmostEqual(pos[2], 0.010 * 0.70710678, places=4)

        # Breast_PushUp: anterior (+X) and superior (+Z)
        pec_joints, _ = generator._build_joint_transforms("breasts", "Breast_PushUp", 0.010)
        self.assertEqual(len(pec_joints), 2)
        pec_pos = pec_joints[0]["pos_keys"][0][1]
        self.assertAlmostEqual(pec_pos[0], 0.010 * 0.70710678, places=4)
        self.assertAlmostEqual(pec_pos[2], 0.010 * 0.70710678, places=4)

    def test_collarbone_and_ankle_bilateral_mirroring(self):
        """Verify bilateral medial tapering for Shoulder_Width and Ankle_Thin."""
        generator = DeformerAnimGenerator(region="all")

        # Shoulder_Width: Left moves -Y, Right moves +Y (inward)
        sh_joints, _ = generator._build_joint_transforms("shoulders", "Shoulder_Width", 0.015)
        self.assertEqual(len(sh_joints), 2)
        self.assertAlmostEqual(sh_joints[0]["pos_keys"][0][1][1], -0.015)
        self.assertAlmostEqual(sh_joints[1]["pos_keys"][0][1][1], 0.015)

        # Ankle_Thin: Left moves -Y, Right moves +Y (inward)
        ank_joints, _ = generator._build_joint_transforms("calves", "Ankle_Thin", 0.012)
        self.assertEqual(len(ank_joints), 2)
        self.assertAlmostEqual(ank_joints[0]["pos_keys"][0][1][1], -0.012)
        self.assertAlmostEqual(ank_joints[1]["pos_keys"][0][1][1], 0.012)

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
            lsl_path = Path(temp_dir) / "thighs_deformer_hud.lsl"
            self.assertTrue(lsl_path.exists())

            # Verify a sample file
            sample_file = Path(temp_dir) / "thigh_gap" / "Thigh_Gap_p01.anim"
            self.assertTrue(sample_file.exists())
            self.assertGreater(sample_file.stat().st_size, 0)

        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def test_master_all_regions_batch_generation(self):
        """Verify master generator produces all 7 region directories and master LSL script."""
        temp_dir = tempfile.mkdtemp(prefix="sl_anim_master_test_")
        try:
            generator = DeformerAnimGenerator(region="all", num_steps=2)
            manifest = generator.generate_all(temp_dir, export_bvh=True)

            # 16 channels * 4 files (2 pos, 2 neg) = 64 anim files + 4 bvh files = 68 files
            self.assertEqual(manifest["total_files_generated"], 68)

            # Check master HUD script exists
            master_lsl = Path(temp_dir) / "master_deformer_hud.lsl"
            self.assertTrue(master_lsl.exists())
            with open(master_lsl, "r", encoding="utf-8") as f:
                lsl_content = f.read()
                self.assertIn("MASTER AVATAR DEFORMER", lsl_content)
                self.assertIn("Thighs", lsl_content)
                self.assertIn("Posture", lsl_content)

            # Check all 7 region folders exist
            for reg in REGIONS_CONFIG.keys():
                reg_dir = Path(temp_dir) / reg
                self.assertTrue(reg_dir.is_dir(), f"Region directory {reg} missing!")

        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
