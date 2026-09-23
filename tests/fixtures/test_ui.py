import re
import unittest
from pathlib import Path
import bpy


class TestUI(unittest.TestCase):
    """Test suite for UI consistency and valid Blender icons."""

    def test_all_ui_icons_are_valid_in_current_blender(self):
        """Audit that all icon="..." references in the UI module are valid Blender enum icons."""
        icons = {
            item.identifier
            for item in bpy.types.UILayout.bl_rna.functions["label"].parameters["icon"].enum_items
        }

        ui_dir = Path(bpy.utils.user_resource("SCRIPTS")).parent  # fallback
        # Find the source ui directory
        import sl_pbr_exporter.ui
        ui_pkg_dir = Path(sl_pbr_exporter.ui.__file__).parent

        invalid_icons = []
        for py_file in ui_pkg_dir.glob("*.py"):
            text = py_file.read_text(encoding="utf-8")
            used = re.findall(r'icon=[\'"]([A-Z0-9_]+)[\'"]', text)
            enum_icons = re.findall(r',\s*[\'"]([A-Z0-9_]+)[\'"],\s*\d+\)', text)
            for u in set(used + enum_icons):
                if u not in icons:
                    invalid_icons.append((py_file.name, u))

        self.assertEqual(
            invalid_icons,
            [],
            f"Found invalid Blender icons in UI files: {invalid_icons}",
        )

    def test_ui_property_groups_registered(self):
        """Verify that scene properties sl_pbr and sl_importer are attached to bpy.context.scene."""
        scene = bpy.context.scene
        self.assertTrue(hasattr(scene, "sl_pbr"), "Scene is missing 'sl_pbr' property group")
        self.assertTrue(hasattr(scene, "sl_importer"), "Scene is missing 'sl_importer' property group")

        # Test switching modes
        scene.sl_pbr.active_mode = "MESH"
        self.assertEqual(scene.sl_pbr.active_mode, "MESH")
        scene.sl_pbr.active_mode = "PBR"
        self.assertEqual(scene.sl_pbr.active_mode, "PBR")
        scene.sl_pbr.active_mode = "MESH"
