"""Unit tests for Second Life Joint Position Deformer Generator."""

import os
import re
import tempfile
import unittest
import xml.etree.ElementTree as ET

from sl_pbr_exporter.core.deformer_generator import DeformerGenerator


class TestDeformerGenerator(unittest.TestCase):
    """Test suite for DeformerGenerator."""

    def setUp(self):
        self.generator = DeformerGenerator()
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_generator_initialization(self):
        """Verify generator initializes with valid base skeleton template."""
        self.assertIsNotNone(self.generator.visual_scene_template)
        self.assertIn("mPelvis", self.generator.visual_scene_template)
        self.assertIn("L_UPPER_LEG", self.generator.visual_scene_template)

    def test_generate_single_valid_xml(self):
        """Generate a single deformer and verify XML structure, triangles, vertices."""
        out_path = os.path.join(self.temp_dir, "test_deformer.dae")
        offsets = {"L_UPPER_LEG": (0.0, -0.015, 0.0), "R_UPPER_LEG": (0.0, 0.015, 0.0)}
        
        result = self.generator.generate_single("TestDeformer", offsets, out_path)
        self.assertTrue(os.path.isfile(result))

        # Check valid XML parse
        tree = ET.parse(result)
        root = tree.getroot()
        self.assertTrue(root.tag.endswith("COLLADA"))

        # Check no NaN / INF
        with open(result, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIsNone(re.search(r"(-?nan|-?inf)", content, re.IGNORECASE))

        # Verify carrier mesh geometry: exactly 1 triangle (3 vertices)
        self.assertIn('count="1"', content)
        self.assertIn('count="9"', content)  # 3 vertices * 3 coords = 9 floats

    def test_bone_offsets_applied(self):
        """Verify the specified bone matrix has the translation delta applied."""
        out_path = os.path.join(self.temp_dir, "offset_test.dae")
        delta_y = -0.025
        offsets = {"L_UPPER_LEG": (0.0, delta_y, 0.0)}
        
        self.generator.generate_single("OffsetTest", offsets, out_path)

        tree = ET.parse(out_path)
        ns = {"c": "http://www.collada.org/2005/11/COLLADASchema"}
        node = tree.find('.//c:node[@id="L_UPPER_LEG"]/c:matrix', ns)
        self.assertIsNotNone(node)
        
        tokens = node.text.split()
        new_y = float(tokens[7])  # row 1, col 3 in 4x4 matrix
        # default L_UPPER_LEG y is approx -0.05
        expected_y = -0.05 + delta_y
        self.assertAlmostEqual(new_y, expected_y, places=3)

    def test_preset_levels_batch(self):
        """Test batch generation of interval levels for a preset."""
        preset_dir = os.path.join(self.temp_dir, "thigh_batch")
        files = self.generator.generate_preset_levels(
            preset_name="thigh_width",
            levels=5,
            min_cm=1.0,
            max_cm=3.0,
            output_dir=preset_dir,
        )
        self.assertEqual(len(files), 5)
        for f in files:
            self.assertTrue(os.path.isfile(f))
            self.assertTrue(f.endswith(".dae"))
            self.assertGreater(os.path.getsize(f), 10000)

    def test_unknown_preset_raises(self):
        """Verify invalid preset names raise ValueError."""
        with self.assertRaises(ValueError):
            self.generator.generate_preset_levels(
                preset_name="nonexistent_preset",
                levels=3,
                output_dir=self.temp_dir,
            )


if __name__ == "__main__":
    unittest.main()
