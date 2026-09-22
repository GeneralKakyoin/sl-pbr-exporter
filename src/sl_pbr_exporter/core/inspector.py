"""Material inspection and node-tree analysis module."""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set
import bpy

from ..config import (
    PASS_AO,
    PASS_BASE_COLOR,
    PASS_EMISSIVE,
    PASS_METALLIC,
    PASS_NORMAL,
    PASS_ROUGHNESS,
    get_material_blend_method,
    get_principled_socket,
)
from ..utils.uv import detect_mirrored_uv_faces, has_active_uv_layer

# Classification constants
CLASS_DIRECT_IMAGE = "DIRECT_IMAGE"
CLASS_SPLIT_IMAGE = "SPLIT_IMAGE"
CLASS_COMPLEX_PROCEDURAL = "COMPLEX_PROCEDURAL"
CLASS_CONSTANT = "CONSTANT"
CLASS_UNCONNECTED = "UNCONNECTED"

PROCEDURAL_NODE_TYPES = {
    "ShaderNodeTexNoise",
    "ShaderNodeTexVoronoi",
    "ShaderNodeTexWave",
    "ShaderNodeTexMusgrave",
    "ShaderNodeTexGradient",
    "ShaderNodeTexMagic",
    "ShaderNodeTexWhiteNoise",
    "ShaderNodeTexChecker",
    "ShaderNodeTexBrick",
}

MATH_AND_MIX_TYPES = {
    "ShaderNodeMath",
    "ShaderNodeVectorMath",
    "ShaderNodeValToRGB",  # ColorRamp
    "ShaderNodeMixRGB",
    "ShaderNodeMix",
    "ShaderNodeRGBCurve",
    "ShaderNodeVectorCurve",
    "ShaderNodeHueSaturation",
    "ShaderNodeInvert",
    "ShaderNodeGamma",
    "ShaderNodeBrightContrast",
}


@dataclass
class SocketClassification:
    classification: str
    image: Optional[bpy.types.Image] = None
    constant_value: Any = None
    node: Optional[bpy.types.Node] = None


@dataclass
class MaterialAnalysis:
    material_name: str
    material: bpy.types.Material
    principled_node: Optional[bpy.types.Node]
    requires_bake: bool
    channels_to_bake: Set[str] = field(default_factory=set)
    direct_textures: Dict[str, bpy.types.Image] = field(default_factory=dict)
    constant_values: Dict[str, Any] = field(default_factory=dict)
    alpha_mode: str = "OPAQUE"  # OPAQUE, MASK, BLEND
    alpha_cutoff: float = 0.5
    has_valid_uvs: bool = True
    mirrored_uv_faces_count: int = 0
    warnings: List[str] = field(default_factory=list)


def find_principled_bsdf(material: bpy.types.Material) -> Optional[bpy.types.Node]:
    """Find the ShaderNodeBsdfPrincipled connected to the active Material Output."""
    if not material or not material.use_nodes or not material.node_tree:
        return None

    # Find active Material Output
    output_node = None
    for node in material.node_tree.nodes:
        if node.type == "OUTPUT_MATERIAL" and getattr(node, "is_active_output", True):
            output_node = node
            break
    if not output_node:
        for node in material.node_tree.nodes:
            if node.type == "OUTPUT_MATERIAL":
                output_node = node
                break

    if not output_node:
        return None

    surface_sock = output_node.inputs.get("Surface")
    if not surface_sock or not surface_sock.is_linked:
        return None

    # Follow surface link
    link = surface_sock.links[0]
    source_node = link.from_node

    if source_node.type == "BSDF_PRINCIPLED":
        return source_node

    # If connected through a reroute or add/mix shader, check inputs
    if source_node.type == "REROUTE" and source_node.inputs[0].is_linked:
        candidate = source_node.inputs[0].links[0].from_node
        if candidate.type == "BSDF_PRINCIPLED":
            return candidate

    return None


def is_default_mapping(mapping_node: bpy.types.Node) -> bool:
    """Check if a ShaderNodeMapping applies non-identity scale, rotation, or location."""
    if mapping_node.type != "MAPPING":
        return True

    try:
        # Check scale
        scale = mapping_node.inputs.get("Scale")
        if scale:
            val = getattr(scale, "default_value", None)
            if val is not None and any(abs(v - 1.0) > 1e-4 for v in val[:3]):
                return False

        # Check location
        loc = mapping_node.inputs.get("Location")
        if loc:
            val = getattr(loc, "default_value", None)
            if val is not None and any(abs(v) > 1e-4 for v in val[:3]):
                return False

        # Check rotation
        rot = mapping_node.inputs.get("Rotation")
        if rot:
            val = getattr(rot, "default_value", None)
            if val is not None and any(abs(v) > 1e-4 for v in val[:3]):
                return False
    except Exception:
        pass

    return True


