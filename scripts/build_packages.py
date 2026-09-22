#!/usr/bin/env python3
"""Build distribution archives for both Blender 3.6 (classic add-on) and Blender 4.2+ (extension)."""

import os
import shutil
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = ROOT / "src" / "sl_pbr_exporter"
DIST_DIR = ROOT / "dist"
MANIFEST_FILE = ROOT / "blender_manifest.toml"
README_FILE = ROOT / "README.md"
LICENSE_FILE = ROOT / "LICENSE"


def clean_dist():
    if DIST_DIR.exists():
        shutil.rmtree(DIST_DIR)
    DIST_DIR.mkdir(parents=True, exist_ok=True)


def build_addon_zip_3_6():
    """Build classic add-on zip: files are placed inside an 'sl_pbr_exporter' folder in the zip."""
    zip_path = DIST_DIR / "sl_pbr_exporter-3.6-addon.zip"
    print(f"Building Blender 3.6+ classic add-on zip: {zip_path.name}...")

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(SRC_DIR):
            # Ignore __pycache__ and hidden files
            dirs[:] = [d for d in dirs if not d.startswith(".") and d != "__pycache__"]
            for file in files:
                if file.startswith(".") or file.endswith((".pyc", ".pyo")):
                    continue
                file_path = Path(root) / file
                rel_path = file_path.relative_to(SRC_DIR)
                archive_name = Path("sl_pbr_exporter") / rel_path
                zf.write(file_path, archive_name)

        if README_FILE.exists():
            zf.write(README_FILE, Path("sl_pbr_exporter") / "README.md")
        if LICENSE_FILE.exists():
            zf.write(LICENSE_FILE, Path("sl_pbr_exporter") / "LICENSE")

    print(f"Successfully generated {zip_path} ({zip_path.stat().st_size} bytes)")


def build_extension_zip_4_2():
    """Build Blender 4.2+ extension zip: manifest and code files are at the root of the zip."""
    zip_path = DIST_DIR / "sl_pbr_exporter-4.2-extension.zip"
    print(f"Building Blender 4.2+ extension zip: {zip_path.name}...")

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        # Write manifest at the root
        if MANIFEST_FILE.exists():
            zf.write(MANIFEST_FILE, "blender_manifest.toml")

        for root, dirs, files in os.walk(SRC_DIR):
            dirs[:] = [d for d in dirs if not d.startswith(".") and d != "__pycache__"]
            for file in files:
                if file.startswith(".") or file.endswith((".pyc", ".pyo")):
                    continue
                file_path = Path(root) / file
                rel_path = file_path.relative_to(SRC_DIR)
                zf.write(file_path, rel_path)

        if README_FILE.exists():
            zf.write(README_FILE, "README.md")
        if LICENSE_FILE.exists():
            zf.write(LICENSE_FILE, "LICENSE")

    print(f"Successfully generated {zip_path} ({zip_path.stat().st_size} bytes)")


def main():
    print("=" * 60)
    print("  Second Life PBR Exporter - Dual Package Builder")
    print("=" * 60)
    clean_dist()
    build_addon_zip_3_6()
    build_extension_zip_4_2()
    print("=" * 60)
    print("Packages created in dist/ folder:")
    for f in DIST_DIR.glob("*.zip"):
        print(f" - {f.name} ({f.stat().st_size:,} bytes)")
    print("=" * 60)


if __name__ == "__main__":
    main()
