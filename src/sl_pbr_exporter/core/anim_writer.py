"""Second Life Binary .anim and BVH Animation Serializer.

Implements byte-accurate serialization and deserialization for Second Life's
native keyframe motion format (.anim v1.0) and Biovision Hierarchy (.bvh).
Compliant with Linden Lab's LLKeyframeMotion and LLBVHLoader.
"""

from __future__ import annotations

import math
import struct
from typing import Any, Dict, List, Optional, Tuple

U16_MAX = 65535
PELVIS_MAX_OFFSET = 5.0  # SL-318 limit (meters)


def f32_to_u16(val: float, lower: float, upper: float) -> int:
    """Quantize float32 into uint16 using Second Life's exact floor normalization."""
    val = max(lower, min(upper, float(val)))
    val -= lower
    val /= (upper - lower)
    ival = int(math.floor(val * U16_MAX))
    return max(0, min(U16_MAX, ival))


def u16_to_f32(ival: int, lower: float, upper: float) -> float:
    """Reconstruct float32 from uint16 using Second Life's unpacking algorithm."""
    val = (ival / float(U16_MAX)) * (upper - lower) + lower
    max_error = (upper - lower) / float(U16_MAX)
    if abs(val) < max_error:
        return 0.0
    return val


def quat_to_vec3(x: float, y: float, z: float, w: float) -> Tuple[float, float, float]:
    """Compress a unit quaternion into a 3D vector following LLQuaternion::packToVector3()."""
    mag = math.sqrt(x * x + y * y + z * z + w * w)
    if mag > 1e-6:
        x /= mag
        y /= mag
        z /= mag
        w /= mag
    if w >= 0.0:
        return (x, y, z)
    else:
        return (-x, -y, -z)


def vec3_to_quat(x: float, y: float, z: float) -> Tuple[float, float, float, float]:
    """Reconstruct a unit quaternion from a compressed 3D vector."""
    mag_sq = x * x + y * y + z * z
    t = 1.0 - mag_sq
    w = math.sqrt(max(0.0, t))
    return (x, y, z, w)


def euler_deg_to_quat(
    pitch_deg: float,
    roll_deg: float,
    yaw_deg: float,
    order: str = "XYZ"
) -> Tuple[float, float, float, float]:
    """Convert Euler rotation angles (degrees) to a normalized quaternion (x, y, z, w)."""
    rx = math.radians(pitch_deg)
    ry = math.radians(roll_deg)
    rz = math.radians(yaw_deg)

    cx, sx = math.cos(rx / 2.0), math.sin(rx / 2.0)
    cy, sy = math.cos(ry / 2.0), math.sin(ry / 2.0)
    cz, sz = math.cos(rz / 2.0), math.sin(rz / 2.0)

    # Standard intrinsic XYZ rotation (matches mayaQ in SL)
    if order == "XYZ":
        qx = sx * cy * cz + cx * sy * sz
        qy = cx * sy * cz - sx * cy * sz
        qz = cx * cy * sz + sx * sy * cz
        qw = cx * cy * cz - sx * sy * sz
    else:
        # Fallback to XYZ
        qx = sx * cy * cz + cx * sy * sz
        qy = cx * sy * cz - sx * cy * sz
        qz = cx * cy * sz + sx * sy * cz
        qw = cx * cy * cz - sx * sy * sz

    return (qx, qy, qz, qw)