def classify_socket_input(sock: bpy.types.NodeSocket) -> SocketClassification:
    """Analyze the subgraph connected to an input socket and classify its complexity."""
    if not sock.is_linked:
        val = getattr(sock, "default_value", None)
        return SocketClassification(
            classification=CLASS_CONSTANT,
            constant_value=val,
        )

    link = sock.links[0]
    node = link.from_node

    # Direct Image Texture
    if node.type == "TEX_IMAGE":
        tex_node = node
        img = tex_node.image
        # Check if vector input is transformed
        vec_sock = tex_node.inputs.get("Vector")
        if vec_sock and vec_sock.is_linked:
            map_node = vec_sock.links[0].from_node
            if not is_default_mapping(map_node):
                return SocketClassification(
                    classification=CLASS_COMPLEX_PROCEDURAL,
                    image=img,
                    node=node,
                )

        if img is not None:
            return SocketClassification(
                classification=CLASS_DIRECT_IMAGE,
                image=img,
                node=node,
            )
        else:
            return SocketClassification(
                classification=CLASS_COMPLEX_PROCEDURAL,
                node=node,
            )

    # Normal Map node handling
    if node.type == "NORMAL_MAP":
        color_sock = node.inputs.get("Color")
        if color_sock and color_sock.is_linked:
            inner_node = color_sock.links[0].from_node
            if inner_node.type == "TEX_IMAGE" and inner_node.image is not None:
                # Direct normal texture through Normal Map node
                return SocketClassification(
                    classification=CLASS_DIRECT_IMAGE,
                    image=inner_node.image,
                    node=inner_node,
                )
        return SocketClassification(classification=CLASS_COMPLEX_PROCEDURAL, node=node)

    # Bump node (height map) -> requires normal baking
    if node.type == "BUMP":
        return SocketClassification(classification=CLASS_COMPLEX_PROCEDURAL, node=node)

    # Separate Color / RGB (Split Image)
    if node.type in ("SEPARATE_COLOR", "SEPARATE_RGB"):
        color_sock = node.inputs.get("Color") or node.inputs.get("Image")
        if color_sock and color_sock.is_linked:
            src_node = color_sock.links[0].from_node
            if src_node.type == "TEX_IMAGE" and src_node.image is not None:
                return SocketClassification(
                    classification=CLASS_SPLIT_IMAGE,
                    image=src_node.image,
                    node=src_node,
                )

    # Procedural or math graph
    return SocketClassification(
        classification=CLASS_COMPLEX_PROCEDURAL,
        node=node,
    )


