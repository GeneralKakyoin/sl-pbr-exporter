"""Modular Second Life Animation Deformer Generator.

Generates upload-ready Second Life .anim (v1.0 binary) and .bvh deformation animations
across all 7 avatar anatomical regions (16 modular channels):
  1. thighs: Thigh_Gap, Thigh_Volume, Thigh_Length
  2. butt: Butt_Lift, Butt_Volume
  3. waist: Belly_Pooch, Hip_Dips, Waist_Cinch
  4. breasts: Breast_Cleavage, Breast_PushUp, Breast_Volume
  5. calves: Calf_Girth, Ankle_Thin
  6. shoulders: Shoulder_Width, Shoulder_Slope
  7. posture: Runway_Arch

Ensures 100% modularity so channels operate independently without AO standing/walking conflicts.
"""

from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    from .anim_writer import (
        SLAnimWriter,
        euler_deg_to_quat,
        quat_to_vec3,
    )
except ImportError:
    from anim_writer import (
        SLAnimWriter,
        euler_deg_to_quat,
        quat_to_vec3,
    )

# Standard duration for a 2-frame static loop at 30 fps
DEFAULT_DURATION = 0.0666667
DEFAULT_FPS = 30.0
DEFAULT_PRIORITY = 5


@dataclass
class ChannelSpec:
    """Specification for an animation deformer channel."""
    name: str              # e.g. "Thigh_Gap"
    category: str          # "position", "rotation", "scale"
    axis: str              # Axis descriptor
    folder: str            # Subdirectory name
    unit: str              # "meters" or "degrees"
    snap_default: float    # Snap value per step
    description: str       # Human-readable explanation


# Master 7-region configuration (16 independent deformation channels)
REGIONS_CONFIG: Dict[str, List[ChannelSpec]] = {
    "thighs": [
        ChannelSpec("Thigh_Gap", "position", "Y", "thigh_gap", "meters", 0.005, "Lateral thigh gap on mHipLeft/mHipRight"),
        ChannelSpec("Thigh_Volume", "scale", "Vol", "thigh_volume", "meters", 0.005, "Thigh fullness on L_UPPER_LEG/R_UPPER_LEG"),
        ChannelSpec("Thigh_Length", "scale", "Len", "thigh_length", "meters", 0.005, "Leg lengthening on mKneeLeft/mKneeRight"),
    ],
    "butt": [
        ChannelSpec("Butt_Lift", "position", "Lift", "butt_lift", "meters", 0.005, "45-deg diagonal shelf lift on BUTT"),
        ChannelSpec("Butt_Volume", "scale", "Vol", "butt_volume", "meters", 0.005, "Posterior depth fullness on BUTT"),
    ],
    "waist": [
        ChannelSpec("Belly_Pooch", "position", "X", "belly_pooch", "meters", 0.005, "Abdomen depth on BELLY"),
        ChannelSpec("Hip_Dips", "position", "Flare", "hip_dips", "meters", 0.005, "High-hip flare on LEFT_HANDLE/RIGHT_HANDLE"),
        ChannelSpec("Waist_Cinch", "scale", "Cinch", "waist_cinch", "meters", 0.005, "Corset cinch on LEFT_HANDLE/RIGHT_HANDLE/BELLY"),
    ],
    "breasts": [
        ChannelSpec("Breast_Cleavage", "position", "Cleavage", "breast_cleavage", "meters", 0.005, "Cleavage squeeze on LEFT_PEC/RIGHT_PEC"),
        ChannelSpec("Breast_PushUp", "position", "PushUp", "breast_pushup", "meters", 0.005, "Push-up lift + forward projection on LEFT_PEC/RIGHT_PEC"),
        ChannelSpec("Breast_Volume", "scale", "Vol", "breast_volume", "meters", 0.005, "Cup volume fullness on LEFT_PEC/RIGHT_PEC"),
    ],
    "calves": [
        ChannelSpec("Calf_Girth", "scale", "Vol", "calf_girth", "meters", 0.005, "Calf muscle fullness on L_LOWER_LEG/R_LOWER_LEG"),
        ChannelSpec("Ankle_Thin", "position", "Taper", "ankle_thin", "meters", 0.005, "Inward ankle taper on mAnkleLeft/mAnkleRight"),
    ],
    "shoulders": [
        ChannelSpec("Shoulder_Width", "position", "Width", "shoulder_width", "meters", 0.005, "Collarbone width on mCollarLeft/mCollarRight"),
        ChannelSpec("Shoulder_Slope", "position", "Slope", "shoulder_slope", "meters", 0.005, "Relaxed slope on mCollarLeft/mCollarRight"),
    ],
    "posture": [
        ChannelSpec("Runway_Arch", "rotation", "Pitch", "runway_arch", "degrees", 2.5, "S-curve spine pitch arch on mTorso"),
    ],
}

