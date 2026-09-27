"""
Batch render script to visually verify 3 completely different avatar exports:
1. Celine32x: Maitreya LaraX Petite Body + LeLutka Kaya 4.0 Head + Dama Dress + Nicha Hair
2. Kalach07: Legacy (f) Body + LeLutka Avalon Lite Head + Vintage Tee + Cutoffs + Yadira Hair
3. Scarlett Romano: eBODY Reborn Body + LeLutka Fleur 3.1 Head + Alba Dress + Ines Stockings + Risk Hair
"""

import math
import sys
from pathlib import Path
import bpy

# Set up paths
ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

# Unload any pre-installed add-on
for mod in list(sys.modules.keys()):
    if "sl_pbr_exporter" in mod:
        del sys.modules[mod]

import sl_pbr_exporter

OUTPUT_DIR = Path(r"C:\Users\Matti\.gemini\antigravity\brain\276e3c20-ec66-4e19-bc45-563c4a995eb5")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

EXPORTS = [
    {
        "id": "export1_celine_maitreya_larax",
        "title": "Maitreya LaraX Petite + LeLutka Kaya 4.0",
        "folder": r"C:\Users\Matti\Desktop\Test SL export\Celine32x",
    },
    {
        "id": "export2_kalach07_legacy_body",
        "title": "Legacy Meshbody (f) + LeLutka Avalon Lite",
        "folder": r"C:\Users\Matti\Desktop\Test SL export\First Batch\Kalach07\Kalach07",
    },
    {
        "id": "export3_scarlett_ebody_reborn",
        "title": "eBODY Reborn + LeLutka Fleur 3.1",
        "folder": r"C:\Users\Matti\Desktop\Test SL export\Scarlett Romano",
    },
]


def setup_studio_environment():
    # Remove all lights and cameras
    for obj in list(bpy.data.objects):
        if obj.type in ("LIGHT", "CAMERA"):
            bpy.data.objects.remove(obj, do_unlink=True)

    # World background
    world = bpy.context.scene.world
    if not world:
        world = bpy.data.worlds.new("StudioWorld")
        bpy.context.scene.world = world
    world.use_nodes = True
    bg_node = world.node_tree.nodes.get("Background")
    if bg_node:
        bg_node.inputs["Color"].default_value = (0.12, 0.13, 0.15, 1.0)
        bg_node.inputs["Strength"].default_value = 0.8

    # 4-point studio lighting
    lights = [
        ("Key_Front_Right", (1.6, -2.4, 1.9), 320),
        ("Fill_Front_Left", (-1.8, -2.0, 1.5), 180),
        ("Rim_Back_Left", (-1.6, 2.2, 1.8), 260),
        ("Rim_Back_Right", (1.6, 2.2, 1.8), 260),
        ("Bottom_Bounce", (0.0, -1.4, 0.3), 90),
    ]
    for name, loc, energy in lights:
        light_data = bpy.data.lights.new(name, "POINT")
        light_data.energy = energy
        light_obj = bpy.data.objects.new(name, light_data)
        light_obj.location = loc
        bpy.context.scene.collection.objects.link(light_obj)

    # Camera with slight three-quarter dynamic angle (15 degrees)
    cam_data = bpy.data.cameras.new("StudioCam")
    cam_data.lens = 55.0  # Portrait lens
    cam_obj = bpy.data.objects.new("StudioCam", cam_data)
    bpy.context.scene.collection.objects.link(cam_obj)
    bpy.context.scene.camera = cam_obj

    dist = 2.85
    angle_rad = math.radians(-15.0)
    cx = dist * math.sin(angle_rad)
    cy = -dist * math.cos(angle_rad)
    cz = 1.02
    cam_obj.location = (cx, cy, cz)
    cam_obj.rotation_euler = (math.radians(91.0), 0.0, angle_rad)

    # Render settings
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.samples = 32
    scene.render.resolution_x = 800
    scene.render.resolution_y = 1200
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    scene.view_settings.view_transform = "Standard"


def run_batch_renders():
    for exp in EXPORTS:
        print(f"\n{'='*70}\n[RENDER] Processing {exp['title']}...\n{'='*70}")
        # Reset scene
        bpy.ops.wm.read_factory_settings(use_empty=True)

        # Register add-on
        try:
            sl_pbr_exporter.unregister()
        except Exception:
            pass
        sl_pbr_exporter.register()

        props = bpy.context.scene.sl_importer
        props.folder_path = exp["folder"]
        props.auto_append_devkit = False
        props.apply_shape = True

        # Scan and import
        bpy.ops.sl_suite.scan_items()
        print(f"Scanned {len(props.items)} items in {exp['folder']}")

        res = bpy.ops.sl_suite.load_selected_items()
        print(f"Import result: {res}")

        # Setup environment and render
        setup_studio_environment()

        out_path = OUTPUT_DIR / f"{exp['id']}.png"
        bpy.context.scene.render.filepath = str(out_path)
        print(f"Rendering to {out_path}...")
        bpy.ops.render.render(write_still=True)
        print(f"Render complete: {out_path} (exists: {out_path.exists()})")


if __name__ == "__main__":
    run_batch_renders()
