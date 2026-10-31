#!/usr/bin/env python3
"""Unified pipeline: build packages, deploy to Blender, run tests, and push to GitHub."""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BLENDER_EXE = Path(r"C:\Program Files\Blender Foundation\Blender 5.2\blender.exe")


def run(cmd, desc, check=True):
    print(f"\n[Sync] {desc}...")
    res = subprocess.run(cmd, cwd=str(ROOT))
    if check and res.returncode != 0:
        print(f"[Sync] Error: '{desc}' failed with exit code {res.returncode}. Aborting.")
        sys.exit(res.returncode)
    return res.returncode


def main():
    commit_msg = sys.argv[1] if len(sys.argv) > 1 else None

    # 1. Build and deploy locally
    run([sys.executable, str(ROOT / "scripts" / "deploy_to_blender.py")], "Building packages and deploying to local Blender")

    # 2. Run test suite
    if BLENDER_EXE.exists():
        run([str(BLENDER_EXE), "--background", "--python", str(ROOT / "tests" / "run_tests.py")], "Running headless test suite")
    else:
        print(f"[Sync] Warning: Blender binary not found at {BLENDER_EXE}. Skipping local test run.")

    # 3. Stage, commit, and push to GitHub if repo is dirty or unpushed commits exist
    status = subprocess.run(["git", "status", "--porcelain"], cwd=str(ROOT), capture_output=True, text=True)
    ahead = subprocess.run(["git", "log", "origin/main..main", "--oneline"], cwd=str(ROOT), capture_output=True, text=True)

    has_changes = bool(status.stdout.strip())
    has_unpushed = bool(ahead.stdout.strip())

    if has_changes:
        if not commit_msg:
            commit_msg = "chore: sync code changes and build packages"
        run(["git", "add", "."], "Staging all changes")
        run(["git", "commit", "-m", commit_msg], f"Committing changes: '{commit_msg}'")
        run(["git", "push", "origin", "main"], "Pushing to GitHub origin/main")
    elif has_unpushed:
        run(["git", "push", "origin", "main"], "Pushing pending commits to GitHub origin/main")
    else:
        print("\n[Sync] Repository is already clean and up to date with origin/main.")

    print("\n[Sync] All sync steps completed successfully! GitHub is 100% in sync.")


if __name__ == "__main__":
    main()
