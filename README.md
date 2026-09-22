# Second Life PBR Material Exporter (`sl-pbr-exporter`)

A high-performance Blender add-on and extension that automates the inspection, baking, channel packing, and export of Blender materials into **Second Life-compliant glTF 2.0 PBR materials (`.glb`)** and loose texture sets.

Built with first-class dual compatibility for **Blender 3.6 LTS** (classic add-on ecosystem) and **Blender 4.2+ / 5.2 LTS** (extension manifest system).

---

## Highlights

- **Zero-Bake Fast Path**: Automatically detects compliant direct image maps and passes them through without redundant re-rendering.
- **Headless State-Managed Cycles Baker**: Bakes complex procedural nodes, color ramps, and bump-to-normal setups without modifying the artist's original shader node tree or corrupting scene render settings.
- **Emission Passthrough Trick**: Bakes raw, lighting-independent greyscale data for roughness and metallic passes.
- **Vectorized NumPy ORM Channel Packing**: Composites Ambient Occlusion (R), Roughness (G), and Metallic (B) into standard glTF ORM textures in milliseconds using vectorized operations.
- **Non-Blocking Modal Progress**: Modal timer execution ensures Blender's UI never freezes during multi-material bake queues.
- **Second Life Standards Enforced**:
  - Tangent-space OpenGL (+Y) normal format with optional DirectX flip.
  - Resolution caps (512, 1024 default, 2048 hard limit).
  - Automatic Alpha detection with manual overrides (`OPAQUE`, `MASK`, `BLEND`).
  - Optional Mirrored UV Island offsetter (+1.0 in U) to eliminate self-overlap baking seams.

---

## Core Pipeline Architecture

```text
[Mesh / Material Input]
          │
          ▼
   [Stage 1: Inspector]
   (Classifies DIRECT vs PROCEDURAL)
          │
   ┌──────┴──────────────────────┐
   │ (Compliant Images)          │ (Procedural / Bump)
   ▼                             ▼
   │                      [Stage 2: Cycles Baker]
   │                      (Emission Passthrough)
   │                             │
   └──────────────┬──────────────┘
                  ▼
         [Stage 3: Channel Packer]
         (Vectorized NumPy ORM: R=AO, G=Roughness, B=Metallic)
                  │
                  ▼
         [Stage 4: Exporter]
   ┌──────────────┴──────────────┐
   ▼                             ▼
[Target A: glTF .glb]     [Target B: Loose Textures]
(Standalone Material)     (_BaseColor, _ORM, _Normal, _Emissive)
```

---

## Installation

### For Blender 3.6 LTS – 4.1
1. Download **`sl_pbr_exporter-3.6-addon.zip`** from the [Latest Release](https://github.com/GeneralKakyoin/sl-pbr-exporter/releases).
2. In Blender, navigate to **Edit** → **Preferences** → **Add-ons**.
3. Click **Install...** at the top right and select the downloaded `.zip` file.
4. Check the box next to **Import-Export: Second Life PBR Exporter** to enable it.

### For Blender 4.2 LTS / 5.2 LTS (Extensions)
1. Download **`sl_pbr_exporter-4.2-extension.zip`** from the [Latest Release](https://github.com/GeneralKakyoin/sl-pbr-exporter/releases).
2. In Blender, navigate to **Edit** → **Preferences** → **Get Extensions**.
3. Click the top-right menu icon (arrow) → **Install from Disk...** and choose the `.zip` file.

---

## Usage Guide

1. Open your 3D scene in Blender and select the mesh object containing the material you wish to export.
2. In the 3D Viewport, press **`N`** to expand the sidebar and click on the **`SL PBR`** tab.
3. **Configure Settings**:
   - **Target**: Choose `.glb & Loose Textures`, `.glb Material Only`, or `Loose Textures Only`.
   - **Scope**: Choose `Active Material`, `Selected Objects` (deduplicating shared materials), or `All Scene Materials`.
   - **Resolution**: Choose `512`, `1024` (recommended default), or `2048`.
   - **Bake Cycles AO**: (Optional) Bake an Ambient Occlusion pass into the Red channel of the ORM map instead of defaulting to pure white (`1.0`).
   - **PBR Standards**: Configure normal orientation (OpenGL default, with DirectX inversion if needed) and Alpha mode (`Auto`, `Opaque`, `Mask`, `Blend`).
4. Click **Inspect** to preview the pre-flight diagnostic report.
5. Click **Export to Second Life PBR**. The non-blocking modal progress bar will run in the status bar until completion.

### Export Output Hierarchy

Exported files are organized into dedicated material subdirectories:

```text
exports/pbr/
└── Material_Wood/
    ├── Material_Wood.glb              # Second Life glTF PBR container
    └── textures/
        ├── Material_Wood_BaseColor.png
        ├── Material_Wood_ORM.png
        ├── Material_Wood_Normal.png
        └── Material_Wood_Emissive.png
```

---

## Uploading to Second Life

> [!TIP]
> Test uploads on the **Aditi Beta Grid** first to avoid spending Linden Dollars (L$10 per material upload).

1. In your Second Life viewer (e.g. Firestorm or Second Life Viewer with PBR support):
2. Navigate to **Build** → **Upload** → **Material...**.
3. Select your exported `.glb` file (e.g. `Material_Wood.glb`).
4. Preview the material channels (Base Color, Normal, ORM, Emissive) in the previewer.
5. Click **Upload** (L$10).
6. Drag the resulting material from your inventory onto any prim face or mesh in-world!

---

## Development & Automated Testing

### Headless CLI Test Suite
Run the automated test matrix against Blender:

```powershell
# In Blender 3.6 LTS
& "C:\Path\To\blender-3.6\blender.exe" --background --factory-startup --python tests/run_tests.py

# In Blender 5.2 LTS
& "C:\Program Files\Blender Foundation\Blender 5.2\blender.exe" --background --factory-startup --python tests/run_tests.py
```

### Packaging Release Archives
To build both the 3.6 classic add-on zip and the 4.2+ extension zip:

```powershell
python scripts/build_packages.py
```

Generated packages will be output to the `dist/` directory.

---

## License

This project is licensed under the [MIT License](LICENSE).