class SLAnimWriter:
    """Writer and Parser for Second Life .anim binary keyframe animation files."""

    VERSION = 1
    SUB_VERSION = 0

    @classmethod
    def serialize_anim(
        cls,
        joints: List[Dict[str, Any]],
        duration: float = 0.0666667,
        base_priority: int = 5,
        loop: bool = True,
        ease_in: float = 0.0,
        ease_out: float = 0.0,
        hand_pose: int = 0,
        emote_name: str = ""
    ) -> bytes:
        """
        Serialize avatar joints animation data into SL binary .anim format.

        Each joint dict in joints:
        {
            "name": str,                      # e.g. 'mHipLeft'
            "priority": int,                  # defaults to base_priority
            "rot_keys": [(t, (vx, vy, vz))],  # compressed quat angles in [-1.0, 1.0]
            "pos_keys": [(t, (px, py, pz))]   # translations in [-5.0, 5.0] meters
        }
        """
        buf = bytearray()

        # 1. Header (44 bytes total)
        buf.extend(struct.pack("<HH", cls.VERSION, cls.SUB_VERSION))
        buf.extend(struct.pack("<i", int(base_priority)))
        buf.extend(struct.pack("<f", float(duration)))
        # emote_name null-terminated
        buf.extend(emote_name.encode("utf-8") + b"\x00")
        buf.extend(struct.pack("<f", 0.0))  # loop_in_point
        buf.extend(struct.pack("<f", float(duration)))  # loop_out_point
        buf.extend(struct.pack("<i", 1 if loop else 0))
        buf.extend(struct.pack("<f", float(ease_in)))
        buf.extend(struct.pack("<f", float(ease_out)))
        buf.extend(struct.pack("<I", int(hand_pose)))
        buf.extend(struct.pack("<I", len(joints)))

        # 2. Joint Motions
        for joint in joints:
            name_bytes = joint["name"].encode("utf-8") + b"\x00"
            buf.extend(name_bytes)

            joint_priority = joint.get("priority", base_priority)
            buf.extend(struct.pack("<i", int(joint_priority)))

            rot_keys = joint.get("rot_keys", [])
            buf.extend(struct.pack("<i", len(rot_keys)))
            for t, (rx, ry, rz) in rot_keys:
                t_short = f32_to_u16(t, 0.0, duration)
                qx = f32_to_u16(rx, -1.0, 1.0)
                qy = f32_to_u16(ry, -1.0, 1.0)
                qz = f32_to_u16(rz, -1.0, 1.0)
                buf.extend(struct.pack("<HHHH", t_short, qx, qy, qz))

            pos_keys = joint.get("pos_keys", [])
            buf.extend(struct.pack("<i", len(pos_keys)))
            for t, (px, py, pz) in pos_keys:
                t_short = f32_to_u16(t, 0.0, duration)
                ux = f32_to_u16(px, -PELVIS_MAX_OFFSET, PELVIS_MAX_OFFSET)
                uy = f32_to_u16(py, -PELVIS_MAX_OFFSET, PELVIS_MAX_OFFSET)
                uz = f32_to_u16(pz, -PELVIS_MAX_OFFSET, PELVIS_MAX_OFFSET)
                buf.extend(struct.pack("<HHHH", t_short, ux, uy, uz))

        # 3. Constraints
        buf.extend(struct.pack("<i", 0))  # num_constraints = 0

        return bytes(buf)

    @classmethod
    def deserialize_anim(cls, data: bytes) -> Dict[str, Any]:
        """Deserialize and validate Second Life .anim binary data."""
        offset = 0
        version, sub_version = struct.unpack_from("<HH", data, offset)
        offset += 4
        if version != cls.VERSION or sub_version != cls.SUB_VERSION:
            raise ValueError(f"Unsupported .anim version: {version}.{sub_version}")

        base_priority, duration = struct.unpack_from("<if", data, offset)
        offset += 8

        null_idx = data.find(b"\x00", offset)
        if null_idx == -1:
            raise ValueError("Corrupt .anim file: Unterminated emote string")
        emote_name = data[offset:null_idx].decode("utf-8")
        offset = null_idx + 1

        loop_in, loop_out, loop, ease_in, ease_out, hand_pose, num_joints = struct.unpack_from(
            "<ffiffII", data, offset
        )
        offset += 28

        joints = []
        for _ in range(num_joints):
            null_idx = data.find(b"\x00", offset)
            if null_idx == -1:
                raise ValueError("Corrupt .anim file: Unterminated joint name")
            joint_name = data[offset:null_idx].decode("utf-8")
            offset = null_idx + 1

            joint_priority, num_rot_keys = struct.unpack_from("<ii", data, offset)
            offset += 8

            rot_keys = []
            for _ in range(num_rot_keys):
                t_short, qx, qy, qz = struct.unpack_from("<HHHH", data, offset)
                offset += 8
                t = u16_to_f32(t_short, 0.0, duration)
                rx = u16_to_f32(qx, -1.0, 1.0)
                ry = u16_to_f32(qy, -1.0, 1.0)
                rz = u16_to_f32(qz, -1.0, 1.0)
                rot_keys.append((t, (rx, ry, rz)))

            num_pos_keys = struct.unpack_from("<i", data, offset)[0]
            offset += 4

            pos_keys = []
            for _ in range(num_pos_keys):
                t_short, ux, uy, uz = struct.unpack_from("<HHHH", data, offset)
                offset += 8
                t = u16_to_f32(t_short, 0.0, duration)
                px = u16_to_f32(ux, -PELVIS_MAX_OFFSET, PELVIS_MAX_OFFSET)
                py = u16_to_f32(uy, -PELVIS_MAX_OFFSET, PELVIS_MAX_OFFSET)
                pz = u16_to_f32(uz, -PELVIS_MAX_OFFSET, PELVIS_MAX_OFFSET)
                pos_keys.append((t, (px, py, pz)))

            joints.append({
                "name": joint_name,
                "priority": joint_priority,
                "rot_keys": rot_keys,
                "pos_keys": pos_keys
            })

        num_constraints = struct.unpack_from("<i", data, offset)[0]
        offset += 4

        return {
            "version": version,
            "sub_version": sub_version,
            "base_priority": base_priority,
            "duration": duration,
            "emote_name": emote_name,
            "loop_in": loop_in,
            "loop_out": loop_out,
            "loop": bool(loop),
            "ease_in": ease_in,
            "ease_out": ease_out,
            "hand_pose": hand_pose,
            "num_joints": num_joints,
            "joints": joints,
            "num_constraints": num_constraints
        }

    @classmethod
    def serialize_bvh(
        cls,
        joint_rotations_deg: Dict[str, Tuple[float, float, float]],
        fps: float = 30.0,
        num_frames: int = 2
    ) -> str:
        """
        Serialize rotation channels for Second Life avatar skeleton into a standard BVH text file.
        Contains minimal SL skeleton hierarchy with root hip (mPelvis).
        """
        frame_time = 1.0 / fps
        lines = [
            "HIERARCHY",
            "ROOT hip",
            "{",
            "  OFFSET 0.000000 0.000000 0.000000",
            "  CHANNELS 6 Xposition Yposition Zposition Zrotation Xrotation Yrotation",
            "  JOINT mHipRight",
            "  {",
            "    OFFSET 0.033757 -0.126765 -0.040998",
            "    CHANNELS 3 Zrotation Xrotation Yrotation",
            "    JOINT mKneeRight",
            "    {",
            "      OFFSET -0.000000 0.000000 -0.440000",
            "      CHANNELS 3 Zrotation Xrotation Yrotation",
            "      End Site",
            "      {",
            "        OFFSET 0.000000 0.000000 -0.440000",
            "      }",
            "    }",
            "  }",
            "  JOINT mHipLeft",
            "  {",
            "    OFFSET 0.033757 0.126765 -0.040998",
            "    CHANNELS 3 Zrotation Xrotation Yrotation",
            "    JOINT mKneeLeft",
            "    {",
            "      OFFSET -0.000000 0.000000 -0.440000",
            "      CHANNELS 3 Zrotation Xrotation Yrotation",
            "      End Site",
            "      {",
            "        OFFSET 0.000000 0.000000 -0.440000",
            "      }",
            "    }",
            "  }",
            "}",
            "MOTION",
            f"Frames: {num_frames}",
            f"Frame Time: {frame_time:.6f}"
        ]

        # Extract rotations: (Zrot, Xrot, Yrot)
        def get_rot(name: str) -> Tuple[float, float, float]:
            if name in joint_rotations_deg:
                rx, ry, rz = joint_rotations_deg[name]
                return (rz, rx, ry)
            return (0.0, 0.0, 0.0)

        hip_pos = (0.0, 0.0, 0.0)
        hip_rot = (0.0, 0.0, 0.0)
        r_hip = get_rot("mHipRight")
        r_knee = get_rot("mKneeRight")
        l_hip = get_rot("mHipLeft")
        l_knee = get_rot("mKneeLeft")

        # Assemble row values
        row_values = [
            hip_pos[0], hip_pos[1], hip_pos[2], hip_rot[0], hip_rot[1], hip_rot[2],
            r_hip[0], r_hip[1], r_hip[2],
            r_knee[0], r_knee[1], r_knee[2],
            l_hip[0], l_hip[1], l_hip[2],
            l_knee[0], l_knee[1], l_knee[2]
        ]
        row_str = " ".join(f"{v:.6f}" for v in row_values)

        for _ in range(num_frames):
            lines.append(row_str)

        return "\n".join(lines) + "\n"
