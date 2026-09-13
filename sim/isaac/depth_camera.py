"""Simulated depth camera (Isaac ideal depth, phase 1 no noise)."""
from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import numpy as np

from sim.common.config import repo_root


class DepthCamera:
    """Front-facing depth camera mounted on drone.

    All parameters from configs/depth_camera.yaml.
    Supports PNG/NPY export, min/max logging, valid pixel ratio, FPS, timestamp.
    """

    def __init__(self, cfg: dict[str, Any], drone):
        self.cfg = cfg["depth_camera"]
        self.drone = drone
        self.width = self.cfg["width"]
        self.height = self.cfg["height"]
        self.fov = self.cfg["fov_deg"]
        self.near = self.cfg["near_m"]
        self.far = self.cfg["far_m"]
        self.fps = self.cfg["fps"]
        self.mount_pos = np.array(self.cfg["mount"]["position"], dtype=float)
        self.mount_rot = np.array(self.cfg["mount"]["rotation"], dtype=float)
        self._camera = None
        self._frame_count = 0
        self._last_time = time.time()

    def build(self, world):
        """Attach depth camera to drone prim."""
        drone_pos = self.drone.get_position()
        cam_pos = drone_pos + self.mount_pos

        # Try Isaac Sim 6.x import first, then legacy
        Camera = None
        try:
            from isaacsim.sensors.camera import Camera
        except ImportError:
            try:
                from omni.isaac.sensor import Camera
            except ImportError:
                pass

        if Camera is not None:
            try:
                self._camera = Camera(
                    prim_path="/World/Sensors/DepthCamera",
                    name="front_depth",
                    position=cam_pos,
                    resolution=(self.width, self.height),
                )
                self._camera.set_focal_length(self._fov_to_focal())
                self._camera.set_clipping_range(self.near, self.far)
            except Exception as e:
                print(f"[WARN] Depth camera build failed: {e}, using synthetic depth")
                self._camera = None
        else:
            print("[WARN] Camera class not available, using synthetic depth")
            self._camera = None
        return self

    def _fov_to_focal(self) -> float:
        """Convert horizontal FOV (deg) to focal length in pixels."""
        return 0.5 * self.width / np.tan(np.deg2rad(self.fov) / 2)

    def update(self):
        """Update camera pose to follow drone."""
        if self._camera is None:
            return
        drone_pos = self.drone.get_position()
        self._camera.set_world_pose(position=drone_pos + self.mount_pos)

    def get_depth(self) -> np.ndarray:
        """Return depth image as float32 numpy array (meters)."""
        if self._camera is not None:
            data = self._camera.get_depth()
            if data is not None:
                return data.astype(np.float32)
        # Fallback: synthetic depth for testing without Isaac
        return self._synthetic_depth()

    def _synthetic_depth(self) -> np.ndarray:
        """Generate synthetic depth for unit tests (no Isaac needed)."""
        depth = np.full((self.height, self.width), 5.0, dtype=np.float32)
        return depth

    def normalize(self, depth: np.ndarray) -> np.ndarray:
        """Apply inverse-depth normalization matching DiffPhys preprocessing."""
        mode = self.cfg["normalization"]["mode"]
        if mode == "inverse_depth":
            with np.errstate(divide="ignore"):
                inv = 1.0 / depth
            inv[~np.isfinite(inv)] = 0.0
            return inv.astype(np.float32)
        return depth

    def save(self, depth: np.ndarray, tag: str = "frame"):
        """Save depth as PNG and NPY."""
        out_dir = repo_root() / "results" / "depth_frames"
        out_dir.mkdir(parents=True, exist_ok=True)
        np.save(out_dir / f"{tag}_{self._frame_count:06d}.npy", depth)
        # PNG via matplotlib (16-bit would be better but this works)
        try:
            import matplotlib
            matplotlib.use("Agg")
            import matplotlib.pyplot as plt
            fig, ax = plt.subplots(figsize=(4, 3), dpi=100)
            ax.imshow(depth, cmap="viridis")
            ax.axis("off")
            fig.tight_layout()
            fig.savefig(out_dir / f"{tag}_{self._frame_count:06d}.png")
            plt.close(fig)
        except Exception:
            pass
        self._frame_count += 1

    def stats(self, depth: np.ndarray) -> dict:
        """Compute min/max/valid ratio/timestamp/FPS."""
        now = time.time()
        dt = now - self._last_time
        actual_fps = 1.0 / dt if dt > 0 else 0.0
        self._last_time = now
        valid = np.isfinite(depth) & (depth > self.near) & (depth < self.far)
        return {
            "min": float(np.min(depth[valid])) if valid.any() else 0.0,
            "max": float(np.max(depth[valid])) if valid.any() else 0.0,
            "valid_pixel_ratio": float(np.mean(valid)),
            "timestamp": now,
            "fps": actual_fps,
        }
