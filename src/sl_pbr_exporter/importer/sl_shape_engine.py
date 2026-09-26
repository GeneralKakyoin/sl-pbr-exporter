"""
Second Life Avatar Shape Deformation Engine.
Applies exact Second Life GPU vertex shader skinning and bone scale ratio math:
    v' = sum_j w_j * [ P_shaped_j + (S_shape_j / S_bind_j) * (v - P_bind_j) ]
using Collada Inverse Bind Matrices and Linden Genepool shape XML.
"""

from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
import xml.etree.ElementTree as ET
import numpy as np
import bpy

# Standard Second Life Avatar 159-bone skeleton hierarchy: {bone_name: (parent_name, default_local_pos)}
SL_SKELETON_HIERARCHY: Dict[str, Tuple[Optional[str], Tuple[float, float, float]]] = {
    'mPelvis': (None, (0.0, 0.0, 1.067)),
    'PELVIS': ('mPelvis', (-0.01, 0.0, -0.02)),
    'BUTT': ('mPelvis', (-0.06, 0.0, -0.1)),
    'mSpine1': ('mPelvis', (0.0, 0.0, 0.084)),
    'mSpine2': ('mSpine1', (0.0, 0.0, -0.084)),
    'mTorso': ('mSpine2', (0.0, 0.0, 0.084)),
    'BELLY': ('mTorso', (0.028, 0.0, 0.04)),
    'LEFT_HANDLE': ('mTorso', (0.0, 0.1, 0.058)),
    'RIGHT_HANDLE': ('mTorso', (0.0, -0.1, 0.058)),
    'LOWER_BACK': ('mTorso', (0.0, 0.0, 0.023)),
    'mSpine3': ('mTorso', (-0.015, 0.0, 0.205)),
    'mSpine4': ('mSpine3', (0.015, 0.0, -0.205)),
    'mChest': ('mSpine4', (-0.015, 0.0, 0.205)),
    'CHEST': ('mChest', (0.028, 0.0, 0.07)),
    'LEFT_PEC': ('mChest', (0.119, 0.082, 0.042)),
    'RIGHT_PEC': ('mChest', (0.119, -0.082, 0.042)),
    'UPPER_BACK': ('mChest', (0.0, 0.0, 0.017)),
    'mNeck': ('mChest', (-0.01, 0.0, 0.251)),
    'NECK': ('mNeck', (0.0, 0.0, 0.02)),
    'mHead': ('mNeck', (0.0, -0.0, 0.076)),
    'HEAD': ('mHead', (0.02, 0.0, 0.07)),
    'mSkull': ('mHead', (0.0, 0.0, 0.079)),
    'mEyeRight': ('mHead', (0.098, -0.036, 0.079)),
    'mEyeLeft': ('mHead', (0.098, 0.036, 0.079)),
    'mFaceRoot': ('mHead', (0.025, 0.0, 0.045)),
    'mFaceEyeAltRight': ('mFaceRoot', (0.073, -0.036, 0.034)),
    'mFaceEyeAltLeft': ('mFaceRoot', (0.073, 0.036, 0.034)),
    'mFaceForeheadLeft': ('mFaceRoot', (0.061, 0.035, 0.083)),
    'mFaceForeheadRight': ('mFaceRoot', (0.061, -0.035, 0.083)),
    'mFaceEyebrowOuterLeft': ('mFaceRoot', (0.065, 0.046, 0.05)),
    'mFaceEyebrowCenterLeft': ('mFaceRoot', (0.071, 0.038, 0.057)),
    'mFaceEyebrowInnerLeft': ('mFaceRoot', (0.075, 0.017, 0.049)),
    'mFaceEyebrowOuterRight': ('mFaceRoot', (0.065, -0.046, 0.05)),
    'mFaceEyebrowCenterRight': ('mFaceRoot', (0.071, -0.038, 0.057)),
    'mFaceEyebrowInnerRight': ('mFaceRoot', (0.075, -0.017, 0.049)),
    'mFaceEyeLidUpperLeft': ('mFaceRoot', (0.07, 0.031, 0.028)),
    'mFaceEyeLidLowerLeft': ('mFaceRoot', (0.07, 0.031, 0.033)),
    'mFaceEyeLidUpperRight': ('mFaceRoot', (0.07, -0.031, 0.028)),
    'mFaceEyeLidLowerRight': ('mFaceRoot', (0.07, -0.031, 0.033)),
    'mFaceEar1Left': ('mFaceRoot', (0.0, 0.08, 0.002)),
    'mFaceEar2Left': ('mFaceEar1Left', (-0.019, 0.018, 0.025)),
    'mFaceEar1Right': ('mFaceRoot', (0.0, -0.08, 0.002)),
    'mFaceEar2Right': ('mFaceEar1Right', (-0.019, -0.018, 0.025)),
    'mFaceNoseLeft': ('mFaceRoot', (0.086, 0.015, -0.004)),
    'mFaceNoseCenter': ('mFaceRoot', (0.102, 0.0, 0.0)),
    'mFaceNoseRight': ('mFaceRoot', (0.086, -0.015, -0.004)),
    'mFaceCheekLowerLeft': ('mFaceRoot', (0.05, 0.034, -0.031)),
    'mFaceCheekUpperLeft': ('mFaceRoot', (0.07, 0.034, -0.005)),
    'mFaceCheekLowerRight': ('mFaceRoot', (0.05, -0.034, -0.031)),
    'mFaceCheekUpperRight': ('mFaceRoot', (0.07, -0.034, -0.005)),
    'mFaceJaw': ('mFaceRoot', (-0.001, 0.0, -0.015)),
    'mFaceChin': ('mFaceJaw', (0.074, 0.0, -0.054)),
    'mFaceTeethLower': ('mFaceJaw', (0.021, 0.0, -0.039)),
    'mFaceLipLowerLeft': ('mFaceTeethLower', (0.045, 0.0, 0.0)),
    'mFaceLipLowerRight': ('mFaceTeethLower', (0.045, 0.0, 0.0)),
    'mFaceLipLowerCenter': ('mFaceTeethLower', (0.045, 0.0, 0.0)),
    'mFaceTongueBase': ('mFaceTeethLower', (0.039, 0.0, 0.005)),
    'mFaceTongueTip': ('mFaceTongueBase', (0.022, 0.0, 0.007)),
    'mFaceJawShaper': ('mFaceRoot', (0.0, 0.0, 0.0)),
    'mFaceForeheadCenter': ('mFaceRoot', (0.069, 0.0, 0.065)),
    'mFaceNoseBase': ('mFaceRoot', (0.094, 0.0, -0.016)),
    'mFaceTeethUpper': ('mFaceRoot', (0.02, 0.0, -0.03)),
    'mFaceLipUpperLeft': ('mFaceTeethUpper', (0.045, 0.0, -0.003)),
    'mFaceLipUpperRight': ('mFaceTeethUpper', (0.045, 0.0, -0.003)),
    'mFaceLipCornerLeft': ('mFaceTeethUpper', (0.028, -0.019, -0.01)),
    'mFaceLipCornerRight': ('mFaceTeethUpper', (0.028, 0.019, -0.01)),
    'mFaceLipUpperCenter': ('mFaceTeethUpper', (0.045, 0.0, -0.003)),
    'mFaceEyecornerInnerLeft': ('mFaceRoot', (0.075, 0.017, 0.032)),
    'mFaceEyecornerInnerRight': ('mFaceRoot', (0.075, -0.017, 0.032)),
    'mFaceNoseBridge': ('mFaceRoot', (0.091, 0.0, 0.02)),
    'mCollarLeft': ('mChest', (0.008, 0.033, 0.207)),
    'L_CLAVICLE': ('mCollarLeft', (0.0, 0.06, 0.0)),
    'mShoulderLeft': ('mCollarLeft', (-0.024, 0.165, -0.029)),
    'L_UPPER_ARM': ('mShoulderLeft', (0.0, 0.09, 0.0)),
    'mElbowLeft': ('mShoulderLeft', (0.003, 0.264, -0.003)),
    'L_LOWER_ARM': ('mElbowLeft', (0.0, 0.09, 0.0)),
    'mWristLeft': ('mElbowLeft', (-0.013, 0.21, -0.011)),
    'L_HAND': ('mWristLeft', (0.0, 0.04, 0.0)),
    'mCollarRight': ('mChest', (0.008, -0.033, 0.207)),
    'R_CLAVICLE': ('mCollarRight', (0.0, -0.06, 0.0)),
    'mShoulderRight': ('mCollarRight', (-0.024, -0.165, -0.029)),
    'R_UPPER_ARM': ('mShoulderRight', (0.0, -0.09, 0.0)),
    'mElbowRight': ('mShoulderRight', (0.003, -0.264, -0.003)),
    'R_LOWER_ARM': ('mElbowRight', (0.0, -0.09, 0.0)),
    'mWristRight': ('mElbowRight', (-0.013, -0.21, -0.011)),
    'R_HAND': ('mWristRight', (0.0, -0.04, 0.0)),
    'mHipRight': ('mPelvis', (-0.045, -0.084, -0.129)),
    'R_UPPER_LEG': ('mHipRight', (0.0, 0.0, -0.18)),
    'mKneeRight': ('mHipRight', (0.014, -0.004, -0.472)),
    'R_LOWER_LEG': ('mKneeRight', (0.0, 0.0, -0.19)),
    'mAnkleRight': ('mKneeRight', (-0.024, 0.007, -0.428)),
    'R_FOOT': ('mAnkleRight', (0.06, 0.0, -0.05)),
    'mFootRight': ('mAnkleRight', (-0.078, -0.016, -0.091)),
    'mToeRight': ('mFootRight', (0.163, 0.006, 0.007)),
    'mHipLeft': ('mPelvis', (-0.045, 0.084, -0.129)),
    'L_UPPER_LEG': ('mHipLeft', (0.0, 0.0, -0.18)),
    'mKneeLeft': ('mHipLeft', (0.014, 0.004, -0.472)),
    'L_LOWER_LEG': ('mKneeLeft', (0.0, 0.0, -0.19)),
    'mAnkleLeft': ('mKneeLeft', (-0.024, -0.007, -0.428)),
    'L_FOOT': ('mAnkleLeft', (0.06, 0.0, -0.05)),
    'mFootLeft': ('mAnkleLeft', (-0.078, 0.016, -0.091)),
    'mToeLeft': ('mFootLeft', (0.163, -0.006, 0.007)),
}

