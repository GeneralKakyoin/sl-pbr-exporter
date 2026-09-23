#!/usr/bin/env python3
"""Headless test runner for Second Life PBR Exporter inside Blender."""

import os
import sys
import unittest
from pathlib import Path

# Add src and tests to sys.path
ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = ROOT / "src"
TESTS_DIR = ROOT / "tests"

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))

# Ensure we unload any pre-installed add-on from Blender's user preferences
for mod_name in list(sys.modules.keys()):
    if mod_name == "sl_pbr_exporter" or mod_name.startswith("sl_pbr_exporter."):
        del sys.modules[mod_name]

import bpy
import sl_pbr_exporter


def run_test_suite():
    print("\n" + "=" * 70)
    print(f"  RUNNING TEST SUITE: Second Life PBR Exporter")
    print(f"  Blender Version: {bpy.app.version_string}")
    print(f"  Python Version : {sys.version.split()[0]}")
    print("=" * 70 + "\n")

    # Register add-on safely (unregister first if already loaded from user preferences)
    try:
        sl_pbr_exporter.unregister()
    except Exception:
        pass
    sl_pbr_exporter.register()

    # Load all fixture tests
    loader = unittest.TestLoader()
    suite = loader.discover(
        start_dir=str(TESTS_DIR / "fixtures"),
        pattern="test_*.py",
    )

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    # Unregister add-on
    try:
        sl_pbr_exporter.unregister()
    except Exception:
        pass

    print("\n" + "=" * 70)
    if result.wasSuccessful():
        print(f"  TESTS PASSED: {result.testsRun} tests executed successfully.")
        print("=" * 70 + "\n")
        sys.exit(0)
    else:
        print(
            f"  TESTS FAILED: {len(result.failures)} failures, {len(result.errors)} errors across {result.testsRun} tests."
        )
        print("=" * 70 + "\n")
        sys.exit(1)


if __name__ == "__main__":
    run_test_suite()
