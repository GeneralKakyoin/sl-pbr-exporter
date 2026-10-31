"""Modular Second Life Animation Deformer Generator.

Generates upload-ready Second Life .anim (v1.0 binary) and .bvh deformation animations
for avatar body regions (starting with Thighs: Position, Rotation, Scale).
Ensures 100% modularity so Position, Rotation, and Scale channels operate independently.
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
    """Specification for an animation channel."""
    category: str      # 'position', 'rotation', 'scale'
    axis: str          # 'X', 'Y', 'Z', 'Vol', 'Len'
    folder: str        # Subfolder name
    unit: str          # 'meters' or 'degrees'
    snap_default: float


# Definition of safe deformation channels for Thighs (No rotation to preserve AO walking/standing locomotion)
THIGH_CHANNELS: List[ChannelSpec] = [
    ChannelSpec("position", "X", "position_x", "meters", 0.005),       # Anterior / Posterior (5mm / step)
    ChannelSpec("position", "Y", "position_y", "meters", 0.005),       # Lateral / Thigh Gap (5mm / step)
    ChannelSpec("position", "Z", "position_z", "meters", 0.005),       # Vertical / Height (5mm / step)
    ChannelSpec("scale", "Vol", "scale_volume", "meters", 0.005),      # Fitted Mesh Thickness / Volume
    ChannelSpec("scale", "Len", "scale_length", "meters", 0.005),      # Thigh Length (Knee offset)
]


class DeformerAnimGenerator:
    """Batch generator for modular Second Life deformation animations."""

    def __init__(
        self,
        region: str = "thighs",
        num_steps: int = 10,
        pos_snap: float = 0.005,      # 5mm per step
        rot_snap: float = 5.0,        # 5 degrees per step
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

        if self.region != "thighs":
            raise NotImplementedError(f"Region '{region}' not yet supported. Only 'thighs' is available.")

    def _build_thigh_joints(
        self,
        category: str,
        axis: str,
        val: float
    ) -> Tuple[List[Dict[str, Any]], Dict[str, Tuple[float, float, float]]]:
        """
        Build joint data for thigh deformer.
        Returns:
            (joints_data_for_anim, bvh_joint_rotations_deg)
        """
        joints = []
        bvh_rotations = {}

        if category == "position":
            # Target structural bones: mHipLeft and mHipRight
            # Y is mirrored (Left: +Y, Right: -Y for outward gap)
            # X and Z are symmetrical
            if axis == "X":
                pos_l = (val, 0.0, 0.0)
                pos_r = (val, 0.0, 0.0)
            elif axis == "Y":
                pos_l = (0.0, val, 0.0)
                pos_r = (0.0, -val, 0.0)
            elif axis == "Z":
                pos_l = (0.0, 0.0, val)
                pos_r = (0.0, 0.0, val)
            else:
                raise ValueError(f"Unknown position axis: {axis}")

            joints.append({
                "name": "mHipLeft",
                "priority": self.priority,
                "rot_keys": [],  # Empty rot_keys guarantees usage has no ROT flag
                "pos_keys": [
                    (0.0, pos_l),
                    (self.duration, pos_l)
                ]
            })
            joints.append({
                "name": "mHipRight",
                "priority": self.priority,
                "rot_keys": [],
                "pos_keys": [
                    (0.0, pos_r),
                    (self.duration, pos_r)
                ]
            })

        elif category == "rotation":
            # Target structural bones: mHipLeft and mHipRight
            # X (Roll/Tilt) and Z (Yaw/Turnout) are mirrored
            # Y (Pitch/Swing) is symmetrical
            if axis == "X":
                rot_deg_l = (val, 0.0, 0.0)
                rot_deg_r = (-val, 0.0, 0.0)
            elif axis == "Y":
                rot_deg_l = (0.0, val, 0.0)
                rot_deg_r = (0.0, val, 0.0)
            elif axis == "Z":
                rot_deg_l = (0.0, 0.0, val)
                rot_deg_r = (0.0, 0.0, -val)
            else:
                raise ValueError(f"Unknown rotation axis: {axis}")

            bvh_rotations["mHipLeft"] = rot_deg_l
            bvh_rotations["mHipRight"] = rot_deg_r

            # Convert to compressed quaternions for .anim
            ql = euler_deg_to_quat(*rot_deg_l)
            qr = euler_deg_to_quat(*rot_deg_r)
            vl = quat_to_vec3(*ql)
            vr = quat_to_vec3(*qr)

            joints.append({
                "name": "mHipLeft",
                "priority": self.priority,
                "rot_keys": [
                    (0.0, vl),
                    (self.duration, vl)
                ],
                "pos_keys": []  # Empty pos_keys guarantees usage has no POS flag
            })
            joints.append({
                "name": "mHipRight",
                "priority": self.priority,
                "rot_keys": [
                    (0.0, vr),
                    (self.duration, vr)
                ],
                "pos_keys": []
            })

        elif category == "scale":
            if axis == "Vol":
                # Target Collision Volume bones: L_UPPER_LEG, R_UPPER_LEG
                # Radial expansion: Y (lateral) + X (anterior 50%)
                pos_l = (val * 0.5, val, 0.0)
                pos_r = (val * 0.5, -val, 0.0)

                joints.append({
                    "name": "L_UPPER_LEG",
                    "priority": self.priority,
                    "rot_keys": [],
                    "pos_keys": [
                        (0.0, pos_l),
                        (self.duration, pos_l)
                    ]
                })
                joints.append({
                    "name": "R_UPPER_LEG",
                    "priority": self.priority,
                    "rot_keys": [],
                    "pos_keys": [
                        (0.0, pos_r),
                        (self.duration, pos_r)
                    ]
                })
            elif axis == "Len":
                # Target Knee joints: mKneeLeft, mKneeRight
                # Displacing Knee downwards (-Z) stretches the thigh
                pos_l = (0.0, 0.0, -val)
                pos_r = (0.0, 0.0, -val)

                joints.append({
                    "name": "mKneeLeft",
                    "priority": self.priority,
                    "rot_keys": [],
                    "pos_keys": [
                        (0.0, pos_l),
                        (self.duration, pos_l)
                    ]
                })
                joints.append({
                    "name": "mKneeRight",
                    "priority": self.priority,
                    "rot_keys": [],
                    "pos_keys": [
                        (0.0, pos_r),
                        (self.duration, pos_r)
                    ]
                })
            else:
                raise ValueError(f"Unknown scale axis: {axis}")

        return joints, bvh_rotations

    def generate_all(
        self,
        output_dir: str | Path,
        export_bvh: bool = True
    ) -> Dict[str, Any]:
        """
        Generate all modular animation steps for the configured region.

        Outputs:
            - .anim binary files (upload ready)
            - .bvh text files (for rotation channels)
            - manifest.json
            - lsl/modular_deformer_hud.lsl
        """
        out_path = Path(output_dir)
        out_path.mkdir(parents=True, exist_ok=True)

        manifest: Dict[str, Any] = {
            "region": self.region,
            "priority": self.priority,
            "duration": self.duration,
            "fps": self.fps,
            "num_steps": self.num_steps,
            "pos_snap": self.pos_snap,
            "rot_snap": self.rot_snap,
            "scale_snap": self.scale_snap,
            "channels": {}
        }

        total_files = 0

        for ch in THIGH_CHANNELS:
            ch_folder = out_path / ch.folder
            ch_folder.mkdir(parents=True, exist_ok=True)

            # Determine snap value
            if ch.category == "position":
                snap = self.pos_snap
            elif ch.category == "rotation":
                snap = self.rot_snap
            else:
                snap = self.scale_snap

            channel_key = f"{ch.category}_{ch.axis}".lower()
            manifest["channels"][channel_key] = {
                "category": ch.category,
                "axis": ch.axis,
                "unit": ch.unit,
                "snap": snap,
                "steps": []
            }

            # Generate positive (+1 to +N) and negative (-1 to -N) steps
            step_ranges = [(1, self.num_steps + 1, "p", 1.0), (1, self.num_steps + 1, "m", -1.0)]

            for start, end, prefix, sign in step_ranges:
                for step_idx in range(start, end):
                    val = step_idx * snap * sign
                    step_name = f"Thigh_{ch.category[:3].title()}_{ch.axis}_{prefix}{step_idx:02d}"

                    joints, bvh_rots = self._build_thigh_joints(ch.category, ch.axis, val)

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

                    # 2. Write BVH if rotation and requested
                    if export_bvh and ch.category == "rotation" and bvh_rots:
                        bvh_text = SLAnimWriter.serialize_bvh(bvh_rots, fps=self.fps, num_frames=2)
                        bvh_file = ch_folder / f"{step_name}.bvh"
                        with open(bvh_file, "w", encoding="utf-8") as f:
                            f.write(bvh_text)
                        step_info["file_bvh"] = str(bvh_file.relative_to(out_path))
                        total_files += 1

                    manifest["channels"][channel_key]["steps"].append(step_info)

        # 3. Write manifest.json
        manifest_file = out_path / "manifest.json"
        with open(manifest_file, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2)

        # 4. Generate LSL HUD script template
        lsl_script = self._generate_lsl_hud_script()
        lsl_file = out_path / "modular_deformer_hud.lsl"
        with open(lsl_file, "w", encoding="utf-8") as f:
            f.write(lsl_script)

        manifest["total_files_generated"] = total_files
        manifest["manifest_file"] = str(manifest_file)
        manifest["lsl_script"] = str(lsl_file)

        return manifest

    def _generate_lsl_hud_script(self) -> str:
        """Generate ready-to-use Second Life LSL HUD script controlling modular channels."""
        return """// ==============================================================================