# Bones that define actual Bento facial features and expressions (eyes, nose, mouth, ears, brows, jaw)
# Excludes armature hierarchy joints like 'mFaceRoot', 'mHead', 'mSkull' which hair and hats are rigged to.
BENTO_FACIAL_FEATURE_BONES = {
    k for k in SL_SKELETON_HIERARCHY
    if (k.startswith('mFace') and k != 'mFaceRoot') or k in ('mEyeLeft', 'mEyeRight')
}

# Bones that belong strictly to the body torso and limbs.
# Any mesh weighted to these bones is clothing, body mesh, or body attachment, and must NEVER
# be treated as a facial mesh.
BODY_TORSO_BONES = {
    'mChest', 'CHEST', 'UPPER_BACK', 'LEFT_PEC', 'RIGHT_PEC',
    'mSpine1', 'mSpine2', 'mSpine3', 'mSpine4', 'mTorso',
    'mPelvis', 'PELVIS', 'BUTT', 'BELLY', 'LEFT_HANDLE', 'RIGHT_HANDLE', 'LOWER_BACK',
    'mHipLeft', 'mHipRight', 'mShoulderLeft', 'mShoulderRight',
    'mCollarLeft', 'mCollarRight', 'L_CLAVICLE', 'R_CLAVICLE',
    'mElbowLeft', 'mElbowRight', 'L_UPPER_ARM', 'R_UPPER_ARM',
    'L_LOWER_ARM', 'R_LOWER_ARM', 'mWristLeft', 'mWristRight',
    'L_HAND', 'R_HAND', 'mKneeLeft', 'mKneeRight',
    'L_UPPER_LEG', 'R_UPPER_LEG', 'L_LOWER_LEG', 'R_LOWER_LEG',
    'mAnkleLeft', 'mAnkleRight', 'L_FOOT', 'R_FOOT',
    'mFootLeft', 'mFootRight', 'mToeLeft', 'mToeRight'
}

