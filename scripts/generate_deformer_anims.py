#!/usr/bin/env python3
"""CLI utility to generate upload-ready Second Life .anim and .bvh deformation animations."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Add core directory to sys.path so it runs standalone without Blender bpy dependencies
PROJECT_ROOT = Path(__file__).resolve().parent.parent
CORE_DIR = PROJECT_ROOT / "src" / "sl_pbr_exporter" / "core"
if str(CORE_DIR) not in sys.path:
    sys.path.insert(0, str(CORE_DIR))

from deformer_anim_generator import DeformerAnimGenerator


def main():
    parser = argparse.ArgumentParser(
        description="Generate Second Life modular deformation animations (.anim v1.0 & .bvh)."
    )
    parser.add_argument(
        "--region",
        default="thighs",
        help="Avatar body region to deform (default: thighs)."
    )
    parser.add_argument(
        "--steps",
        type=int,
        default=10,
        help="Number of steps in each direction (positive and negative, default: 10)."
    )
    parser.add_argument(
        "--pos-snap",
        type=float,
        default=0.005,
        help="Position snap increment in meters (default: 0.005 = 5mm)."
    )
    parser.add_argument(
        "--rot-snap",
        type=float,
        default=5.0,
        help="Rotation snap increment in degrees (default: 5.0 deg)."
    )
    parser.add_argument(
        "--scale-snap",
        type=float,
        default=0.005,
        help="Scale volume/length snap increment in meters (default: 0.005 = 5mm)."
    )
    parser.add_argument(
        "--priority",
        type=int,
        default=5,
        help="Animation priority level (default: 5)."
    )
    parser.add_argument(
        "--out",
        default="export/anims/thighs",
        help="Target output directory (default: export/anims/thighs)."
    )
    parser.add_argument(
        "--no-bvh",
        action="store_true",
        help="Disable generating companion .bvh files for rotation tracks."
    )

    args = parser.parse_args()

    out_dir = Path(args.out)
    if not out_dir.is_absolute():
        out_dir = PROJECT_ROOT / out_dir
    print(f"======================================================================")
    print(f"  Second Life Deformer Animation Generator")
    print(f"  Region       : {args.region.title()}")
    print(f"  Steps        : {args.steps} (+1 to +{args.steps}, -1 to -{args.steps})")
    print(f"  Position Snap: {args.pos_snap * 1000.0:.1f} mm ({args.pos_snap} m)")
    print(f"  Rotation Snap: {args.rot_snap:.1f} deg")
    print(f"  Scale Snap   : {args.scale_snap * 1000.0:.1f} mm ({args.scale_snap} m)")
    print(f"  Priority     : {args.priority}")
    print(f"  Output Dir   : {out_dir}")
    print(f"======================================================================\n")

    generator = DeformerAnimGenerator(
        region=args.region,
        num_steps=args.steps,
        pos_snap=args.pos_snap,
        rot_snap=args.rot_snap,
        scale_snap=args.scale_snap,
        priority=args.priority
    )

    manifest = generator.generate_all(
        output_dir=out_dir,
        export_bvh=not args.no_bvh
    )

    print(f"Successfully generated {manifest['total_files_generated']} animation files:")
    for ch_name, ch_data in manifest["channels"].items():
        count = len(ch_data["steps"])
        unit = ch_data["unit"]
        snap = ch_data["snap"]
        print(f"  - [{ch_name.upper():<14}] : {count} steps (snap: {snap} {unit})")

    print(f"\nArtifacts:")
    print(f"  - Manifest  : {manifest['manifest_file']}")
    print(f"  - LSL Script: {manifest['lsl_script']}")
    print(f"\nSecond Life Upload Instructions:")
    print(f"  1. In Firestorm / SL Viewer, select 'Upload' -> 'Animation...'")
    print(f"  2. Choose all the .anim files from the folders above (or bulk upload).")
    print(f"  3. Drop the uploaded animations and 'modular_deformer_hud.lsl' into your HUD prim.")
    print(f"  4. Attach the HUD and click to sculpt your avatar in real-time!")
    print(f"======================================================================")


if __name__ == "__main__":
    main()
