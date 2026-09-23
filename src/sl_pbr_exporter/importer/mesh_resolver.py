"""Scan, identify, and resolve outfit items from folders, DAE files, and Second Life XMLs."""

import json
from pathlib import Path
from typing import Any, Dict, List


def scan_directory_items(folder_path: Path) -> List[Dict[str, Any]]:
    """Scan a directory for importable outfit items (outfit_items.json, .dae files, or .xml files)."""
    if not folder_path or not folder_path.exists() or not folder_path.is_dir():
        return []

    items: List[Dict[str, Any]] = []
    seen_names = set()

    # 1. Check for outfit_items.json manifest
    manifest_path = folder_path / "outfit_items.json"
    if manifest_path.exists():
        try:
            with open(manifest_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                for entry in data:
                    dae_rel = entry.get("dae")
                    name = entry.get("name") or (Path(dae_rel).stem if dae_rel else "Item")
                    dae_path = folder_path / dae_rel if dae_rel else None
                    if dae_path and dae_path.exists() and name not in seen_names:
                        seen_names.add(name)
                        items.append({
                            "name": name,
                            "type": "DAE",
                            "path": str(dae_path),
                            "textures_dir": str(folder_path / "textures"),
                        })
        except Exception:
            pass

    # 2. Check for .dae files directly in directory
    for dae in sorted(folder_path.glob("*.dae")):
        if "_combined" in dae.name.lower() or "_sl" in dae.name.lower():
            continue
        if dae.stem not in seen_names:
            seen_names.add(dae.stem)
            items.append({
                "name": dae.stem,
                "type": "DAE",
                "path": str(dae),
                "textures_dir": str(folder_path / "textures"),
            })

    # 3. Check for .dae files in immediate subdirectories (single-item mode folders)
    for sub in folder_path.iterdir():
        if sub.is_dir() and sub.name != "textures":
            for dae in sub.glob("*.dae"):
                if dae.stem not in seen_names:
                    seen_names.add(dae.stem)
                    items.append({
                        "name": dae.stem,
                        "type": "DAE",
                        "path": str(dae),
                        "textures_dir": str(sub / "textures"),
                    })

    # 4. Check for Second Life object XML files
    for xml in sorted(folder_path.glob("*.xml")):
        name_lower = xml.name.lower()
        if name_lower.endswith(("_bakes.xml", "_shape.xml", "bakes.xml", "shape.xml")):
            continue
        if xml.stem not in seen_names:
            seen_names.add(xml.stem)
            items.append({
                "name": xml.stem,
                "type": "XML",
                "path": str(xml),
                "textures_dir": str(folder_path / "textures"),
            })

    return items
