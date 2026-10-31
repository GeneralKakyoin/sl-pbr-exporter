#!/usr/bin/env python3
"""Build packages and automatically deploy to local Blender 3.6 and 5.2+ installations."""

import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = ROOT / "src" / "sl_pbr_exporter"
MANIFEST_FILE = ROOT / "blender_manifest.toml"
SCRIPTS_DIR = ROOT / "scripts"

# Import build_packages
sys.path.insert(0, str(SCRIPTS_DIR))
import build_packages


def deploy():
    # 1. Run full packaging
    build_packages.main()

    appdata = os.environ.get("APPDATA")
    if not appdata:
        print("[Deploy] Warning: APPDATA environment variable not found.")
        return

    blender_appdata = Path(appdata) / "Blender Foundation" / "Blender"

    # Targets to sync
    targets = [
        ("Blender 3.6 (Classic Addon)", blender_appdata / "3.6" / "scripts" / "addons" / "sl_pbr_exporter", False),
        ("Blender 5.2 (Extension)", blender_appdata / "5.2" / "extensions" / "user_default" / "sl_pbr_exporter", True),
    ]

    print("\nDeploying files to local Blender installations...")
    for label, target_dir, is_extension in targets:
        if not target_dir.parent.exists():
            continue

        target_dir.mkdir(parents=True, exist_ok=True)

        # Copy source tree excluding __pycache__ and hidden files
        for root, dirs, files in os.walk(SRC_DIR):
            dirs[:] = [d for d in dirs if not d.startswith(".") and d != "__pycache__"]
            rel_dir = Path(root).relative_to(SRC_DIR)
            dest_dir = target_dir / rel_dir
            dest_dir.mkdir(parents=True, exist_ok=True)
            for f in files:
                if f.startswith(".") or f.endswith((".pyc", ".pyo")):
                    continue
                shutil.copy2(Path(root) / f, dest_dir / f)

        if is_extension and MANIFEST_FILE.exists():
            shutil.copy2(MANIFEST_FILE, target_dir / "blender_manifest.toml")

        print(f" -> Deployed successfully to {label}: {target_dir}")

    print("\nDeployment complete! Reload in Blender with F3 -> 'Reload Scripts' or restart.")


if __name__ == "__main__":
    deploy()
