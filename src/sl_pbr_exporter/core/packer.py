"""High-performance vectorized NumPy channel packing for glTF 2.0 ORM maps."""

from typing import Any, Dict, Optional, Union
import bpy
import numpy as np

from ..config import COLORSPACE_NON_COLOR, PASS_AO, PASS_METALLIC, PASS_ROUGHNESS


def _extract_channel_array(
    source: Optional[Union[bpy.types.Image, float, int]],
    resolution: int,
    channel_index: int = 0,
    default_value: float = 1.0,
) -> np.ndarray:
    """Extract a 2D float array of shape (H, W) from an Image or constant scalar."""
    if source is None:
        return np.full((resolution, resolution), default_value, dtype=np.float32)

    if isinstance(source, (float, int)):
        return np.full((resolution, resolution), float(source), dtype=np.float32)

    if isinstance(source, bpy.types.Image):
        img = source
        # If dimensions don't match, create a scaled copy
        if img.size[0] != resolution or img.size[1] != resolution:
            temp_copy = img.copy()
            temp_copy.scale(resolution, resolution)
            arr = np.empty(resolution * resolution * 4, dtype=np.float32)
            temp_copy.pixels.foreach_get(arr)
            bpy.data.images.remove(temp_copy, do_unlink=True)
        else:
            arr = np.empty(resolution * resolution * 4, dtype=np.float32)
            img.pixels.foreach_get(arr)

        arr = arr.reshape((resolution, resolution, 4))
        # Return single channel (e.g. 0 for Red/Greyscale, 1 for Green)
        return arr[:, :, channel_index]

    return np.full((resolution, resolution), default_value, dtype=np.float32)


def pack_orm_image(
    name: str,
    resolution: int,
    ao_source: Optional[Union[bpy.types.Image, float]] = None,
    roughness_source: Optional[Union[bpy.types.Image, float]] = None,
    metallic_source: Optional[Union[bpy.types.Image, float]] = None,
) -> bpy.types.Image:
    """Pack Occlusion (R), Roughness (G), and Metallic (B) into a glTF 2.0 ORM texture.

    Executes in milliseconds via NumPy vectorization.
    """
    # 1. R Channel: Ambient Occlusion (fallback to 1.0 pure white)
    r_channel = _extract_channel_array(
        ao_source, resolution, channel_index=0, default_value=1.0
    )

    # 2. G Channel: Roughness (fallback to 0.5)
    g_channel = _extract_channel_array(
        roughness_source, resolution, channel_index=0, default_value=0.5
    )

    # 3. B Channel: Metallic (fallback to 0.0)
    b_channel = _extract_channel_array(
        metallic_source, resolution, channel_index=0, default_value=0.0
    )

    # 4. A Channel: glTF ORM alpha is unused, set to 1.0 (opaque)
    a_channel = np.ones((resolution, resolution), dtype=np.float32)

    # Stack channels to (H, W, 4)
    packed_rgba = np.stack([r_channel, g_channel, b_channel, a_channel], axis=-1)
    flat_pixels = packed_rgba.astype(np.float32).ravel()

    # Create destination image in Blender
    img_name = f"{name}_ORM"
    if img_name in bpy.data.images:
        bpy.data.images.remove(bpy.data.images[img_name])

    orm_image = bpy.data.images.new(
        name=img_name,
        width=resolution,
        height=resolution,
        alpha=True,
        float_buffer=False,
    )
    orm_image.colorspace_settings.name = COLORSPACE_NON_COLOR
    orm_image.pixels.foreach_set(flat_pixels)
    orm_image.update()

    return orm_image


def invert_normal_green_channel(normal_image: bpy.types.Image) -> bpy.types.Image:
    """Flip the green channel (Y) of a normal map to convert from DirectX (-Y) to OpenGL (+Y)."""
    if not normal_image:
        return normal_image

    w, h = normal_image.size
    total_pixels = w * h * 4
    arr = np.empty(total_pixels, dtype=np.float32)
    normal_image.pixels.foreach_get(arr)

    arr = arr.reshape((h, w, 4))
    # Invert green channel: G = 1.0 - G
    arr[:, :, 1] = 1.0 - arr[:, :, 1]

    flat = arr.astype(np.float32).ravel()
    normal_image.pixels.foreach_set(flat)
    normal_image.update()
    return normal_image
