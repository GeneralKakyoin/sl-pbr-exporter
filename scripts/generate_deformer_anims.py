#!/usr/bin/env python3
"""CLI utility to generate upload-ready Second Life .anim and .bvh deformation animations.

Supports all 7 Anatomical Regions (16 Independent Modular Channels):
  1. thighs   : Thigh_Gap, Thigh_Volume, Thigh_Length
  2. butt     : Butt_Lift, Butt_Volume
  3. waist    : Belly_Pooch, Hip_Dips, Waist_Cinch
  4. breasts  : Breast_Cleavage, Breast_PushUp, Breast_Volume
  5. calves   : Calf_Girth, Ankle_Thin
  6. shoulders: Shoulder_Width, Shoulder_Slope
  7. posture  : Runway_Arch
  or 'all' to generate the complete master deformation suite.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Add core directory to sys.path so it runs standalone without Blender bpy dependencies
PROJECT_ROOT = Path(__file__).resolve().parent.parent
CORE_DIR = PROJECT_ROOT / "src" / "sl_pbr_exporter" / "core"
if str(CORE_DIR) not in sys.path:
    sys.path.insert(0, str(CORE_DIR))

from deformer_anim_generator import DeformerAnimGenerator, REGIONS_CONFIG


def main():
    parser = argparse.ArgumentParser(
        description="Generate Second Life modular deformation animations (.anim v1.0 & .bvh)."
    )
    valid_regions = list(REGIONS_CONFIG.keys()) + ["all"]
    parser.add_argument(
        "--region",
        default="all",
        choices=valid_regions,
        help="Avatar body region to deform (default: all)."
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
        default=2.5,
        help="Rotation snap increment in degrees (default: 2.5 deg)."
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
        default=None,
        help="Target output directory (default: export/anims/[region])."
    )
    parser.add_argument(
        "--no-bvh",
        action="store_true",
        help="Disable generating companion .bvh files for rotation tracks."
    )

    args = parser.parse_args()

    # Default output directory
    if args.out:
        out_dir = Path(args.out)
    else:
        if args.region == "all":
            out_dir = PROJECT_ROOT / "export" / "anims"
        else:
            out_dir = PROJECT_ROOT / "export" / "anims" / args.region

    if not out_dir.is_absolute():
        out_dir = PROJECT_ROOT / out_dir

    print(f"======================================================================")
    print(f"  Second Life Multi-Region Deformer Animation Generator")
    print(f"  Region       : {args.region.upper()}")
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
    current_reg = None
    for ch_name, ch_data in manifest["channels"].items():
        reg = ch_data.get("region", "thighs").upper()
        if reg != current_reg:
            print(f"\n  [{reg}]")
            current_reg = reg
        count = len(ch_data["steps"])
        unit = ch_data["unit"]
        snap = ch_data["snap"]
        desc = ch_data.get("description", "")
        print(f"    - {ch_data['name']:<18} : {count:2d} steps (snap: {snap} {unit}) -> {desc}")

    print(f"\nArtifacts:")
    print(f"  - Manifest  : {manifest['manifest_file']}")
    print(f"  - LSL Script: {manifest['lsl_script']}")
    print(f"\nSecond Life Upload Instructions:")
    print(f"  1. In Firestorm / SL Viewer, select 'Upload' -> 'Animation...'")
    print(f"  2. Bulk select all .anim files from the generated folders.")
    print(f"  3. Drop the uploaded animations and the generated .lsl HUD script into your HUD prim.")
    print(f"  4. Attach the HUD and sculpt your avatar in real time without conflicting with AOs!")
    print(f"======================================================================")


if __name__ == "__main__":
    main()