// Modular Second Life Avatar Deformer HUD Script
// Controls independent deformation channels (Position, Rotation, Scale).
// Plays Priority 5 looped animations concurrently on the avatar.
// ==============================================================================

integer CHANNEL_DIALOG = -884422;
integer gListener;
key gOwner;

// Track active animation per channel
// Channels: 0:PosX, 1:PosY, 2:PosZ, 3:ScaleVol, 4:ScaleLen
list gActiveAnims = ["", "", "", "", ""];
list gStepIndices = [0, 0, 0, 0, 0];
list gChannelNames = [
    "Pos_X", "Pos_Y", "Pos_Z",
    "Scale_Vol", "Scale_Len"
];

integer gCurrentChannel = 1; // Default to Pos_Y (Thigh Gap)
integer MAX_STEPS = 10;

string getAnimName(integer ch_idx, integer step) {
    if (step == 0) return "";
    string ch = llList2String(gChannelNames, ch_idx);
    string prefix = "p";
    if (step < 0) {
        prefix = "m";
        step = -step;
    }
    string sStep = (string)step;
    if (step < 10) sStep = "0" + sStep;
    return "Thigh_" + ch + "_" + prefix + sStep;
}

setChannelStep(integer ch_idx, integer new_step) {
    if (new_step > MAX_STEPS) new_step = MAX_STEPS;
    if (new_step < -MAX_STEPS) new_step = -MAX_STEPS;
    
    integer old_step = llList2Integer(gStepIndices, ch_idx);
    if (old_step == new_step) return;
    
    string old_anim = llList2String(gActiveAnims, ch_idx);
    string new_anim = getAnimName(ch_idx, new_step);
    
    // Stop old animation on this channel
    if (old_anim != "" && llGetInventoryType(old_anim) == INVENTORY_ANIMATION) {
        llStopAnimation(old_anim);
    }
    
    // Play new animation on this channel
    if (new_anim != "" && llGetInventoryType(new_anim) == INVENTORY_ANIMATION) {
        llStartAnimation(new_anim);
    }
    
    gActiveAnims = llListReplaceList(gActiveAnims, [new_anim], ch_idx, ch_idx);
    gStepIndices = llListReplaceList(gStepIndices, [new_step], ch_idx, ch_idx);
    
    llOwnerSay("Channel [" + llList2String(gChannelNames, ch_idx) + "] -> Step " + (string)new_step);
}

