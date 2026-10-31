# Second Life Creator Suite (Mesh & PBR)

[![GitHub Release](https://img.shields.io/github/v/release/GeneralKakyoin/sl-pbr-exporter?color=blue&label=Latest%20Release)](https://github.com/GeneralKakyoin/sl-pbr-exporter/releases/latest)
[![Blender 3.6 LTS](https://img.shields.io/badge/Blender-3.6%20LTS-orange.svg)](https://github.com/GeneralKakyoin/sl-pbr-exporter/releases/latest)
[![Blender 5.2 LTS](https://img.shields.io/badge/Blender-5.2%20LTS-blue.svg)](https://github.com/GeneralKakyoin/sl-pbr-exporter/releases/latest)
[![Test Suite](https://img.shields.io/badge/Tests-48%20Passed-brightgreen.svg)](https://github.com/GeneralKakyoin/sl-pbr-exporter/actions)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

A unified Blender add-on and extension combining **Mesh & DevKit Import / Rigging** with automated **Cycles Baking, ORM Channel Packing, and glTF 2.0 PBR Material Export**.

Built with first-class dual compatibility for **Blender 3.6 LTS** (classic add-on ecosystem) and **Blender 4.2+ / 5.2 LTS** (extension manifest system).

---

## 🚀 Quick Download & Install (30 Seconds)

Download the pre-packaged zip for your Blender version from [Latest Releases](https://github.com/GeneralKakyoin/sl-pbr-exporter/releases/latest):

| Blender Version | Package Archive | Installation Instructions |
| :--- | :--- | :--- |
| **Blender 3.6 LTS** | [`sl_pbr_exporter-3.6-addon.zip`](https://github.com/GeneralKakyoin/sl-pbr-exporter/releases/latest) | `Edit` $\rightarrow$ `Preferences` $\rightarrow$ `Add-ons` $\rightarrow$ `Install...` $\rightarrow$ Select ZIP. Enable **Second Life Creator Suite**. |
| **Blender 4.2+ / 5.2 LTS** | [`sl_pbr_exporter-4.2-extension.zip`](https://github.com/GeneralKakyoin/sl-pbr-exporter/releases/latest) | `Edit` $\rightarrow$ `Preferences` $\rightarrow$ `Get Extensions` $\rightarrow$ Top right menu $\rightarrow$ `Install from Disk...` $\rightarrow$ Select ZIP. |

---

## 📚 Technical Documentation & Knowledge Base

- **[Architecture & Knowledge Codex](docs/ARCHITECTURE_AND_KNOWLEDGE_BASE.md)**: Full mathematical equations ($S_{\text{eff}} = S_{\text{shape}} / S_{\text{bind}}$, FK trees, coordinate rotations $\mathbf{R}_z(\pm 90^\circ)$, $\Delta Z_{\text{neck}}$ seam lock), 4-way topological mesh classification, forensic analysis of past false diagnoses ("the culprit traps"), and PBR baking internals.
- **[Disaster Recovery & Clean-Machine Manual](docs/DISASTER_RECOVERY.md)**: Zero-to-hero instructions to reconstruct the entire development and production environment from scratch on a clean machine in under 15 minutes.
- **[Verified Bento Shape Engine Fix Record](docs/VERIFIED_BENTO_SHAPE_FIX.md)**: Forensic record and user-verified benchmarks for Bento facial mesh deformation.

---

## Highlights

### 1. Mesh & DevKit Importer (`Mesh & DevKit` Mode)
- **Batch Outfit Loading**: Automatically scans outfit folders and displays an interactive checklist to import multiple pieces at once (with **Select All / Deselect All**).
- **Hybrid Avatar & Item Shaping Architecture**:
  - Automatically classifies all scene meshes (Bento face, rigged hair, unrigged items, and rigged clothing).
  - Shields custom Bento heads and rigged hair while driving body clothing through Avastar's slider deformation pass.
  - Deforms Bento facial meshes using exact 1:1 Linden GenePool math with inverse bind matrix compensation and neck anchoring.
  - Applies forward kinematics and bone scaling to rigged hair via non-destructive shape keys.
- **Avastar DevKit Auto-Detection & Appending**:
  - Automatically rebinds imported items to any Avastar `Avatar` armature in the scene.
  - If no DevKit exists in the scene, automatically **appends** the DevKit armature and body mesh from your configured DevKit `.blend` file (stored in `Documents/SecondLife/Kits/`).
- **Second Life Shape XML Integration**: Detects and applies `*_shape.xml` files directly, deforming both the avatar body and clothing pieces simultaneously.
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

## Hybrid Avatar & Item Shaping Architecture

Second Life avatars combine disparate mesh technologies: mesh bodies (e.g., eBODY Reborn, Kupra), Bento facial meshes with baked Collada bind matrices (LeLutka EvoX, Genus), rigged hair, rigged clothing items (catsuits, corsets, boots, gloves), and unrigged static accessories.

Standard Avastar slider deformation (`avastar.import_shape`) modifies edit bones in rest pose and mutates vertex positions directly. However:
1. **Bento heads** with non-identity bind scales ($S_{\text{bind}} \neq 1.0$) undergo double-deformation and skull crushing under Avastar.
2. **Clothing items** imported *after* the shape pass remain at factory zero-slider dimensions because the armature modifier sees no pose displacement at rest.
3. **Rigged hair** can suffer vertical displacement hacks or unweighted distortion.
4. **Unrigged meshes** must never receive shape deformation.

The add-on implements an automated **Hybrid Multi-Pass Pipeline**:

```
[Import Selected Items (.dae)]
             │
             ▼
[Bind Items to DevKit Armature]
             │
             ▼
[Classify Meshes via should_shield_from_avastar()]
    │                                         │
    ├─────────────────────────────┐           │
    ▼                             ▼           ▼
[Shielded: Bento Face]    [Shielded: Hair] [Rigged Clothing & Body]
(Detach parent & mod)     (Detach mod)      (Attached to rig)
                                              │
                                              ▼
                                   [Avastar Shape Pass]
                                   - Shapes rest bones
                                   - Morphs body mesh
                                   - Morphs rigged clothing!
                                              │
                                              ▼
                                   [Measure Delta Z Neck Seam]
                                              │
                                              ▼
                                   [Restore Shielded Meshes]
                                              │
                                              ▼
                                   [1:1 SL Bento Face Engine]
                                   - Effective scale: S_eff = S_shape / S_bind
                                   - Neck anchor: X, Y *= S_eff (tracks neck thickness slider)
                                   - Vertical seam: Z += Delta Z_neck (locks seam height)
                                              │
                                              ▼
                                   [1:1 SL Bone Hair Engine]
                                   - FK position & head scale
                                   - Non-destructive shape key
```

### 4-Way Mesh Classification (`should_shield_from_avastar`)

| Classification | Vertex Weight Signature | Pipeline Treatment |
| :--- | :--- | :--- |
| **Bento Facial Features** | Weights on `mFace*` (e.g. `mFaceNoseCenter`, `mFaceChin`) and NO torso/limb weights | **Shielded from Avastar**. Shaped by 1:1 SL Bento Face Engine using Collada inverse bind scale inversion ($S_{\text{eff}} = S_{\text{shape}} / S_{\text{bind}}$), horizontal neck thickness scaling tracking $S_{\text{eff}}$, and vertical neck seam anchoring. |
| **Rigged Hair & Head Attachments** | Weights on head attachment bones (`mHead`, `HEAD`, `mSkull`, `mFaceRoot`) and no Bento facial feature weights (`mFace*`) | **Shielded from Avastar**. Shaped by 1:1 SL Bone Hair Engine using FK translation and scale from shape XML into a non-destructive `SL_Avatar_Shape` shape key. Hair strand weights on upper torso/back do not cause hair to leak into Avastar sliders. |
| **Unrigged Static Meshes** | 0 vertex groups (bangs, glasses, earrings) | **Shielded from all shaping**. Preserved as static objects. |
| **Rigged Body Clothing & Outfit Items** | Weights on `mPelvis`, `mTorso`, limbs, or collision volumes (`BELLY`, `CHEST`, `UPPER_BACK`, `L/R_CLAVICLE`) | **Not shielded (Avastar shaped)**. Bound to rig before Avastar's slider pass so clothing, catsuits, and accessories (e.g. collars/chokers with incidental `mFaceJaw` weights) scale and morph seamlessly to body contours. |

### Universal Body Isolation & Visibility (`setup_devkit_visibility`)

Modern Second Life DevKits and multi-part avatar exports bundle multiple mesh permutations within the same file (primary bodies, alternate breast/deformer variations, alternate flat/mid/high feet, hand poses, custom shape deformers, and rig bone widgets).

The add-on automatically identifies the primary body mesh across all body brands (Maitreya Lara/LaraX, Legacy, Kupra, eBODY Reborn, Belleza Gen.X/Jake, Inithium, Slink, Erika, Prima, StarMesh, or unbranded bodies) and enforces clean visibility by setting both `obj.hide_viewport = True` and `obj.hide_render = True` across bone custom shape widgets (`WGT_`, `cs_`), collision hulls, and alternate cut variations. This prevents alternate geometries from rendering on top of the base body in Cycles/EEVEE and causing clipping or z-fighting through rigged clothing.

---

## Directory Organization

The suite utilizes clean, dynamic folders in your **Documents** directory (completely decoupled from any hardcoded username):

```text
Documents/
└── SecondLife/
    ├── Kits/                          # Avastar DevKit .blend files (Maitreya, Legacy, Kupra, Reborn, etc.)
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
- **DevKit Status**: Shows active armature and Avastar status. Includes options to **Auto-Append Rig**, **Load Body Mesh**, **Load with Custom Shape**, and **Create Armature-Only DevKit**.
- **Import DevKit Alone**: Click **Import DevKit Alone** (or **Import DevKit (Custom Shape)**) to import the DevKit armature and body mesh into your scene without needing to load any outfit items.
- **Custom Shape Toggle**: Enable **Load with Custom Shape** to pick any Second Life shape XML file (`.xml`). When enabled, the DevKit (and any loaded items) will be deformed to your custom shape. When disabled, the DevKit loads in its default neutral shape.
- **Folder**: Select an outfit folder or single-item folder.
- **Checklist**: Check the items you wish to load, or click **Select All**.
- **DevKit Body Toggle**: Toggle **Load DevKit Body** on or off. When disabled, the importer binds items directly to the armature only without loading the avatar body mesh or helper geometry.
- Click **Load Selected (Armature Only)** or **Load Selected onto DevKit Body**.
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

### Packaging & Local Live Deployment

```powershell
# Build dual distribution packages in dist/
python scripts/build_packages.py

# Build and automatically sync to active Blender 3.6 & 5.2 user directories
python scripts/deploy_to_blender.py
```

---

## License

Licensed under the [MIT License](LICENSE).
