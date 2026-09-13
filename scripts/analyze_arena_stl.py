#!/usr/bin/env python3
"""Analyze RoboMaster arena STL: geometry, scale hints, mesh quality.

Outputs a JSON report used to populate configs/arena.yaml and docs/ASSETS.md.
Never modifies the source STL (read-only).
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import trimesh

ARENA_STL = Path(__file__).resolve().parent.parent / "assets" / "source" / "arena" / "rmuc_2026_arena.stl"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest().upper()


def main() -> int:
    if not ARENA_STL.exists():
        print(f"ERROR: STL not found: {ARENA_STL}", file=sys.stderr)
        return 1

    report: dict = {"file": str(ARENA_STL), "sha256": sha256(ARENA_STL)}

    mesh = trimesh.load(ARENA_STL, force="mesh")
    report["file_size_bytes"] = ARENA_STL.stat().st_size

    # --- basic counts ---
    report["triangle_count"] = int(len(mesh.faces))
    report["vertex_count"] = int(len(mesh.vertices))

    # --- bounds (do NOT assume units) ---
    lo = mesh.bounds[0].tolist()
    hi = mesh.bounds[1].tolist()
    extents = (mesh.bounds[1] - mesh.bounds[0]).tolist()
    report["bounds_min"] = lo
    report["bounds_max"] = hi
    report["extents_xyz"] = extents

    # --- mesh quality ---
    report["watertight"] = bool(mesh.is_watertight)
    report["volume_valid"] = bool(mesh.is_volume)
    if mesh.is_volume:
        report["volume"] = float(mesh.volume)
    else:
        report["volume"] = None

    # --- winding / normals ---
    report["winding_consistent"] = bool(mesh.is_winding_consistent)

    # --- components (connected bodies) ---
    try:
        comps = mesh.split(only_watertight=False)
        report["component_count"] = int(len(comps))
        comp_stats = []
        for i, c in enumerate(comps):
            e = (c.bounds[1] - c.bounds[0]).tolist()
            comp_stats.append(
                {
                    "index": i,
                    "triangles": int(len(c.faces)),
                    "extents_xyz": e,
                    "center": c.bounds.mean(axis=0).tolist(),
                }
            )
        report["components"] = comp_stats
    except Exception as exc:  # pragma: no cover - defensive
        report["component_count"] = None
        report["component_error"] = str(exc)

    # --- degenerate faces / area sanity ---
    try:
        areas = mesh.area_faces
        report["surface_area"] = float(mesh.area)
        report["zero_area_faces"] = int(np.sum(areas <= 1e-12))
    except Exception as exc:  # pragma: no cover
        report["surface_area"] = None
        report["area_error"] = str(exc)

    # --- scale inference (hints only, NOT authoritative) ---
    # RoboMaster arena: official field is ~ 14 m x 14 m (RMUC 2023+); the
    # extracted extents tell us if the STL is in mm, cm or m.
    max_extent = float(np.max(extents))
    guesses = {
        "m": max_extent,
        "cm": max_extent / 100.0,
        "mm": max_extent / 1000.0,
    }
    # Official RMUC field width is 14 m (one side). Check which unit lands near 14.
    closest = min(guesses.items(), key=lambda kv: abs(kv[1] - 14.0))
    report["scale_hints"] = {
        "max_extent_raw": max_extent,
        "if_mm_side_m": guesses["mm"],
        "if_cm_side_m": guesses["cm"],
        "if_m_side_m": guesses["m"],
        "closest_to_14m_assuming_unit": closest[0],
    }

    out = Path(__file__).resolve().parent.parent / "assets" / "manifests" / "arena_analysis.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