resetAll() {
    integer i;
    for (i = 0; i < 5; ++i) {
        string anim = llList2String(gActiveAnims, i);
        if (anim != "" && llGetInventoryType(anim) == INVENTORY_ANIMATION) {
            llStopAnimation(anim);
        }
    }
    gActiveAnims = ["", "", "", "", ""];
    gStepIndices = [0, 0, 0, 0, 0];
    llOwnerSay("All deformer channels reset to skeleton default.");
}

showMenu() {
    string ch_name = llList2String(gChannelNames, gCurrentChannel);
    integer current_step = llList2Integer(gStepIndices, gCurrentChannel);
    
    string text = "\\n=== THIGH DEFORMER HUD ===\\n" +
                  "Current Channel: [" + ch_name + "]\\n" +
                  "Active Step: " + (string)current_step + " / " + (string)MAX_STEPS + "\\n\\n" +
                  "Select an action or change channel:";
                  
    list buttons = [
        "- Step", "Reset Ch", "+ Step",
        "Select Ch", "Reset All", "Close"
    ];
    llDialog(gOwner, text, buttons, CHANNEL_DIALOG);
}

showChannelMenu() {
    string text = "\\nSelect Deformer Channel to Adjust:";
    list buttons = [
        "Pos_X", "Pos_Y", "Pos_Z",
        "Scale_Vol", "Scale_Len", "<< Back"
    ];
    llDialog(gOwner, text, buttons, CHANNEL_DIALOG);
}

