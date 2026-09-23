# Second Life Creator Suite (Mesh & PBR)

A unified Blender add-on and extension combining **Mesh & DevKit Import / Rigging** with automated **Cycles Baking, ORM Channel Packing, and glTF 2.0 PBR Material Export**.

Built with first-class dual compatibility for **Blender 3.6 LTS** (classic add-on ecosystem) and **Blender 4.2+ / 5.2 LTS** (extension manifest system).

---

## Highlights

### 1. Mesh & DevKit Importer (`Mesh & DevKit` Mode)
- **Batch Outfit Loading**: Automatically scans outfit folders and displays an interactive checklist to import multiple pieces at once (with **Select All / Deselect All**).
- **Avastar DevKit Auto-Detection & Appending**:
  - Automatically rebinds imported items to any Avastar `Avatar` armature in the scene.
  - If no DevKit exists in the scene, automatically **appends** the DevKit armature and body mesh from your configured DevKit `.blend` file (stored in `Documents/SecondLife/Kits/`).
- **Second Life Shape XML Integration**: Detects and applies `*_shape.xml` files directly via Avastar (`bpy.ops.avastar.import_shape()`) to match avatar body slider proportions.
- **Coordinate Space Alignment**: Instantly rotates Second Life coordinate space (+X forward) by -90° around Z to align with Blender/Avastar space (-Y forward).
- **Weight Transfer**: One-click Data Transfer modifier projection from the body mesh to the active item, with vertex weights automatically clamped to **max 4 weights per vertex** (Second Life hard limit) and normalized.
- **Second Life Collada (.dae) Export**: Direct export with Avastar presets ready for in-world upload.

### 2. PBR Material Exporter (`PBR Exporter` Mode)
- **Zero-Bake Fast Path**: Detects compliant direct image textures and passes them through without re-rendering.
- **Headless State-Managed Cycles Baker**: Bakes procedural textures, color ramps, and bump-to-normal setups without modifying original artist node trees or corrupting render settings.
- **Emission Passthrough Trick**: Bakes raw, lighting-independent greyscale data for roughness and metallic passes.
- **Vectorized NumPy ORM Channel Packing**: Composites Ambient Occlusion (R), Roughness (G), and Metallic (B) into standard glTF ORM textures in milliseconds (~60ms for 2048x2048).
- **Second Life Standards Enforced**: OpenGL (+Y) normals, 2048px resolution caps, automated Alpha detection (`OPAQUE`, `MASK`, `BLEND`), and optional Mirrored UV Island offsetter.

---

## Directory Organization

The suite utilizes clean, dynamic folders in your **Documents** directory (completely decoupled from any hardcoded username):

```text
Documents/
└── SecondLife/
    ├── Kits/                          # Avastar DevKit .blend files (eBODY Reborn, etc.)
    └── Exports/
        ├── Mesh/                      # Default destination for Mesh items
        └── PBR/                       # Default destination for PBR materials
            ├── MATERIALS/             # Standalone .glb containers
            │   └── Material_Wood.glb
            └── TEXTURES/              # Loose textures
                ├── Material_Wood_BaseColor.png
                ├── Material_Wood_ORM.png
                ├── Material_Wood_Normal.png
                └── Material_Wood_Emissive.png
```

---

## Installation

### For Blender 3.6 LTS – 4.1
1. Download **`sl_pbr_exporter-3.6-addon.zip`** from the [Latest Release](https://github.com/GeneralKakyoin/sl-pbr-exporter/releases).
2. In Blender, navigate to **Edit** → **Preferences** → **Add-ons**.
3. Click **Install...** and select the `.zip` file.
4. Check **Import-Export: Second Life Creator Suite (Mesh & PBR)** to enable it.

### For Blender 4.2 LTS / 5.2 LTS (Extensions)
1. Download **`sl_pbr_exporter-4.2-extension.zip`** from the [Latest Release](https://github.com/GeneralKakyoin/sl-pbr-exporter/releases).
2. In Blender, navigate to **Edit** → **Preferences** → **Get Extensions**.
3. Click the top-right menu icon → **Install from Disk...** and choose the `.zip` file.

---

## Usage Guide

1. In Blender, press **`N`** in the 3D Viewport to open the sidebar, and switch to the **`Second Life`** tab.
2. Use the top toggle buttons to switch between **`[ Mesh & DevKit ]`** and **`[ PBR Material Exporter ]`**:

### Mode 1: Mesh & DevKit
- **DevKit Status**: Shows active armature and Avastar status.
- **Folder**: Select an outfit folder or single-item folder.
- **Checklist**: Check the items you wish to load, or click **Select All**.
- Click **Load Selected onto DevKit**.
- If needed, click **Transfer Weights from Body** to refit weights.
- Click **Export Item for SL (.dae)** to generate the final upload file.

### Mode 2: PBR Material Exporter
- Configure **Target** (`.glb & Loose Textures`), **Scope**, **Resolution** (512, 1024, 2048), and **PBR Standards**.
- Click **Inspect** to run pre-flight diagnostics.
- Click **Export to Second Life PBR**. The non-blocking modal progress timer will run in the status bar.

---

## Development & Automated Testing

Run the automated test suite across installed Blender versions:

```powershell
# Blender 3.6 LTS
& "C:\Path\To\blender-3.6\blender.exe" --background --factory-startup --python tests/run_tests.py

# Blender 5.2 LTS
& "C:\Program Files\Blender Foundation\Blender 5.2\blender.exe" --background --factory-startup --python tests/run_tests.py
```

### Packaging Release Archives
```powershell
python scripts/build_packages.py
```

---

## License

Licensed under the [MIT License](LICENSE).