# Legacy THIGH_CHANNELS mapping for backwards compatibility with tests
THIGH_CHANNELS: List[ChannelSpec] = [
    ChannelSpec("Thigh_Pos_X", "position", "X", "position_x", "meters", 0.005, "Anterior / Posterior displacement"),
    ChannelSpec("Thigh_Pos_Y", "position", "Y", "position_y", "meters", 0.005, "Lateral / Thigh Gap"),
    ChannelSpec("Thigh_Pos_Z", "position", "Z", "position_z", "meters", 0.005, "Vertical / Height displacement"),
    ChannelSpec("Thigh_Rot_X", "rotation", "X", "rotation_x", "degrees", 5.0, "Roll / Tilt"),
    ChannelSpec("Thigh_Rot_Y", "rotation", "Y", "rotation_y", "degrees", 5.0, "Pitch / Swing"),
    ChannelSpec("Thigh_Rot_Z", "rotation", "Z", "rotation_z", "degrees", 5.0, "Yaw / Turn-out"),
    ChannelSpec("Thigh_Scale_Vol", "scale", "Vol", "scale_volume", "meters", 0.005, "Fitted Mesh Thickness / Volume"),
    ChannelSpec("Thigh_Scale_Len", "scale", "Len", "scale_length", "meters", 0.005, "Thigh Length (Knee offset)"),
]