default {
    state_entry() {
        gOwner = llGetOwner();
        llRequestPermissions(gOwner, PERMISSION_TRIGGER_ANIMATION);
    }
    
    run_time_permissions(integer perm) {
        if (perm & PERMISSION_TRIGGER_ANIMATION) {
            llOwnerSay("Deformer HUD ready. Touch HUD to open controls.");
        }
    }
    
    attach(key id) {
        if (id != NULL_KEY) {
            gOwner = id;
            llRequestPermissions(gOwner, PERMISSION_TRIGGER_ANIMATION);
        } else {
            resetAll();
        }
    }
    
    touch_start(integer total_number) {
        if (llDetectedKey(0) != gOwner) return;
        llListenRemove(gListener);
        CHANNEL_DIALOG = (integer)(llFrand(-999999.0) - 100000.0);
        gListener = llListen(CHANNEL_DIALOG, "", gOwner, "");
        showMenu();
    }
    
    listen(integer channel, string name, key id, string msg) {
        if (id != gOwner) return;
        
        if (msg == "Close") {
            llListenRemove(gListener);
            return;
        }
        else if (msg == "+ Step") {
            integer cur = llList2Integer(gStepIndices, gCurrentChannel);
            setChannelStep(gCurrentChannel, cur + 1);
            showMenu();
        }
        else if (msg == "- Step") {
            integer cur = llList2Integer(gStepIndices, gCurrentChannel);
            setChannelStep(gCurrentChannel, cur - 1);
            showMenu();
        }
        else if (msg == "Reset Ch") {
            setChannelStep(gCurrentChannel, 0);
            showMenu();
        }
        else if (msg == "Reset All") {
            resetAll();
            showMenu();
        }
        else if (msg == "Select Ch") {
            showChannelMenu();
        }
        else if (msg == "<< Back") {
            showMenu();
        }
        else {
            // Check if msg matches a channel name
            integer idx = llListFindList(gChannelNames, [msg]);
            if (idx != -1) {
                gCurrentChannel = idx;
                showMenu();
            }
        }
    }
}
"""
