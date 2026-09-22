"""Unit tests for glTF .glb container and loose texture exporter."""

import shutil
import tempfile
import unittest
from pathlib import Path
import bpy

from sl_pbr_exporter.config import COLORSPACE_NON_COLOR, COLORSPACE_SRGB
from sl_pbr_exporter.core.exporter import (
    build_synthetic_gltf_material,
    export_standalone_glb,
    save_loose_textures,
)
from sl_pbr_exporter.core.packer import pack_orm_image


class TestExporter(unittest.TestCase):

    def setUp(self):
        for mat in list(bpy.data.materials):
            bpy.data.materials.remove(mat, do_unlink=True)
        for obj in list(bpy.data.objects):
            bpy.data.objects.remove(obj, do_unlink=True)
        for mesh in list(bpy.data.meshes):
            bpy.data.meshes.remove(mesh, do_unlink=True)
        for img in list(bpy.data.images):
            bpy.data.images.remove(img, do_unlink=True)
        self.temp_dir = Path(tempfile.mkdtemp(prefix="sl_pbr_test_"))

    def tearDown(self):
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_synthetic_material_and_glb_export(self):
        """Verify that synthetic glTF material is assembled and exported cleanly to a .glb file."""
        # Create test textures
        bc_img = bpy.data.images.new("TestBC", 32, 32)
        bc_img.colorspace_settings.name = COLORSPACE_SRGB

        orm_img = pack_orm_image("TestExportMat", 32, ao_source=1.0, roughness_source=0.5, metallic_source=0.0)

        norm_img = bpy.data.images.new("TestNorm", 32, 32)
        norm_img.colorspace_settings.name = COLORSPACE_NON_COLOR

        synth_mat = build_synthetic_gltf_material(
            name="TestExportMat",
            base_color_img=bc_img,
            orm_img=orm_img,
            normal_img=norm_img,
            alpha_mode="OPAQUE",
        )

        self.assertIsNotNone(synth_mat)
        self.assertTrue(synth_mat.use_nodes)

        # Export .glb
        glb_path = self.temp_dir / "TestExportMat" / "TestExportMat.glb"
        success = export_standalone_glb("TestExportMat", synth_mat, glb_path)

        self.assertTrue(success, "export_standalone_glb should return True")
        self.assertTrue(glb_path.exists(), f"Generated .glb file must exist at {glb_path}")
        self.assertGreater(glb_path.stat().st_size, 0, "Generated .glb file must be non-empty")

    def test_loose_textures_export(self):
        """Verify that loose PNG texture files are written to disk."""
        bc_img = bpy.data.images.new("LooseBC", 32, 32)
        orm_img = pack_orm_image("LooseMat", 32, 1.0, 0.5, 0.0)

        tex_dir = self.temp_dir / "LooseMat" / "textures"
        saved = save_loose_textures(
            material_name="LooseMat",
            textures_dir=tex_dir,
            base_color_img=bc_img,
            orm_img=orm_img,
        )

        self.assertIn("BASE_COLOR", saved)
        self.assertIn("ORM", saved)
        self.assertTrue(saved["BASE_COLOR"].exists())
        self.assertTrue(saved["ORM"].exists())


if __name__ == "__main__":
    unittest.main()
