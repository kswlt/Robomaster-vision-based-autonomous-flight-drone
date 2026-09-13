#!/usr/bin/env python3
"""Render arena projections to PNG for structure identification.

Top-down (x-y) and side (x-z) scatter projections, colored by height.
Output goes to assets/manifests/arena_preview_*.png. Read-only on the STL.
"""
from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import trimesh

ARENA_STL = Path(__file__).resolve().parent.parent / "assets" / "source" / "arena" / "rmuc_2026_arena.stl"
OUT_DIR = Path(__file__).resolve().parent.parent / "assets" / "manifests"


def main() -> None:
    mesh = trimesh.load(ARENA_STL, force="mesh")
    v = mesh.vertices  # (N,3)
    x, y, z = v[:, 0], v[:, 1], v[:, 2]

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # 1) top-down, color = height
    fig, ax = plt.subplots(figsize=(16, 9), dpi=110)
    sc = ax.scatter(x, y, c=z, s=0.35, cmap="turbo")
    ax.set_aspect("equal")
    ax.set_title(f"RMUC 2026 arena top-down (raw units; N={len(v)} verts)")
    ax.set_xlabel("x"); ax.set_ylabel("y")
    plt.colorbar(sc, label="z (raw units)")
    fig.tight_layout()
    fig.savefig(OUT_DIR / "arena_preview_topdown.png")
    plt.close(fig)

    # 2) side view x-z
    fig, ax = plt.subplots(figsize=(16, 6), dpi=110)
    ax.scatter(x, z, c=y, s=0.35, cmap="viridis")
    ax.set_aspect("equal")
    ax.set_title("RMUC 2026 arena side view (x-z, color=y)")
    ax.set_xlabel("x"); ax.set_ylabel("z")
    fig.tight_layout()
    fig.savefig(OUT_DIR / "arena_preview_side.png")
    plt.close(fig)

    # 3) side view y-z
    fig, ax = plt.subplots(figsize=(16, 6), dpi=110)
    ax.scatter(y, z, c=x, s=0.35, cmap="viridis")
    ax.set_aspect("equal")
    ax.set_title("RMUC 2026 arena side view (y-z, color=x)")
    ax.set_xlabel("y"); ax.set_ylabel("z")
    fig.tight_layout()
    fig.savefig(OUT_DIR / "arena_preview_side_yz.png")
    plt.close(fig)

    print("saved:", [p.name for p in OUT_DIR.glob("arena_preview_*.png")])


if __name__ == "__main__":
    main()
