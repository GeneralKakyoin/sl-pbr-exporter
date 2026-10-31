"""Second Life Joint Position Deformer Generator.

Generates 100% compliant COLLADA (.dae) files containing joint position overrides
for Second Life fitted mesh avatars and attachments without requiring 3D modeling tools.
"""

from __future__ import annotations

import os
import re
from typing import Dict, List, Tuple, Optional


class DeformerGenerator:
    """Generates Second Life COLLADA .dae files with Joint Position Overrides."""

    # Built-in Anatomical Presets
    # Format: parameter_name -> function(val_meters) -> dict of {bone_name: (dx, dy, dz)}
    PRESETS = {
        "thigh_width": lambda v: {
            # In Avastar bone local space, Y is lateral: Left leg negative, Right leg positive
            "L_UPPER_LEG": (0.0, -v, 0.0),
            "R_UPPER_LEG": (0.0, v, 0.0),
        },
        "thigh_thickness": lambda v: {
            # Forward/backward thickness
            "L_UPPER_LEG": (v, 0.0, 0.0),
            "R_UPPER_LEG": (v, 0.0, 0.0),
        },
        "thigh_height": lambda v: {
            "L_UPPER_LEG": (0.0, 0.0, v),
            "R_UPPER_LEG": (0.0, 0.0, v),
        },
        "hip_spread": lambda v: {
            "mHipLeft": (0.0, v, 0.0),
            "mHipRight": (0.0, -v, 0.0),
        },
        "butt_projection": lambda v: {
            # Negative X moves backward in Second Life skeleton root coordinates
            "BUTT": (-v, 0.0, 0.0),
        },
        "butt_lift": lambda v: {
            "BUTT": (0.0, 0.0, v),
        },
        "pelvis_depth": lambda v: {
            "PELVIS": (v, 0.0, 0.0),
        },
        "belly": lambda v: {
            "BELLY": (v, 0.0, 0.0),
        },
    }

    def __init__(self, template_path: Optional[str] = None):
        """Initialize generator with base visual scene skeleton."""
        if template_path is None:
            # Default to bundled template
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            template_path = os.path.join(base_dir, "templates", "avatar_skeleton_template.xml")

        if not os.path.isfile(template_path):
            raise FileNotFoundError(f"Base skeleton template not found: {template_path}")

        with open(template_path, "r", encoding="utf-8") as f:
            self.visual_scene_template = f.read()

    def generate_single(
        self,
        name: str,
        bone_offsets: Dict[str, Tuple[float, float, float]],
        output_path: str,
    ) -> str:
        """Generate a single .dae deformer file.

        Args:
            name: Human-readable name of the deformer (e.g. 'Thigh_Width_L3')
            bone_offsets: Mapping of bone_name -> (dx, dy, dz) in meters
            output_path: Full file path to save the .dae file

        Returns:
            The path to the generated .dae file.
        """
        vs_xml = self.visual_scene_template

        # Apply offsets to visual scene bone matrices
        for bone_name, (dx, dy, dz) in bone_offsets.items():
            pattern = re.compile(
                r'(<node\s+id="' + re.escape(bone_name) + r'"[^>]*>[\s\S]*?<matrix\s+sid="transform">)([\s\S]*?)(</matrix>)',
                re.MULTILINE,
            )
            match = pattern.search(vs_xml)
            if match:
                prefix, mat_str, suffix = match.groups()
                tokens = mat_str.split()
                if len(tokens) == 16:
                    # Column 3 holds local translations: index 3 (x), 7 (y), 11 (z)
                    orig_x = float(tokens[3])
                    orig_y = float(tokens[7])
                    orig_z = float(tokens[11])

                    tokens[3] = f"{orig_x + dx:.6f}"
                    tokens[7] = f"{orig_y + dy:.6f}"
                    tokens[11] = f"{orig_z + dz:.6f}"

                    new_mat = (
                        f"\n  {tokens[0]}  {tokens[1]}  {tokens[2]}  {tokens[3]}\n"
                        f"  {tokens[4]}  {tokens[5]}  {tokens[6]}  {tokens[7]}\n"
                        f"  {tokens[8]}  {tokens[9]}  {tokens[10]}  {tokens[11]}\n"
                        f"  {tokens[12]}  {tokens[13]}  {tokens[14]}  {tokens[15]}\n"
                    )
                    vs_xml = vs_xml[:match.start(2)] + new_mat + vs_xml[match.end(2):]

        # Assemble clean Second Life compliant COLLADA DAE
        # Minimal 1-triangle carrier mesh at pelvis level (1mm, virtually invisible)
        # 100% weighted to mPelvis
        dae_content = f"""<?xml version="1.0" encoding="utf-8"?>
<COLLADA xmlns="http://www.collada.org/2005/11/COLLADASchema" version="1.4.1">
  <asset>
    <contributor>
      <author>Second Life Creator Suite</author>
      <authoring_tool>SL Deformer Generator v1.0</authoring_tool>
    </contributor>
    <created>2026-10-31T00:00:00</created>
    <modified>2026-10-31T00:00:00</modified>
    <unit name="meter" meter="1"/>
    <up_axis>Z_UP</up_axis>
  </asset>
  <library_materials>
    <material id="{name}_mat-material" name="{name}_mat">
      <instance_effect url="#{name}_mat-effect"/>
    </material>
  </library_materials>
  <library_effects>
    <effect id="{name}_mat-effect">
      <profile_COMMON>
        <technique sid="common">
          <phong>
            <diffuse><color>0.5 0.5 0.5 1</color></diffuse>
          </phong>
        </technique>
      </profile_COMMON>
    </effect>
  </library_effects>
  <library_geometries>
    <geometry id="{name}-mesh" name="{name}">
      <mesh>
        <source id="{name}-mesh-positions">
          <float_array id="{name}-mesh-positions-array" count="9">0 0 1.06701 0 0.001 1.06701 0 0 1.06801</float_array>
          <technique_common>
            <accessor source="#{name}-mesh-positions-array" count="3" stride="3">
              <param name="X" type="float"/>
              <param name="Y" type="float"/>
              <param name="Z" type="float"/>
            </accessor>
          </technique_common>
        </source>
        <source id="{name}-mesh-normals">
          <float_array id="{name}-mesh-normals-array" count="3">0 0 1</float_array>
          <technique_common>
            <accessor source="#{name}-mesh-normals-array" count="1" stride="3">
              <param name="X" type="float"/>
              <param name="Y" type="float"/>
              <param name="Z" type="float"/>
            </accessor>
          </technique_common>
        </source>
        <source id="{name}-mesh-map-0">
          <float_array id="{name}-mesh-map-0-array" count="6">0 0 1 0 0 1</float_array>
          <technique_common>
            <accessor source="#{name}-mesh-map-0-array" count="3" stride="2">
              <param name="S" type="float"/>
              <param name="T" type="float"/>
            </accessor>
          </technique_common>
        </source>
        <vertices id="{name}-mesh-vertices">
          <input semantic="POSITION" source="#{name}-mesh-positions"/>
        </vertices>
        <triangles material="{name}_mat" count="1">
          <input semantic="VERTEX" source="#{name}-mesh-vertices" offset="0"/>
          <input semantic="NORMAL" source="#{name}-mesh-normals" offset="1"/>
          <input semantic="TEXCOORD" source="#{name}-mesh-map-0" offset="2" set="0"/>
          <p>0 0 0 1 0 1 2 0 2</p>
        </triangles>
      </mesh>
    </geometry>
  </library_geometries>
  <library_controllers>
    <controller id="Avatar_{name}-skin" name="Avatar">
      <skin source="#{name}-mesh">
        <bind_shape_matrix>1 0 0 0 0 1 0 0 0 0 1 0 0 0 0 1</bind_shape_matrix>
        <source id="Avatar_{name}-skin-joints">
          <Name_array id="Avatar_{name}-skin-joints-array" count="1">mPelvis</Name_array>
          <technique_common>
            <accessor source="#Avatar_{name}-skin-joints-array" count="1" stride="1">
              <param name="JOINT" type="Name"/>
            </accessor>
          </technique_common>
        </source>
        <source id="Avatar_{name}-skin-bind_poses">
          <float_array id="Avatar_{name}-skin-bind_poses-array" count="16">1 0 0 0 0 1 0 0 0 0 1 -1.06702 0 0 0 1</float_array>
          <technique_common>
            <accessor source="#Avatar_{name}-skin-bind_poses-array" count="1" stride="16">
              <param name="TRANSFORM" type="float4x4"/>
            </accessor>
          </technique_common>
        </source>
        <source id="Avatar_{name}-skin-weights">
          <float_array id="Avatar_{name}-skin-weights-array" count="1">1</float_array>
          <technique_common>
            <accessor source="#Avatar_{name}-skin-weights-array" count="1" stride="1">
              <param name="WEIGHT" type="float"/>
            </accessor>
          </technique_common>
        </source>
        <joints>
          <input semantic="JOINT" source="#Avatar_{name}-skin-joints"/>
          <input semantic="INV_BIND_MATRIX" source="#Avatar_{name}-skin-bind_poses"/>
        </joints>
        <vertex_weights count="3">
          <input semantic="JOINT" source="#Avatar_{name}-skin-joints" offset="0"/>
          <input semantic="WEIGHT" source="#Avatar_{name}-skin-weights" offset="1"/>
          <vcount>1 1 1</vcount>
          <v>0 0 0 0 0 0</v>
        </vertex_weights>
      </skin>
    </controller>
  </library_controllers>
  <library_visual_scenes>
{vs_xml}
  </library_visual_scenes>
  <scene>
    <instance_visual_scene url="#Scene"/>
  </scene>
</COLLADA>
"""
        # Inject carrier mesh node under scene
        node_injection = f"""
    <node id="{name}" name="{name}" type="NODE">
      <translate sid="location">0 0 0</translate>
      <rotate sid="rotationZ">0 0 1 0</rotate>
      <rotate sid="rotationY">0 1 0 0</rotate>
      <rotate sid="rotationX">1 0 0 0</rotate>
      <scale sid="scale">1 1 1</scale>
      <instance_controller url="#Avatar_{name}-skin">
        <skeleton>#mPelvis</skeleton>
        <bind_material>
          <technique_common>
            <instance_material symbol="{name}_mat" target="#{name}_mat-material"/>
          </technique_common>
        </bind_material>
      </instance_controller>
    </node>
  </visual_scene>"""
        dae_content = dae_content.replace("</visual_scene>", node_injection)

        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(dae_content)

        return output_path

    def generate_preset_levels(
        self,
        preset_name: str,
        levels: int = 5,
        min_cm: float = 0.5,
        max_cm: float = 2.5,
        output_dir: str = "export/deformers",
    ) -> List[str]:
        """Generate a batch of interval levels for a given preset.

        Args:
            preset_name: Name of the preset (e.g. 'thigh_width', 'butt_projection')
            levels: Number of steps/levels to generate
            min_cm: Minimum offset in centimeters
            max_cm: Maximum offset in centimeters
            output_dir: Target directory to save all .dae files

        Returns:
            List of generated file paths.
        """
        if preset_name not in self.PRESETS:
            raise ValueError(f"Unknown preset: '{preset_name}'. Available: {list(self.PRESETS.keys())}")

        func = self.PRESETS[preset_name]
        step_size = (max_cm - min_cm) / (levels - 1) if levels > 1 else 0.0

        generated_files = []
        for i in range(levels):
            val_cm = min_cm + i * step_size
            val_meters = val_cm / 100.0
            offsets = func(val_meters)

            file_name = f"{preset_name}_L{i+1}_{val_cm:.1f}cm.dae"
            file_path = os.path.join(output_dir, file_name)
            name = f"{preset_name}_L{i+1}"

            self.generate_single(name, offsets, file_path)
            generated_files.append(file_path)

        return generated_files
