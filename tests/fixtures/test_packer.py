"""Unit tests for vectorized NumPy ORM Channel Packer."""

import time
import unittest
import bpy
import numpy as np

from sl_pbr_exporter.config import COLORSPACE_NON_COLOR
from sl_pbr_exporter.core.packer import invert_normal_green_channel, pack_orm_image


class TestPacker(unittest.TestCase):

    def setUp(self):
        for img in list(bpy.data.images):
            bpy.data.images.remove(img, do_unlink=True)

    def test_orm_channel_assignment(self):
        """Verify that R=AO (1.0 default), G=Roughness, B=Metallic are correctly packed."""
        orm_img = pack_orm_image(
            name="TestMat",
            resolution=64,
            ao_source=None,  # Should fallback to 1.0
            roughness_source=0.75,
            metallic_source=0.25,
        )

        self.assertEqual(orm_img.colorspace_settings.name, COLORSPACE_NON_COLOR)
        self.assertEqual(orm_img.size[0], 64)
        self.assertEqual(orm_img.size[1], 64)

        # Inspect pixels
        pixels = np.empty(64 * 64 * 4, dtype=np.float32)
        orm_img.pixels.foreach_get(pixels)
        pixels = pixels.reshape((64, 64, 4))

        # Check first pixel
        r, g, b, a = pixels[0, 0]
        self.assertAlmostEqual(r, 1.0, places=2, msg="Red (AO) should default to 1.0")
        self.assertAlmostEqual(g, 0.75, places=2, msg="Green (Roughness) should match 0.75")
        self.assertAlmostEqual(b, 0.25, places=2, msg="Blue (Metallic) should match 0.25")
        self.assertAlmostEqual(a, 1.0, places=2, msg="Alpha should be 1.0")

    def test_normal_green_inversion(self):
        """Verify that DirectX to OpenGL conversion flips the Green channel."""
        norm_img = bpy.data.images.new(name="TestNorm", width=16, height=16)
        # Fill with (0.5, 0.2, 1.0, 1.0)
        flat = np.tile([0.5, 0.2, 1.0, 1.0], 16 * 16).astype(np.float32)
        norm_img.pixels.foreach_set(flat)
        norm_img.update()

        invert_normal_green_channel(norm_img)

        result_pixels = np.empty(16 * 16 * 4, dtype=np.float32)
        norm_img.pixels.foreach_get(result_pixels)
        result_pixels = result_pixels.reshape((16, 16, 4))

        g_val = result_pixels[0, 0, 1]
        self.assertAlmostEqual(g_val, 0.8, places=2, msg="Green channel should be inverted (1.0 - 0.2 = 0.8)")

    def test_packing_performance_benchmark(self):
        """Benchmark that packing a 2048x2048 ORM texture executes in under 0.5 seconds."""
        t0 = time.perf_counter()
        orm_img = pack_orm_image(
            name="PerfBench",
            resolution=2048,
            ao_source=1.0,
            roughness_source=0.5,
            metallic_source=0.0,
        )
        elapsed = time.perf_counter() - t0

        self.assertLess(
            elapsed,
            0.5,
            f"NumPy ORM packing took {elapsed:.3f}s; expected under 0.5s for 2048x2048",
        )
        print(f"  [Benchmark] 2048x2048 ORM packed in {elapsed * 1000:.1f}ms")


if __name__ == "__main__":
    unittest.main()
