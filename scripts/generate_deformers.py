#!/usr/bin/env python3
"""Second Life Deformer Batch Generator CLI.

Usage Examples:
    # Generate 5 levels of thigh width (0.5cm to 2.5cm)
    python scripts/generate_deformers.py --preset thigh_width --levels 5 --min-cm 0.5 --max-cm 2.5

    # Generate 5 levels of butt projection (1.0cm to 3.0cm)
    python scripts/generate_deformers.py --preset butt_projection --levels 5 --min-cm 1.0 --max-cm 3.0

    # Generate starter set for all anatomical presets
    python scripts/generate_deformers.py --all-presets --levels 3

    # List all available presets
    python scripts/generate_deformers.py --list-presets
"""

import argparse
import os
import sys

# Ensure core module is on sys.path without triggering Blender addon bpy imports
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CORE_DIR = os.path.join(REPO_ROOT, "src", "sl_pbr_exporter", "core")
if CORE_DIR not in sys.path:
    sys.path.insert(0, CORE_DIR)

from deformer_generator import DeformerGenerator


def main():
    parser = argparse.ArgumentParser(
        description="Second Life Joint Position Deformer Generator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--preset",
        type=str,
        choices=list(DeformerGenerator.PRESETS.keys()),
        help="Preset deformation channel to generate",
    )
    parser.add_argument(
        "--all-presets",
        action="store_true",
        help="Generate batch intervals for ALL anatomical presets",
    )
    parser.add_argument(
        "--levels",
        type=int,
        default=5,
        help="Number of interval levels to generate (default: 5)",
    )
    parser.add_argument(
        "--min-cm",
        type=float,
        default=0.5,
        help="Minimum offset in centimeters (default: 0.5)",
    )
    parser.add_argument(
        "--max-cm",
        type=float,
        default=2.5,
        help="Maximum offset in centimeters (default: 2.5)",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="export/deformers",
        help="Output directory (default: export/deformers)",
    )
    parser.add_argument(
        "--list-presets",
        action="store_true",
        help="List all supported anatomical presets and exit",
    )

    args = parser.parse_args()

    if args.list_presets:
        print("Available Anatomical Presets:")
        for name in DeformerGenerator.PRESETS.keys():
            print(f"  - {name}")
        return 0

    generator = DeformerGenerator()
    out_dir = os.path.abspath(args.output_dir)

    presets_to_run = []
    if args.all_presets:
        presets_to_run = list(DeformerGenerator.PRESETS.keys())
    elif args.preset:
        presets_to_run = [args.preset]
    else:
        # Default interactive suggestion
        print("No preset specified. Defaulting to '--preset thigh_width'.")
        print("Use --list-presets or --help to view all options.\n")
        presets_to_run = ["thigh_width"]

    print("=" * 65)
    print("  SECOND LIFE JOINT POSITION DEFORMER GENERATOR")
    print("=" * 65)
    print(f"Target Output Directory: {out_dir}")
    print(f"Levels per preset:       {args.levels}")
    print(f"Range:                   {args.min_cm} cm -> {args.max_cm} cm")
    print("-" * 65)

    total_files = 0
    for preset_name in presets_to_run:
        target_sub_dir = os.path.join(out_dir, preset_name)
        files = generator.generate_preset_levels(
            preset_name=preset_name,
            levels=args.levels,
            min_cm=args.min_cm,
            max_cm=args.max_cm,
            output_dir=target_sub_dir,
        )
        total_files += len(files)
        print(f"\n[Preset: {preset_name}] -> {len(files)} files created in {target_sub_dir}")
        for f in files:
            size_kb = os.path.getsize(f) / 1024.0
            print(f"  + {os.path.basename(f):35} ({size_kb:.1f} KB, 1 tri, 3 verts)")

    print("\n" + "=" * 65)
    print(f"SUCCESS: Generated {total_files} Second Life Deformer DAE files!")
    print("=" * 65)
    print("\nHOW TO UPLOAD TO SECOND LIFE:")
    print("  1. In Firestorm / SL Viewer, go to: Build -> Upload -> Model (.dae)")
    print("  2. Select one of the generated .dae files above.")
    print("  3. In the 'Rigging' tab, make sure both are checked:")
    print("     [x] Include skin weights")
    print("     [x] Include joint positions")
    print("  4. In the 'Physics' tab, set Level of Detail to 'Lowest' (or box).")
    print("  5. Click 'Calculate weights & fee' -> fee will be exactly 11 L$!")
    print("  6. Upload and wear the attachment!")
    print("=" * 65)

    return 0


if __name__ == "__main__":
    sys.exit(main())