class DeformerAnimGenerator:
    """Batch generator for modular Second Life deformation animations."""

    def __init__(
        self,
        region: str = "all",
        num_steps: int = 10,
        pos_snap: float = 0.005,      # 5mm per step
        rot_snap: float = 2.5,        # 2.5 degrees per step
        scale_snap: float = 0.005,    # 5mm collision bone delta per step
        priority: int = DEFAULT_PRIORITY,
        duration: float = DEFAULT_DURATION,
        fps: float = DEFAULT_FPS
    ):
        self.region = region.lower()
        self.num_steps = max(1, int(num_steps))
        self.pos_snap = float(pos_snap)
        self.rot_snap = float(rot_snap)
        self.scale_snap = float(scale_snap)
        self.priority = int(priority)
        self.duration = float(duration)
        self.fps = float(fps)

        valid_regions = set(REGIONS_CONFIG.keys()) | {"all"}
        if self.region not in valid_regions:
            raise ValueError(
                f"Unknown region '{region}'. Valid regions are: {', '.join(sorted(valid_regions))}"
            )

    def _build_joint_transforms(
        self,
        region: str,
        channel_name: str,
        val: float
    ) -> Tuple[List[Dict[str, Any]], Dict[str, Tuple[float, float, float]]]:
        """
        Build joint data and optional BVH rotations for a given region channel.

        Returns:
            (joints_data_for_anim, bvh_joint_rotations_deg)
        """
        joints: List[Dict[str, Any]] = []
        bvh_rotations: Dict[str, Tuple[float, float, float]] = {}

        # -------------------------------------------------------------
        # 1. THIGHS
        # -------------------------------------------------------------
        if region == "thighs":
            if channel_name in ("Thigh_Gap", "position_y", "Pos_Y"):
                # Lateral displacement: Left +Y, Right -Y
                pos_l = (0.0, val, 0.0)
                pos_r = (0.0, -val, 0.0)
                joints.append(self._make_pos_joint("mHipLeft", pos_l))
                joints.append(self._make_pos_joint("mHipRight", pos_r))

            elif channel_name in ("Thigh_Volume", "scale_vol", "Scale_Vol"):
                # Upper leg thickness collision bones: lateral + anterior (50%)
                pos_l = (val * 0.5, val, 0.0)
                pos_r = (val * 0.5, -val, 0.0)
                joints.append(self._make_pos_joint("L_UPPER_LEG", pos_l))
                joints.append(self._make_pos_joint("R_UPPER_LEG", pos_r))

            elif channel_name in ("Thigh_Length", "scale_len", "Scale_Len"):
                # Upper leg length: shift knees down (-Z)
                pos_l = (0.0, 0.0, -val)
                pos_r = (0.0, 0.0, -val)
                joints.append(self._make_pos_joint("mKneeLeft", pos_l))
                joints.append(self._make_pos_joint("mKneeRight", pos_r))

            # Legacy axes for test backwards compatibility
            elif channel_name in ("Thigh_Pos_X", "position_x", "Pos_X"):
                pos = (val, 0.0, 0.0)
                joints.append(self._make_pos_joint("mHipLeft", pos))
                joints.append(self._make_pos_joint("mHipRight", pos))

            elif channel_name in ("Thigh_Pos_Z", "position_z", "Pos_Z"):
                pos = (0.0, 0.0, val)
                joints.append(self._make_pos_joint("mHipLeft", pos))
                joints.append(self._make_pos_joint("mHipRight", pos))

            elif channel_name in ("Thigh_Rot_X", "rotation_x", "Rot_X"):
                rot_l = (val, 0.0, 0.0)
                rot_r = (-val, 0.0, 0.0)
                bvh_rotations["mHipLeft"] = rot_l
                bvh_rotations["mHipRight"] = rot_r
                joints.append(self._make_rot_joint("mHipLeft", rot_l))
                joints.append(self._make_rot_joint("mHipRight", rot_r))

            elif channel_name in ("Thigh_Rot_Y", "rotation_y", "Rot_Y"):
                rot_l = (0.0, val, 0.0)
                rot_r = (0.0, val, 0.0)
                bvh_rotations["mHipLeft"] = rot_l
                bvh_rotations["mHipRight"] = rot_r
                joints.append(self._make_rot_joint("mHipLeft", rot_l))
                joints.append(self._make_rot_joint("mHipRight", rot_r))

            elif channel_name in ("Thigh_Rot_Z", "rotation_z", "Rot_Z"):
                rot_l = (0.0, 0.0, val)
                rot_r = (0.0, 0.0, -val)
                bvh_rotations["mHipLeft"] = rot_l
                bvh_rotations["mHipRight"] = rot_r
                joints.append(self._make_rot_joint("mHipLeft", rot_l))
                joints.append(self._make_rot_joint("mHipRight", rot_r))

            else:
                raise ValueError(f"Unknown channel '{channel_name}' for region 'thighs'")

        # -------------------------------------------------------------
        # 2. BUTT
        # -------------------------------------------------------------
        elif region == "butt":
            if channel_name == "Butt_Lift":
                # 45-deg diagonal shelf: posterior (-X) and vertical (+Z)
                # In SL avatar coords: -X is posterior, +Z is superior
                diag = val * 0.70710678
                pos = (-diag, 0.0, diag)
                joints.append(self._make_pos_joint("BUTT", pos))

            elif channel_name == "Butt_Volume":
                # Posterior depth fullness on BUTT collision bone (-X)
                pos = (-val, 0.0, 0.0)
                joints.append(self._make_pos_joint("BUTT", pos))

            else:
                raise ValueError(f"Unknown channel '{channel_name}' for region 'butt'")

        # -------------------------------------------------------------
        # 3. WAIST
        # -------------------------------------------------------------
        elif region == "waist":
            if channel_name == "Belly_Pooch":
                # Abdomen depth on BELLY (+X anterior)
                pos = (val, 0.0, 0.0)
                joints.append(self._make_pos_joint("BELLY", pos))

            elif channel_name == "Hip_Dips":
                # High-hip flare on LEFT_HANDLE (+Y) and RIGHT_HANDLE (-Y)
                joints.append(self._make_pos_joint("LEFT_HANDLE", (0.0, val, 0.0)))
                joints.append(self._make_pos_joint("RIGHT_HANDLE", (0.0, -val, 0.0)))

            elif channel_name == "Waist_Cinch":
                # Corset compression: narrow handles (-Y Left, +Y Right) and flatten belly (-X)
                joints.append(self._make_pos_joint("LEFT_HANDLE", (0.0, -val, 0.0)))
                joints.append(self._make_pos_joint("RIGHT_HANDLE", (0.0, val, 0.0)))
                joints.append(self._make_pos_joint("BELLY", (-val * 0.5, 0.0, 0.0)))

            else:
                raise ValueError(f"Unknown channel '{channel_name}' for region 'waist'")

        # -------------------------------------------------------------
        # 4. BREASTS
        # -------------------------------------------------------------
        elif region == "breasts":
            if channel_name == "Breast_Cleavage":
                # Squeeze inward: LEFT_PEC moves -Y, RIGHT_PEC moves +Y
                joints.append(self._make_pos_joint("LEFT_PEC", (0.0, -val, 0.0)))
                joints.append(self._make_pos_joint("RIGHT_PEC", (0.0, val, 0.0)))

            elif channel_name == "Breast_PushUp":
                # 45-deg lift (+Z) and forward projection (+X)
                diag = val * 0.70710678
                pos = (diag, 0.0, diag)
                joints.append(self._make_pos_joint("LEFT_PEC", pos))
                joints.append(self._make_pos_joint("RIGHT_PEC", pos))

            elif channel_name == "Breast_Volume":
                # Fullness: forward (+X) + slight lateral (+Y Left, -Y Right)
                joints.append(self._make_pos_joint("LEFT_PEC", (val, val * 0.5, 0.0)))
                joints.append(self._make_pos_joint("RIGHT_PEC", (val, -val * 0.5, 0.0)))

            else:
                raise ValueError(f"Unknown channel '{channel_name}' for region 'breasts'")

        # -------------------------------------------------------------
        # 5. CALVES
        # -------------------------------------------------------------
        elif region == "calves":
            if channel_name == "Calf_Girth":
                # Calf muscle bulge: posterior (-X) + lateral width (+Y Left, -Y Right)
                joints.append(self._make_pos_joint("L_LOWER_LEG", (-val, val * 0.5, 0.0)))
                joints.append(self._make_pos_joint("R_LOWER_LEG", (-val, -val * 0.5, 0.0)))

            elif channel_name == "Ankle_Thin":
                # Ankle taper: inward towards midline (-Y Left, +Y Right)
                joints.append(self._make_pos_joint("mAnkleLeft", (0.0, -val, 0.0)))
                joints.append(self._make_pos_joint("mAnkleRight", (0.0, val, 0.0)))

            else:
                raise ValueError(f"Unknown channel '{channel_name}' for region 'calves'")

        # -------------------------------------------------------------
        # 6. SHOULDERS
        # -------------------------------------------------------------
        elif region == "shoulders":
            if channel_name == "Shoulder_Width":
                # Collarbone narrow width: inward towards neck (-Y Left, +Y Right)
                joints.append(self._make_pos_joint("mCollarLeft", (0.0, -val, 0.0)))
                joints.append(self._make_pos_joint("mCollarRight", (0.0, val, 0.0)))

            elif channel_name == "Shoulder_Slope":
                # Downward relaxed slope: lower collarbones along -Z
                joints.append(self._make_pos_joint("mCollarLeft", (0.0, 0.0, -val)))
                joints.append(self._make_pos_joint("mCollarRight", (0.0, 0.0, -val)))

            else:
                raise ValueError(f"Unknown channel '{channel_name}' for region 'shoulders'")

        # -------------------------------------------------------------
        # 7. POSTURE
        # -------------------------------------------------------------
        elif region == "posture":
            if channel_name == "Runway_Arch":
                # S-curve lower spine pitch rotation around Y on mTorso
                rot_deg = (0.0, val, 0.0)
                bvh_rotations["mTorso"] = rot_deg
                joints.append(self._make_rot_joint("mTorso", rot_deg))

            else:
                raise ValueError(f"Unknown channel '{channel_name}' for region 'posture'")

        else:
            raise ValueError(f"Unknown region '{region}'")

        return joints, bvh_rotations

    def _make_pos_joint(self, bone_name: str, pos: Tuple[float, float, float]) -> Dict[str, Any]:
        """Create a joint dict with 0 rotation keys and 2 static position keys."""
        return {
            "name": bone_name,
            "priority": self.priority,
            "rot_keys": [],
            "pos_keys": [
                (0.0, pos),
                (self.duration, pos)
            ]
        }

    def _make_rot_joint(self, bone_name: str, rot_deg: Tuple[float, float, float]) -> Dict[str, Any]:
        """Create a joint dict with 0 position keys and 2 static rotation keys."""
        q = euler_deg_to_quat(*rot_deg)
        v = quat_to_vec3(*q)
        return {
            "name": bone_name,
            "priority": self.priority,
            "rot_keys": [
                (0.0, v),
                (self.duration, v)
            ],
            "pos_keys": []
        }

    # Backward compatibility helper for existing test suite
    def _build_thigh_joints(
        self,
        category: str,
        axis: str,
        val: float
    ) -> Tuple[List[Dict[str, Any]], Dict[str, Tuple[float, float, float]]]:
        """Legacy helper maintaining exact compatibility with earlier thigh unit tests."""
        key = f"{category}_{axis}".lower()
        return self._build_joint_transforms("thighs", key, val)

    def generate_all(
        self,
        output_dir: str | Path,
        export_bvh: bool = True
    ) -> Dict[str, Any]:
        """
        Generate all modular animation steps for the configured region(s).

        Outputs:
            - .anim binary files (upload ready)
            - .bvh text files (for rotation channels)
            - manifest.json
            - modular LSL HUD scripts
        """
        out_path = Path(output_dir)
        out_path.mkdir(parents=True, exist_ok=True)

        target_regions = list(REGIONS_CONFIG.keys()) if self.region == "all" else [self.region]

        manifest: Dict[str, Any] = {
            "region": self.region,
            "target_regions": target_regions,
            "priority": self.priority,
            "duration": self.duration,
            "fps": self.fps,
            "num_steps": self.num_steps,
            "pos_snap": self.pos_snap,
            "rot_snap": self.rot_snap,
            "scale_snap": self.scale_snap,
            "channels": {},
            "generated_files": []
        }

        total_files = 0
        all_channel_specs: List[Tuple[str, ChannelSpec]] = []

        for r_name in target_regions:
            region_folder = out_path if len(target_regions) == 1 else out_path / r_name
            region_folder.mkdir(parents=True, exist_ok=True)

            channels = REGIONS_CONFIG[r_name]
            for ch in channels:
                all_channel_specs.append((r_name, ch))
                ch_folder = region_folder / ch.folder
                ch_folder.mkdir(parents=True, exist_ok=True)

                if ch.category == "position":
                    snap = self.pos_snap
                elif ch.category == "rotation":
                    snap = self.rot_snap
                else:
                    snap = self.scale_snap

                channel_key = ch.name.lower()
                manifest["channels"][channel_key] = {
                    "name": ch.name,
                    "region": r_name,
                    "category": ch.category,
                    "axis": ch.axis,
                    "unit": ch.unit,
                    "snap": snap,
                    "description": ch.description,
                    "steps": []
                }

                step_ranges = [(1, self.num_steps + 1, "p", 1.0), (1, self.num_steps + 1, "m", -1.0)]

                for start, end, prefix, sign in step_ranges:
                    for step_idx in range(start, end):
                        val = step_idx * snap * sign
                        step_name = f"{ch.name}_{prefix}{step_idx:02d}"

                        joints, bvh_rots = self._build_joint_transforms(r_name, ch.name, val)

                        # 1. Write binary .anim
                        anim_bytes = SLAnimWriter.serialize_anim(
                            joints=joints,
                            duration=self.duration,
                            base_priority=self.priority,
                            loop=True,
                            ease_in=0.0,
                            ease_out=0.0
                        )
                        anim_file = ch_folder / f"{step_name}.anim"
                        with open(anim_file, "wb") as f:
                            f.write(anim_bytes)
                        total_files += 1

                        step_info: Dict[str, Any] = {
                            "name": step_name,
                            "step_index": step_idx if sign > 0 else -step_idx,
                            "value": round(val, 6),
                            "file_anim": str(anim_file.relative_to(out_path)),
                        }

                        # 2. Write BVH companion if requested
                        if export_bvh and ch.category == "rotation" and bvh_rots:
                            bvh_text = SLAnimWriter.serialize_bvh(bvh_rots, fps=self.fps, num_frames=2)
                            bvh_file = ch_folder / f"{step_name}.bvh"
                            with open(bvh_file, "w", encoding="utf-8") as f:
                                f.write(bvh_text)
                            step_info["file_bvh"] = str(bvh_file.relative_to(out_path))
                            total_files += 1

                        manifest["channels"][channel_key]["steps"].append(step_info)
                        manifest["generated_files"].append(str(anim_file.relative_to(out_path)))

        # 3. Write manifest.json
        manifest_file = out_path / "manifest.json"
        with open(manifest_file, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2)

        # 4. Generate Master / Region LSL HUD script
        if self.region == "all":
            lsl_script = self._generate_master_lsl_hud_script(all_channel_specs)
            lsl_file = out_path / "master_deformer_hud.lsl"
        else:
            lsl_script = self._generate_region_lsl_hud_script(self.region, REGIONS_CONFIG[self.region])
            lsl_file = out_path / f"{self.region}_deformer_hud.lsl"

        with open(lsl_file, "w", encoding="utf-8") as f:
            f.write(lsl_script)

        # Also generate modular_deformer_hud.lsl for thigh backwards compatibility
        if self.region in ("thighs", "all"):
            thigh_script = self._generate_region_lsl_hud_script("thighs", REGIONS_CONFIG["thighs"])
            legacy_lsl = (out_path if self.region == "thighs" else out_path / "thighs") / "modular_deformer_hud.lsl"
            with open(legacy_lsl, "w", encoding="utf-8") as f:
                f.write(thigh_script)

        manifest["total_files_generated"] = total_files
        manifest["manifest_file"] = str(manifest_file)
        manifest["lsl_script"] = str(lsl_file)

        return manifest

    def _generate_region_lsl_hud_script(self, region_name: str, channels: List[ChannelSpec]) -> str:
        """Generate a focused LSL HUD script for a single body region."""
        ch_names_lsl = ", ".join(f'"{c.name}"' for c in channels)
        empty_anims_lsl = ", ".join('""' for _ in channels)
        zero_indices_lsl = ", ".join('0' for _ in channels)
        num_ch = len(channels)

        ch_buttons_lsl = ", ".join(f'"{c.name}"' for c in channels)

        return f"""// ==============================================================================
// Second Life Avatar Deformer HUD - Region: {region_name.upper()}
// Fully modular Priority {self.priority} looped deformer animation player.
// ==============================================================================

integer CHANNEL_DIALOG = -884422;
integer gListener;
key gOwner;

list gChannelNames = [{ch_names_lsl}];
list gActiveAnims = [{empty_anims_lsl}];
list gStepIndices = [{zero_indices_lsl}];

integer gCurrentChannel = 0;
integer MAX_STEPS = {self.num_steps};

string getAnimName(integer ch_idx, integer step) {{
    if (step == 0) return "";
    string ch = llList2String(gChannelNames, ch_idx);
    string prefix = "p";
    if (step < 0) {{
        prefix = "m";
        step = -step;
    }}
    string sStep = (string)step;
    if (step < 10) sStep = "0" + sStep;
    return ch + "_" + prefix + sStep;
}}

setChannelStep(integer ch_idx, integer new_step) {{
    if (new_step > MAX_STEPS) new_step = MAX_STEPS;
    if (new_step < -MAX_STEPS) new_step = -MAX_STEPS;
    
    integer old_step = llList2Integer(gStepIndices, ch_idx);
    if (old_step == new_step) return;
    
    string old_anim = llList2String(gActiveAnims, ch_idx);
    string new_anim = getAnimName(ch_idx, new_step);
    
    if (old_anim != "" && llGetInventoryType(old_anim) == INVENTORY_ANIMATION) {{
        llStopAnimation(old_anim);
    }}
    if (new_anim != "" && llGetInventoryType(new_anim) == INVENTORY_ANIMATION) {{
        llStartAnimation(new_anim);
    }}
    
    gActiveAnims = llListReplaceList(gActiveAnims, [new_anim], ch_idx, ch_idx);
    gStepIndices = llListReplaceList(gStepIndices, [new_step], ch_idx, ch_idx);
    
    llOwnerSay("{region_name.title()} [" + llList2String(gChannelNames, ch_idx) + "] -> Step " + (string)new_step);
}}

resetAll() {{
    integer i;
    for (i = 0; i < {num_ch}; ++i) {{
        string anim = llList2String(gActiveAnims, i);
        if (anim != "" && llGetInventoryType(anim) == INVENTORY_ANIMATION) {{
            llStopAnimation(anim);
        }}
    }}
    gActiveAnims = [{empty_anims_lsl}];
    gStepIndices = [{zero_indices_lsl}];
    llOwnerSay("All {region_name.title()} deformers reset to skeleton default.");
}}

showMenu() {{
    string ch_name = llList2String(gChannelNames, gCurrentChannel);
    integer current_step = llList2Integer(gStepIndices, gCurrentChannel);
    
    string text = "\\n=== {region_name.upper()} DEFORMER HUD ===\\n" +
                  "Channel: [" + ch_name + "]\\n" +
                  "Active Step: " + (string)current_step + " / " + (string)MAX_STEPS + "\\n\\n" +
                  "Select an action or switch channel:";
                  
    list buttons = [
        "- Step", "Reset Ch", "+ Step",
        "- 5", "Step 0", "+ 5",
        "Select Ch", "Reset All", "Close"
    ];
    llDialog(gOwner, text, buttons, CHANNEL_DIALOG);
}}

showChannelMenu() {{
    string text = "\\nSelect {region_name.title()} Channel to Adjust:";
    list buttons = [{ch_buttons_lsl}, "<< Back"];
    llDialog(gOwner, text, buttons, CHANNEL_DIALOG);
}}

default {{
    state_entry() {{
        gOwner = llGetOwner();
        llRequestPermissions(gOwner, PERMISSION_TRIGGER_ANIMATION);
    }}
    
    run_time_permissions(integer perm) {{
        if (perm & PERMISSION_TRIGGER_ANIMATION) {{
            llOwnerSay("{region_name.title()} Deformer HUD ready. Touch to open controls.");
        }}
    }}
    
    attach(key id) {{
        if (id != NULL_KEY) {{
            gOwner = id;
            llRequestPermissions(gOwner, PERMISSION_TRIGGER_ANIMATION);
        }} else {{
            resetAll();
        }}
    }}
    
    touch_start(integer total_number) {{
        if (llDetectedKey(0) != gOwner) return;
        llListenRemove(gListener);
        CHANNEL_DIALOG = (integer)(llFrand(-999999.0) - 100000.0);
        gListener = llListen(CHANNEL_DIALOG, "", gOwner, "");
        showMenu();
    }}
    
    listen(integer channel, string name, key id, string msg) {{
        if (id != gOwner) return;
        
        if (msg == "Close") {{
            llListenRemove(gListener);
            return;
        }}
        else if (msg == "+ Step") {{
            integer cur = llList2Integer(gStepIndices, gCurrentChannel);
            setChannelStep(gCurrentChannel, cur + 1);
            showMenu();
        }}
        else if (msg == "- Step") {{
            integer cur = llList2Integer(gStepIndices, gCurrentChannel);
            setChannelStep(gCurrentChannel, cur - 1);
            showMenu();
        }}
        else if (msg == "+ 5") {{
            integer cur = llList2Integer(gStepIndices, gCurrentChannel);
            setChannelStep(gCurrentChannel, cur + 5);
            showMenu();
        }}
        else if (msg == "- 5") {{
            integer cur = llList2Integer(gStepIndices, gCurrentChannel);
            setChannelStep(gCurrentChannel, cur - 5);
            showMenu();
        }}
        else if (msg == "Reset Ch" || msg == "Step 0") {{
            setChannelStep(gCurrentChannel, 0);
            showMenu();
        }}
        else if (msg == "Reset All") {{
            resetAll();
            showMenu();
        }}
        else if (msg == "Select Ch") {{
            showChannelMenu();
        }}
        else if (msg == "<< Back") {{
            showMenu();
        }}
        else {{
            integer idx = llListFindList(gChannelNames, [msg]);
            if (idx != -1) {{
                gCurrentChannel = idx;
                showMenu();
            }}
        }}
    }}
}}
"""

    def _generate_master_lsl_hud_script(self, channel_specs: List[Tuple[str, ChannelSpec]]) -> str:
        """Generate a master multi-region LSL HUD script controlling all 16 channels."""
        region_names = list(REGIONS_CONFIG.keys())
        reg_buttons_lsl = ", ".join(f'"{r.title()}"' for r in region_names)
        
        all_ch_names = [ch.name for _, ch in channel_specs]
        ch_names_lsl = ", ".join(f'"{name}"' for name in all_ch_names)
        empty_anims_lsl = ", ".join('""' for _ in all_ch_names)
        zero_indices_lsl = ", ".join('0' for _ in all_ch_names)
        num_ch = len(all_ch_names)

        return f"""// ==============================================================================
// Second Life Master Multi-Region Deformer HUD Script
// Supports all 7 Anatomical Regions & 16 Modular Channels:
// Thighs, Butt, Waist, Breasts, Calves, Shoulders, Posture
// Looped Priority {self.priority} Deformations Running Additively.
// ==============================================================================

integer CHANNEL_DIALOG = -885533;
integer gListener;
key gOwner;

list gRegions = [{reg_buttons_lsl}];
list gChannelNames = [{ch_names_lsl}];
list gActiveAnims = [{empty_anims_lsl}];
list gStepIndices = [{zero_indices_lsl}];

// Region channel ranges
// 0: Thighs (0-2), 1: Butt (3-4), 2: Waist (5-7), 3: Breasts (8-10)
// 4: Calves (11-12), 5: Shoulders (13-14), 6: Posture (15)
list gRegionStart = [0, 3, 5, 8, 11, 13, 15];
list gRegionCount = [3, 2, 3, 3, 2, 2, 1];

integer gCurrentRegion = 0;
integer gCurrentChannel = 0;
integer MAX_STEPS = {self.num_steps};

string getAnimName(integer ch_idx, integer step) {{
    if (step == 0) return "";
    string ch = llList2String(gChannelNames, ch_idx);
    string prefix = "p";
    if (step < 0) {{
        prefix = "m";
        step = -step;
    }}
    string sStep = (string)step;
    if (step < 10) sStep = "0" + sStep;
    return ch + "_" + prefix + sStep;
}}

setChannelStep(integer ch_idx, integer new_step) {{
    if (new_step > MAX_STEPS) new_step = MAX_STEPS;
    if (new_step < -MAX_STEPS) new_step = -MAX_STEPS;
    
    integer old_step = llList2Integer(gStepIndices, ch_idx);
    if (old_step == new_step) return;
    
    string old_anim = llList2String(gActiveAnims, ch_idx);
    string new_anim = getAnimName(ch_idx, new_step);
    
    if (old_anim != "" && llGetInventoryType(old_anim) == INVENTORY_ANIMATION) {{
        llStopAnimation(old_anim);
    }}
    if (new_anim != "" && llGetInventoryType(new_anim) == INVENTORY_ANIMATION) {{
        llStartAnimation(new_anim);
    }}
    
    gActiveAnims = llListReplaceList(gActiveAnims, [new_anim], ch_idx, ch_idx);
    gStepIndices = llListReplaceList(gStepIndices, [new_step], ch_idx, ch_idx);
    
    llOwnerSay("[" + llList2String(gChannelNames, ch_idx) + "] -> Step " + (string)new_step);
}}

resetAll() {{
    integer i;
    for (i = 0; i < {num_ch}; ++i) {{
        string anim = llList2String(gActiveAnims, i);
        if (anim != "" && llGetInventoryType(anim) == INVENTORY_ANIMATION) {{
            llStopAnimation(anim);
        }}
    }}
    gActiveAnims = [{empty_anims_lsl}];
    gStepIndices = [{zero_indices_lsl}];
    llOwnerSay("All 16 deformer channels reset to skeleton default.");
}}

showMainMenu() {{
    string text = "\\n=== MASTER AVATAR DEFORMER ===\\n" +
                  "Select an anatomical region to adjust:";
    list buttons = [
        "Thighs", "Butt", "Waist",
        "Breasts", "Calves", "Shoulders",
        "Posture", "Reset All", "Close"
    ];
    llDialog(gOwner, text, buttons, CHANNEL_DIALOG);
}}

showRegionMenu(integer reg_idx) {{
    gCurrentRegion = reg_idx;
    string reg_name = llList2String(gRegions, reg_idx);
    integer start = llList2Integer(gRegionStart, reg_idx);
    integer count = llList2Integer(gRegionCount, reg_idx);
    
    string text = "\\n=== " + llToUpper(reg_name) + " CHANNELS ===\\n" +
                  "Select a channel to sculpt:";
                  
    list buttons = [];
    integer i;
    for (i = 0; i < count; ++i) {{
        buttons += [llList2String(gChannelNames, start + i)];
    }}
    buttons += ["<< Main", "Reset All", "Close"];
    llDialog(gOwner, text, buttons, CHANNEL_DIALOG);
}}

showChannelControl(integer ch_idx) {{
    gCurrentChannel = ch_idx;
    string ch_name = llList2String(gChannelNames, ch_idx);
    integer current_step = llList2Integer(gStepIndices, ch_idx);
    
    string text = "\\n=== CHANNEL: " + ch_name + " ===\\n" +
                  "Active Step: " + (string)current_step + " / " + (string)MAX_STEPS + "\\n\\n" +
                  "Use buttons below to adjust:";
                  
    list buttons = [
        "- Step", "Reset Ch", "+ Step",
        "- 5", "Step 0", "+ 5",
        "<< Region", "Reset All", "Close"
    ];
    llDialog(gOwner, text, buttons, CHANNEL_DIALOG);
}}

default {{
    state_entry() {{
        gOwner = llGetOwner();
        llRequestPermissions(gOwner, PERMISSION_TRIGGER_ANIMATION);
    }}
    
    run_time_permissions(integer perm) {{
        if (perm & PERMISSION_TRIGGER_ANIMATION) {{
            llOwnerSay("Master Deformer HUD ready. Touch HUD to sculpt avatar.");
        }}
    }}
    
    attach(key id) {{
        if (id != NULL_KEY) {{
            gOwner = id;
            llRequestPermissions(gOwner, PERMISSION_TRIGGER_ANIMATION);
        }} else {{
            resetAll();
        }}
    }}
    
    touch_start(integer total_number) {{
        if (llDetectedKey(0) != gOwner) return;
        llListenRemove(gListener);
        CHANNEL_DIALOG = (integer)(llFrand(-999999.0) - 100000.0);
        gListener = llListen(CHANNEL_DIALOG, "", gOwner, "");
        showMainMenu();
    }}
    
    listen(integer channel, string name, key id, string msg) {{
        if (id != gOwner) return;
        
        if (msg == "Close") {{
            llListenRemove(gListener);
            return;
        }}
        else if (msg == "<< Main") {{
            showMainMenu();
        }}
        else if (msg == "<< Region") {{
            showRegionMenu(gCurrentRegion);
        }}
        else if (msg == "+ Step") {{
            integer cur = llList2Integer(gStepIndices, gCurrentChannel);
            setChannelStep(gCurrentChannel, cur + 1);
            showChannelControl(gCurrentChannel);
        }}
        else if (msg == "- Step") {{
            integer cur = llList2Integer(gStepIndices, gCurrentChannel);
            setChannelStep(gCurrentChannel, cur - 1);
            showChannelControl(gCurrentChannel);
        }}
        else if (msg == "+ 5") {{
            integer cur = llList2Integer(gStepIndices, gCurrentChannel);
            setChannelStep(gCurrentChannel, cur + 5);
            showChannelControl(gCurrentChannel);
        }}
        else if (msg == "- 5") {{
            integer cur = llList2Integer(gStepIndices, gCurrentChannel);
            setChannelStep(gCurrentChannel, cur - 5);
            showChannelControl(gCurrentChannel);
        }}
        else if (msg == "Reset Ch" || msg == "Step 0") {{
            setChannelStep(gCurrentChannel, 0);
            showChannelControl(gCurrentChannel);
        }}
        else if (msg == "Reset All") {{
            resetAll();
            showMainMenu();
        }}
        else {{
            // Check if region clicked
            integer r_idx = llListFindList(gRegions, [msg]);
            if (r_idx != -1) {{
                showRegionMenu(r_idx);
                return;
            }}
            
            // Check if channel clicked
            integer c_idx = llListFindList(gChannelNames, [msg]);
            if (c_idx != -1) {{
                showChannelControl(c_idx);
                return;
            }}
        }}
    }}
}}
"""