def inspect_material(
    material: bpy.types.Material,
    target_object: Optional[bpy.types.Object] = None,
    bake_ao: bool = False,
    alpha_override: str = "AUTO",
) -> MaterialAnalysis:
    """Perform a comprehensive inspection of a material's node tree and geometry."""
    mat_name = material.name if material else "None"
    warnings: List[str] = []

    if not material or not material.use_nodes:
        return MaterialAnalysis(
            material_name=mat_name,
            material=material,
            principled_node=None,
            requires_bake=False,
            warnings=["Material does not use nodes."],
        )

    principled = find_principled_bsdf(material)
    if not principled:
        return MaterialAnalysis(
            material_name=mat_name,
            material=material,
            principled_node=None,
            requires_bake=True,
            warnings=["No Principled BSDF node found connected to Material Output."],
        )

    channels_to_bake: Set[str] = set()
    direct_textures: Dict[str, bpy.types.Image] = {}
    constant_values: Dict[str, Any] = {}

    # 1. Base Color
    sock_bc = get_principled_socket(principled, "Base Color")
    if sock_bc:
        cls = classify_socket_input(sock_bc)
        if cls.classification == CLASS_DIRECT_IMAGE and cls.image:
            direct_textures[PASS_BASE_COLOR] = cls.image
        elif cls.classification == CLASS_CONSTANT:
            constant_values[PASS_BASE_COLOR] = cls.constant_value
            # If it's a constant color, we can either synthesize or bake; mark for baking if non-white
            channels_to_bake.add(PASS_BASE_COLOR)
        else:
            channels_to_bake.add(PASS_BASE_COLOR)

    # 2. Roughness
    sock_rough = get_principled_socket(principled, "Roughness")
    if sock_rough:
        cls = classify_socket_input(sock_rough)
        if cls.classification == CLASS_DIRECT_IMAGE and cls.image:
            direct_textures[PASS_ROUGHNESS] = cls.image
        elif cls.classification == CLASS_CONSTANT:
            constant_values[PASS_ROUGHNESS] = cls.constant_value
        elif cls.classification == CLASS_SPLIT_IMAGE and cls.image:
            # Multi-channel split map, will pack directly or bake if needed
            direct_textures[PASS_ROUGHNESS] = cls.image
        else:
            channels_to_bake.add(PASS_ROUGHNESS)

    # 3. Metallic
    sock_metal = get_principled_socket(principled, "Metallic")
    if sock_metal:
        cls = classify_socket_input(sock_metal)
        if cls.classification == CLASS_DIRECT_IMAGE and cls.image:
            direct_textures[PASS_METALLIC] = cls.image
        elif cls.classification == CLASS_CONSTANT:
            constant_values[PASS_METALLIC] = cls.constant_value
        elif cls.classification == CLASS_SPLIT_IMAGE and cls.image:
            direct_textures[PASS_METALLIC] = cls.image
        else:
            channels_to_bake.add(PASS_METALLIC)

    # 4. Normal
    sock_norm = get_principled_socket(principled, "Normal")
    if sock_norm and sock_norm.is_linked:
        cls = classify_socket_input(sock_norm)
        if cls.classification == CLASS_DIRECT_IMAGE and cls.image:
            direct_textures[PASS_NORMAL] = cls.image
        else:
            channels_to_bake.add(PASS_NORMAL)

    # 5. Emission
    sock_emit = get_principled_socket(principled, "Emission")
    sock_emit_strength = get_principled_socket(principled, "Emission Strength")
    has_emission = False
    if sock_emit and (sock_emit.is_linked or any(v > 0.001 for v in sock_emit.default_value[:3])):
        strength = getattr(sock_emit_strength, "default_value", 1.0) if sock_emit_strength else 1.0
        if strength > 0.001:
            has_emission = True
            cls = classify_socket_input(sock_emit)
            if cls.classification == CLASS_DIRECT_IMAGE and cls.image:
                direct_textures[PASS_EMISSIVE] = cls.image
            elif cls.classification != CLASS_CONSTANT:
                channels_to_bake.add(PASS_EMISSIVE)

    # 6. Ambient Occlusion pass
    if bake_ao:
        channels_to_bake.add(PASS_AO)

    # 7. Alpha / Transparency analysis
    alpha_mode = "OPAQUE"
    alpha_cutoff = 0.5
    blend_method = get_material_blend_method(material)

    sock_alpha = get_principled_socket(principled, "Alpha")
    alpha_val = getattr(sock_alpha, "default_value", 1.0) if sock_alpha else 1.0
    alpha_linked = sock_alpha.is_linked if sock_alpha else False

    if alpha_override != "AUTO":
        alpha_mode = alpha_override
    else:
        if blend_method == "CLIP":
            alpha_mode = "MASK"
        elif blend_method in ("BLEND", "HASHED"):
            alpha_mode = "BLEND"
        elif alpha_linked or (alpha_val < 0.999):
            # If linked to image texture or reduced opacity
            alpha_mode = "MASK" if blend_method == "CLIP" else "BLEND"
        else:
            alpha_mode = "OPAQUE"

    # 8. UV Geometry checks
    has_uvs = True
    mirrored_faces_count = 0
    if target_object and target_object.type == "MESH":
        has_uvs = has_active_uv_layer(target_object)
        if not has_uvs:
            warnings.append(f"Object '{target_object.name}' has no active UV map.")
        else:
            mirrored_faces = detect_mirrored_uv_faces(target_object.data)
            mirrored_faces_count = len(mirrored_faces)
            if mirrored_faces_count > 0:
                warnings.append(
                    f"Detected {mirrored_faces_count} mirrored UV faces. "
                    "Use 'Offset Mirrored Islands' during bake to avoid seam artifacts."
                )

    requires_bake = len(channels_to_bake) > 0

    return MaterialAnalysis(
        material_name=mat_name,
        material=material,
        principled_node=principled,
        requires_bake=requires_bake,
        channels_to_bake=channels_to_bake,
        direct_textures=direct_textures,
        constant_values=constant_values,
        alpha_mode=alpha_mode,
        alpha_cutoff=alpha_cutoff,
        has_valid_uvs=has_uvs,
        mirrored_uv_faces_count=mirrored_faces_count,
        warnings=warnings,
    )