HEAD_ATTACHMENT_BONES = {'mHead', 'HEAD', 'mSkull', 'mFaceRoot'}

# Backward compatibility alias
FACIAL_BONE_NAMES = BENTO_FACIAL_FEATURE_BONES



def parse_shape_xml_bones(shape_xml_path: Path) -> Dict[str, Dict[str, np.ndarray]]:
    """Parse bone position and scale from a Second Life shape XML."""
    if not shape_xml_path.exists():
        return {}

    tree = ET.parse(str(shape_xml_path))
    root = tree.getroot()

    bones: Dict[str, Dict[str, np.ndarray]] = {}
    for b in root.findall('.//bone'):
        name = b.get('name')
        if not name:
            continue
        pos_str = b.get('position')
        scale_str = b.get('scale')
        pos = np.array([float(x) for x in pos_str.split()], dtype=np.float32) if pos_str else None
        scale = np.array([float(x) for x in scale_str.split()], dtype=np.float32) if scale_str else None
        bones[name] = {'pos': pos, 'scale': scale}

    return bones


def parse_dae_skin_info(dae_paths: List[Path]) -> Dict[str, Any]:
    """
    Extract Inverse Bind Matrices, Bind Scales, and Bind World Positions
    from Collada (.dae) files.
    """
    ns = {'c': 'http://www.collada.org/2005/11/COLLADASchema'}
    ibms: Dict[str, np.ndarray] = {}
    bind_scales: Dict[str, np.ndarray] = {}
    bind_world_pos: Dict[str, np.ndarray] = {}

    for dae_file in dae_paths:
        if not dae_file.exists():
            continue
        try:
            tree = ET.parse(str(dae_file))
            root = tree.getroot()
            for skin in root.findall('.//c:skin', ns):
                joints = []
                for s in skin.findall('c:source', ns):
                    arr = s.find('c:Name_array', ns)
                    if arr is not None and arr.text:
                        joints = arr.text.split()
                    f_arr = s.find('c:float_array', ns)
                    if f_arr is not None and f_arr.text and 'bind' in s.get('id', '').lower():
                        vals = [float(x) for x in f_arr.text.split()]
                        for i in range(len(vals) // 16):
                            if i >= len(joints):
                                break
                            jname = joints[i]
                            if jname not in ibms:
                                ibm = np.array(vals[i*16:(i+1)*16], dtype=np.float32).reshape(4, 4)
                                ibms[jname] = ibm
                                try:
                                    inv = np.linalg.inv(ibm)
                                    bind_world_pos[jname] = inv[:3, 3]
                                    bind_scales[jname] = np.array(
                                        [np.linalg.norm(inv[:3, c]) for c in range(3)], dtype=np.float32
                                    )
                                except Exception:
                                    bind_scales[jname] = np.ones(3, dtype=np.float32)
                                    bind_world_pos[jname] = np.zeros(3, dtype=np.float32)
        except Exception as e:
            print(f"[ShapeEngine] Warning reading {dae_file.name}: {e}")

    return {
        'ibms': ibms,
        'bind_scales': bind_scales,
        'bind_world_pos': bind_world_pos,
    }


def compute_shaped_skeleton(
    shape_bones: Dict[str, Dict[str, Optional[np.ndarray]]],
    dae_skin_info: Dict[str, Any],
    anchor_bone: str = 'mNeck',
    delta_neck: Optional[Any] = None,
) -> Tuple[Dict[str, np.ndarray], Dict[str, np.ndarray]]:
    """
    Computes effective scales (S_shape / S_bind) and forward-kinematics world positions
    anchored at anchor_bone (default: mNeck) to guarantee 100% gapless neck seam alignment.
    If delta_neck is provided, the anchor joint and all descendants are shifted accordingly.
    """
    bind_scales = dae_skin_info.get('bind_scales', {})
    bind_world_pos = dae_skin_info.get('bind_world_pos', {})

    # Build parent map and default pos map from SL hierarchy
    parent_map = {k: v[0] for k, v in SL_SKELETON_HIERARCHY.items()}
    default_pos_map = {k: np.array(v[1], dtype=np.float32) for k, v in SL_SKELETON_HIERARCHY.items()}

    delta_sl = np.zeros(3, dtype=np.float32)
    if delta_neck is not None:
        if isinstance(delta_neck, (int, float)):
            delta_sl[2] = float(delta_neck)
        elif hasattr(delta_neck, "__iter__"):
            arr = np.array(list(delta_neck), dtype=np.float32)
            if arr.ndim == 0:
                delta_sl[2] = float(arr)
            else:
                n = min(3, len(arr))
                delta_sl[:n] = arr[:n]

    # Anchor position at anchor_bone bind position, offset by delta_sl
    anchor_bind_pos = bind_world_pos.get(anchor_bone, np.array([-0.0249, 0.0, 1.6071], dtype=np.float32))
    shaped_world_pos: Dict[str, np.ndarray] = {anchor_bone: anchor_bind_pos + delta_sl}

    def get_bone_scale(name: str) -> np.ndarray:
        sb = shape_bones.get(name, {})
        s = sb.get('scale')
        return s if s is not None else np.ones(3, dtype=np.float32)

    def get_bone_local_pos(name: str) -> np.ndarray:
        sb = shape_bones.get(name, {})
        p = sb.get('pos')
        if p is not None:
            return p
        return default_pos_map.get(name, np.zeros(3, dtype=np.float32))

    def get_shaped_pos(name: str) -> np.ndarray:
        if name in shaped_world_pos:
            return shaped_world_pos[name]
        parent = parent_map.get(name)
        pos = get_bone_local_pos(name)
        if not parent or parent == anchor_bone:
            p_wp = shaped_world_pos[anchor_bone]
            p_scale = get_bone_scale(anchor_bone)
        else:
            p_wp = get_shaped_pos(parent)
            p_scale = get_bone_scale(parent)
        wp = p_wp + p_scale * pos
        shaped_world_pos[name] = wp
        return wp

    # Compute for all known joints
    all_joints = set(bind_scales.keys()).union(shape_bones.keys())
    for jname in all_joints:
        get_shaped_pos(jname)

    # Compute effective scales: S_eff = S_shape / S_bind
    eff_scales: Dict[str, np.ndarray] = {}
    for jname in all_joints:
        s_shape = get_bone_scale(jname)
        s_bind = bind_scales.get(jname, np.ones(3, dtype=np.float32))
        s_bind_safe = np.where(s_bind < 1e-4, 1.0, s_bind)
        eff_scales[jname] = s_shape / s_bind_safe

    return eff_scales, shaped_world_pos


def apply_exact_sl_shape_to_meshes(
    meshes: List[bpy.types.Object],
    folder_path: Path,
    shape_xml_path: Optional[Path] = None,
    shape_key_name: str = "SL_Avatar_Shape",
    anchor_bone: str = "mNeck",
    delta_neck: Optional[Any] = None,
) -> int:
    """
    Applies Second Life GPU vertex shader transformation to the specified mesh objects.
    Deforms geometry using exact bone scale ratios and forward kinematics, saving the result
    as a non-destructive Shape Key (default value 1.0) while keeping Basis untouched.

    If delta_neck is provided (scalar height delta or 3D offset vector in SL coordinates),
    the neck anchor and facial joints track the body neck seam seamlessly.

    Returns the count of successfully deformed mesh objects.
    """
    if not shape_xml_path:
        # Search folder for shape XML
        shape_candidates = list(folder_path.glob("*_shape.xml")) + list(folder_path.glob("*.xml"))
        # Exclude devkit_session.json etc
        shape_candidates = [c for c in shape_candidates if "_shape" in c.name or c.suffix == ".xml"]
        if shape_candidates:
            shape_xml_path = shape_candidates[0]

    if not shape_xml_path or not shape_xml_path.exists():
        print(f"[ShapeEngine] No shape XML found in {folder_path}. Skipping SL shape deformation.")
        return 0

    # Parse shape XML
    shape_bones = parse_shape_xml_bones(shape_xml_path)
    if not shape_bones:
        print(f"[ShapeEngine] Shape XML {shape_xml_path.name} contains no bone definitions.")
        return 0

    delta_sl = np.zeros(3, dtype=np.float32)
    if delta_neck is not None:
        if isinstance(delta_neck, (int, float)):
            delta_sl[2] = float(delta_neck)
        elif hasattr(delta_neck, "__iter__"):
            arr = np.array(list(delta_neck), dtype=np.float32)
            if arr.ndim == 0:
                delta_sl[2] = float(arr)
            else:
                n = min(3, len(arr))
                delta_sl[:n] = arr[:n]

    # Find and parse DAE files for skinning data
    dae_files = list(folder_path.glob("*.dae"))
    dae_skin_info = parse_dae_skin_info(dae_files)
    bind_world_pos = dae_skin_info.get('bind_world_pos', {})

    # Compute skeleton
    eff_scales, shaped_world_pos = compute_shaped_skeleton(
        shape_bones, dae_skin_info, anchor_bone=anchor_bone, delta_neck=delta_sl
    )

    facial_bone_names = FACIAL_BONE_NAMES

    deformed_count = 0
    for obj in meshes:
        if obj.type != 'MESH' or not obj.data or not obj.vertex_groups:
            continue

        vgroups = {g.index: g.name for g in obj.vertex_groups}
        mesh = obj.data

        # Ensure this is a Bento head / facial attachment mesh (head, eyes, ears, lashes, teeth, etc.),
        # NOT hair, body, or clothing.
        # A Bento facial mesh MUST have weights for Bento facial feature bones,
        # and MUST NOT have weights for torso/limb bones.
        has_facial_weight = False
        has_body_weight = False
        for v in mesh.vertices:
            for g in v.groups:
                if g.weight > 0.01:
                    bname = vgroups.get(g.group)
                    if bname in BENTO_FACIAL_FEATURE_BONES:
                        has_facial_weight = True
                    elif bname in BODY_TORSO_BONES:
                        has_body_weight = True
            if has_facial_weight and has_body_weight:
                break

        if not has_facial_weight or has_body_weight:
            if mesh.shape_keys:
                sk = mesh.shape_keys.key_blocks.get(shape_key_name)
                if sk:
                    sk.value = 0.0
            continue

        BSM = np.array(obj.matrix_world, dtype=np.float32)
        try:
            inv_BSM = np.linalg.inv(BSM)
        except Exception:
            inv_BSM = np.eye(4, dtype=np.float32)

        # Setup Shape Keys
        if not mesh.shape_keys:
            obj.shape_key_add(name="Basis", from_mix=False)

        sk = mesh.shape_keys.key_blocks.get(shape_key_name)
        if not sk:
            sk = obj.shape_key_add(name=shape_key_name, from_mix=False)

        sk.value = 1.0

        # Determine whether the mesh is in Avastar/Blender space (-90 deg Z rotated)
        # or native Second Life space (+X forward, +Y left).
        is_avastar_space = (
            obj.get("sl_aligned_to_devkit", False)
            or (obj.parent and obj.parent.type == "ARMATURE")
            or any(m.type == "ARMATURE" and m.object for m in obj.modifiers)
        )

        R_to_sl = np.array([
            [0.0, -1.0, 0.0],
            [1.0,  0.0, 0.0],
            [0.0,  0.0, 1.0]
        ], dtype=np.float32)

        R_to_ava = np.array([
            [ 0.0, 1.0, 0.0],
            [-1.0, 0.0, 0.0],
            [ 0.0, 0.0, 1.0]
        ], dtype=np.float32)

        # Calculate exact vertex deformation
        verts = mesh.vertices
        for idx, v in enumerate(verts):
            # Original position in world space: BSM @ local_co
            p_world = (BSM @ np.array([v.co.x, v.co.y, v.co.z, 1.0], dtype=np.float32))[:3]
            p_sl = R_to_sl @ p_world if is_avastar_space else p_world

            total_w = 0.0
            p_def_sl = np.zeros(3, dtype=np.float32)

            for g in v.groups:
                jname = vgroups.get(g.group)
                if jname and jname in eff_scales:
                    w = g.weight
                    if w > 1e-4:
                        if jname == anchor_bone:
                            # Anchor joint (mNeck seam): scale horizontally by s_eff around bone center
                            # to match shaped body neck circumference, and translate vertically by delta_sl
                            p_bind = bind_world_pos.get(anchor_bone, np.array([-0.0249, 0.0, 1.6071], dtype=np.float32))
                            s_eff = eff_scales.get(anchor_bone, np.ones(3, dtype=np.float32))
                            p_j = np.zeros(3, dtype=np.float32)
                            p_j[0] = p_bind[0] + s_eff[0] * (p_sl[0] - p_bind[0])
                            p_j[1] = p_bind[1] + s_eff[1] * (p_sl[1] - p_bind[1])
                            p_j[2] = p_sl[2] + delta_sl[2]
                        else:
                            p_bind = bind_world_pos.get(jname, p_sl)
                            p_shaped = shaped_world_pos.get(jname, p_bind)
                            s_eff = eff_scales[jname]
                            p_j = p_shaped + s_eff * (p_sl - p_bind)

                        p_def_sl += w * p_j
                        total_w += w

            if total_w > 0.0:
                p_def_sl /= total_w
            else:
                p_def_sl = p_sl + delta_sl

            p_def_world = R_to_ava @ p_def_sl if is_avastar_space else p_def_sl

            # Convert deformed world position back to local mesh space
            p_def_4 = np.array([p_def_world[0], p_def_world[1], p_def_world[2], 1.0], dtype=np.float32)
            p_local = (inv_BSM @ p_def_4)[:3]
            sk.data[idx].co = p_local

        deformed_count += 1

    print(f"[ShapeEngine] Successfully applied 1:1 Second Life shape '{shape_xml_path.name}' to {deformed_count} mesh object(s).")
    return deformed_count
