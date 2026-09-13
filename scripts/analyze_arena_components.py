#!/usr/bin/env python3
"""Component-level STL analysis for unit calibration.

The arena STL raw extents (29.15 x 16.05 x 18.04) do not map cleanly to a
standard 14m x 14m RMUC field under mm/cm/m assumptions. This script splits
the mesh into connected components and reports their extents so known RoboMaster
objects (armor plates, obstacle frames, walls) can be used to calibrate units.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import trimesh

ARENA_STL = Path(__file__).resolve().parent.parent / "assets" / "source" / "arena" / "rmuc_2026_arena.stl"
OUT = Path(__file__).resolve().parent.parent / "assets" / "manifests" / "arena_components.json"


def main() -> None:
    mesh = trimesh.load(ARENA_STL, force="mesh")
    comps = mesh.split(only_watertight=False)

    rows = []
    for i, c in enumerate(comps):
        ext = (c.bounds[1] - c.bounds[0]).tolist()
        rows.append(
            {
                "index": i,
                "triangles": int(len(c.faces)),
                "vertices": int(len(c.vertices)),
                "extents_xyz": ext,
                "max_extent": float(np.max(ext)),
                "center": c.bounds.mean(axis=0).tolist(),
            }
        )

    rows.sort(key=lambda r: -r["triangles"])
    report = {
        "component_count": len(rows),
        "top_components_by_triangles": rows[:40],
        "z_histogram_edges": None,
        "z_histogram_counts": None,
    }

    # z-layer histogram to identify floor / wall tops
    z = mesh.vertices[:, 2]
    hist, edges = np.histogram(z, bins=64)
    report["z_histogram_edges"] = edges.tolist()
    report["z_histogram_counts"] = hist.tolist()

    OUT.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(f"components: {len(rows)}")
    print(f"{'idx':>4} {'tri':>8} {'maxExt':>8} {'extents':>40} center")
    for r in rows[:40]:
        e = ",".join(f"{v:.3f}" for v in r["extents_xyz"])
        cen = ",".join(f"{v:.2f}" for v in r["center"])
        print(f"{r['index']:>4} {r['triangles']:>8} {r['max_extent']:>8.3f} [{e}] ({cen})")
    print("\nz histogram (nonzero bins):")
    for k in range(len(hist)):
        if hist[k] > 0:
            print(f"  z in [{edges[k]:.3f},{edges[k+1]:.3f}): {hist[k]}")


if __name__ == "__main__":
    main()
