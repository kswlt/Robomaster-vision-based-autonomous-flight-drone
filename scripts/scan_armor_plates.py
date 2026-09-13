#!/usr/bin/env python3
"""Scan arena components for flat plate-like objects (armor plate candidates).

Unit is now known to be meters (RMUC 2026 battlefield 28m x 15m). This script
reports thin plates whose in-plane dimensions fall in plausible armor-plate
ranges, so armor.yaml can pick a concrete target location.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import trimesh

ARENA_STL = Path(__file__).resolve().parent.parent / "assets" / "source" / "arena" / "rmuc_2026_arena.stl"
OUT = Path(__file__).resolve().parent.parent / "assets" / "manifests" / "armor_plate_candidates.json"


def main() -> None:
    mesh = trimesh.load(ARENA_STL, force="mesh")
    comps = mesh.split(only_watertight=False)

    plates = []
    for i, c in enumerate(comps):
        e = c.bounds[1] - c.bounds[0]
        order = np.argsort(e)  # ascending: thinnest first
        thin = float(e[order[0]])
        wide1 = float(e[order[1]])
        wide2 = float(e[order[2]])
        if thin <= 0.0 and wide1 > 0.0:
            thin_ratio = 1e9
        elif thin <= 0.0:
            continue
        else:
            thin_ratio = wide2 / thin
        # plausible armor plate: thin (<= 0.05 m), in-plane 0.05..0.6 m
        if 0.0 < thin <= 0.05 and 0.05 <= wide1 <= 0.6 and 0.05 <= wide2 <= 0.6 and len(c.faces) >= 4:
            plates.append(
                {
                    "index": i,
                    "triangles": int(len(c.faces)),
                    "extents_xyz": e.tolist(),
                    "thin_dim_axis": int(order[0]),
                    "in_plane": [wide1, wide2],
                    "center": c.bounds.mean(axis=0).tolist(),
                    "bounds_min": c.bounds[0].tolist(),
                    "bounds_max": c.bounds[1].tolist(),
                }
            )

    plates.sort(key=lambda r: (round(r["center"][2], 1), r["center"][0], r["center"][1]))
    report = {"candidate_count": len(plates), "candidates": plates}
    OUT.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(f"armor-plate candidates: {len(plates)}")
    for p in plates:
        e = ",".join(f"{v:.4f}" for v in p["extents_xyz"])
        cen = ",".join(f"{v:.3f}" for v in p["center"])
        print(f"  idx={p['index']:>6} tri={p['triangles']:>4} ext=[{e}] center=({cen}) inplane={p['in_plane']}")


if __name__ == "__main__":
    main()
