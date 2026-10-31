# Second Life Creator Suite: Disaster Recovery & Clean-Machine Setup Manual

**Project**: Second Life Creator Suite (`sl_pbr_exporter`)  
**Repository**: [GeneralKakyoin/sl-pbr-exporter](https://github.com/GeneralKakyoin/sl-pbr-exporter)  
**Version**: 0.2.1  
**Target Environments**: Windows 10/11, Blender 3.6 LTS & Blender 5.2 LTS

---

## 1. Overview & Objectives

If your computer dies, your drive corrupts, or you need to reproduce this entire project on a completely new machine, follow this manual step-by-step. 

By following these instructions, you will go from a clean Windows installation to a fully functional, verified development and production environment in **under 15 minutes**, with zero guesswork.

---

## 2. Clean-Machine Software Prerequisites

### Step 1: Install Git & Python
1. **Git**: Download and install [Git for Windows](https://git-scm.com/download/win).
   * Ensure `git` is added to your Windows PATH.
2. **Python 3.10+**: Download and install Python from [python.org](https://www.python.org/) or Microsoft Store.
   * Check *"Add Python to PATH"* during installation.
   * Verify in PowerShell:
     ```powershell
     python --version
     git --version
     ```

### Step 2: Install Blender
Install the supported Blender LTS versions:
1. **Blender 3.6 LTS** (Classic Add-on system):
   * Install path: `C:\Program Files\Blender Foundation\Blender 3.6\blender.exe`
2. **Blender 5.2 LTS** (Extension Manifest system):
   * Install path: `C:\Program Files\Blender Foundation\Blender 5.2\blender.exe`

---

## 3. Clone Repository & Setup Workspace

### Step 1: Clone the Codebase
Open PowerShell in your documents folder:
```powershell
cd C:\Users\$env:USERNAME\Documents\antigravity
git clone https://github.com/GeneralKakyoin/sl-pbr-exporter.git valiant-shannon
cd valiant-shannon
```

### Step 2: Verify Repository Integrity
Check git status and commit history:
```powershell
git status
git log -n 5 --oneline
```

---

## 4. Local Asset Layout & DevKit Conventions

Proprietary commercial DevKits (such as eBODY Reborn, Legacy, Maitreya LaraX, LeLutka EvoX, Kupra, etc.) are protected by Second Life Creator NDAs and intellectual property laws. They are **never stored in the public Git repository**.

Instead, they are maintained locally in your user profile:

### Recommended Directory Structure:
```
C:\Users\<username>\Documents\SecondLife\
└── Kits\
    ├── eBODY Reborn DevKit.blend
    ├── Legacy DevKit.blend
    ├── Maitreya LaraX DevKit.blend
    └── Shapes\
        ├── Default_shape.xml
        └── MyCustomAvatar_shape.xml
```

### DevKit Blend File Requirements:
1. **Armature Object**: Must be named `Avatar` (or contain bone `mPelvis`).
2. **Body Mesh Object**: Must be weighted to `mPelvis`, `mTorso`, and `mChest`.
3. **Rigged Hair / Items**: Weighted to `mHead`, `HEAD`, `mSkull`, or `mFaceRoot`.
4. **Bento Head**: Weighted to `BENTO_FACIAL_FEATURE_BONES`.

> [!NOTE]
> **Synthetic Test Fixtures**:
> The automated test suite (`tests/run_tests.py` and `tests/fixtures/`) does **not** require commercial DevKit files. It generates synthetic in-memory armatures, vertex groups, and Collada DAE structures on the fly, allowing tests to run 100% headless on any clean machine or GitHub CI runner.

---

## 5. Build, Test & Deploy Commands

### 1. Run the Headless Test Suite
Verify that all 48 unit tests pass in Blender 5.2:
```powershell
& "C:\Program Files\Blender Foundation\Blender 5.2\blender.exe" --background --python tests/run_tests.py
```
*Expected Output*: `OK (48 tests executed successfully)`

### 2. Build Release Packages
Build dual ZIP distribution archives in `dist/`:
```powershell
python scripts/build_packages.py
```
Generates:
* `dist/sl_pbr_exporter-3.6-addon.zip`
* `dist/sl_pbr_exporter-4.2-extension.zip`

### 3. Deploy Directly to Live Blender Installations
Sync the latest codebase directly into your local Blender add-on and extension directories:
```powershell
python scripts/deploy_to_blender.py
```
This automatically updates:
* **Blender 3.6**: `%APPDATA%\Blender Foundation\Blender\3.6\scripts\addons\sl_pbr_exporter\`
* **Blender 5.2**: `%APPDATA%\Blender Foundation\Blender\5.2\extensions\user_default\sl_pbr_exporter\`

---

## 6. Installing in Blender via UI (Non-Developer Mode)

If you are reinstalling on a production workstation without setting up a development workspace:

### In Blender 3.6 LTS:
1. Open Blender 3.6.
2. Go to **Edit** $\rightarrow$ **Preferences** $\rightarrow$ **Add-ons**.
3. Click **Install...** at the top right.
4. Select `sl_pbr_exporter-3.6-addon.zip` (downloaded from GitHub Releases).
5. Search for `Second Life Creator Suite` in the search bar and check the checkbox to enable it.

### In Blender 4.2+ / 5.2 LTS:
1. Open Blender 5.2.
2. Go to **Edit** $\rightarrow$ **Preferences** $\rightarrow$ **Get Extensions**.
3. Click the dropdown arrow at the top right $\rightarrow$ **Install from Disk...**.
4. Select `sl_pbr_exporter-4.2-extension.zip`.
5. The extension will install and activate automatically under User Extensions.

---

## 7. Emergency Diagnostics & Troubleshooting Checklist

| Issue | Diagnostic Step | Immediate Fix |
| :--- | :--- | :--- |
| **Changes to code not showing in Blender** | Python caches compiled modules in memory. | In Blender, press `F3` $\rightarrow$ type `Reload Scripts` (`bpy.ops.script.reload()`). If operators were added/removed, restart Blender completely. |
| **Missing module error on `numpy`** | Blender includes NumPy bundled by default. | Verify your Blender installation is not corrupted by running `blender --background --python-expr "import numpy; print(numpy.__file__)"`. |
| **Headless test fails on UI icon check** | A UI icon enum string was used that does not exist in the active Blender version. | Check `tests/fixtures/test_ui.py` output. Replace the invalid icon in `src/sl_pbr_exporter/ui/` with a universal enum like `TOOL_SETTINGS` or `FILE_TICK`. |
| **Avastar operator not found warning** | Avastar is not installed in the background Blender instance. | This is normal during headless unit tests. The suite automatically tests both the Avastar-present path and the graceful standalone fallback path. |
| **GitHub Actions CI fails on Ubuntu** | Workflow `lint_and_test.yml` checks Ruff linting and runs headless Blender. | Run `ruff check src/ scripts/` locally before pushing to catch any formatting or syntax issues. |

---

## 8. Workspace AI Guidelines

The root of this repository contains [`GEMINI.md`](file:///c:/Users/Matti/Documents/antigravity/valiant-shannon/GEMINI.md). This file instructs any future coding assistant on:
1. Mandatory automatic deployment via `python scripts/deploy_to_blender.py`.
2. Reminding the user to reload scripts via `F3 -> Reload Scripts`.
3. Mandatory headless verification before closing turns.
