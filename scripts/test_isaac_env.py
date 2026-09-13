"""Minimal Isaac Sim environment test - writes results to file."""
import sys
import os
import traceback

OUTPUT_FILE = r"C:\Users\Admin\Desktop\端到端强化学习无人机仿真\results\isaac_env_test.txt"

def log(msg):
    print(msg, flush=True)
    with open(OUTPUT_FILE, "a", encoding="utf-8") as f:
        f.write(msg + "\n")

def main():
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write("=== Isaac Sim Environment Test ===\n")

    log(f"Python: {sys.version}")
    log(f"Python executable: {sys.executable}")

    try:
        from isaacsim import SimulationApp
        log("SUCCESS: imported isaacsim.SimulationApp")
    except Exception as e:
        log(f"FAIL: import SimulationApp: {e}")
        return 1

    try:
        app = SimulationApp({"headless": True})
        log("SUCCESS: SimulationApp created (headless)")
    except Exception as e:
        log(f"FAIL: create SimulationApp: {e}")
        traceback.print_exc()
        return 1

    # Debug: print sys.path after app creation
    log("--- sys.path after app creation ---")
    for p in sys.path:
        log(f"  {p}")

    # Try various import paths for World
    import_paths = [
        "omni.isaac.core",
        "isaacsim.core.api",
        "isaacsim.core.api.world",
        "isaacsim.core.api.world.world",
    ]
    for mod_path in import_paths:
        try:
            __import__(mod_path)
            log(f"SUCCESS: import {mod_path}")
        except Exception as e:
            log(f"FAIL: import {mod_path}: {e}")

    # Try to find World
    try:
        from isaacsim.core.api.world.world import World
        log("SUCCESS: from isaacsim.core.api.world.world import World")
    except Exception as e:
        log(f"FAIL: World import: {e}")

    try:
        world = World(stage_units_in_meters=1.0)
        log("SUCCESS: World created")
    except Exception as e:
        log(f"FAIL: create World: {e}")
        traceback.print_exc()
        app.close()
        return 1

    try:
        from isaacsim.core.api.objects import DynamicCuboid
        log("SUCCESS: imported DynamicCuboid from isaacsim.core.api.objects")
    except Exception as e:
        log(f"FAIL: import DynamicCuboid: {e}")
        traceback.print_exc()
        app.close()
        return 1

    try:
        import numpy as np
        cuboid = DynamicCuboid(
            prim_path="/World/test_cuboid",
            name="test_cuboid",
            position=np.array([0, 0, 1.0]),
            size=0.1,
            mass=0.1,
        )
        log("SUCCESS: DynamicCuboid created")
    except Exception as e:
        log(f"FAIL: create DynamicCuboid: {e}")
        traceback.print_exc()

    try:
        world.reset()
        log("SUCCESS: world.reset()")
    except Exception as e:
        log(f"FAIL: world.reset(): {e}")
        traceback.print_exc()

    try:
        for i in range(10):
            world.step(render=False)
        pos, _ = cuboid.get_world_pose()
        log(f"SUCCESS: 10 physics steps, cuboid z={pos[2]:.4f}")
    except Exception as e:
        log(f"FAIL: physics step: {e}")
        traceback.print_exc()

    try:
        import warp as wp
        log(f"SUCCESS: warp {wp.__version__}, CUDA available: {wp.is_cuda_available()}")
    except Exception as e:
        log(f"WARN: import warp: {e}")

    log("=== ALL TESTS PASSED ===")

    try:
        app.close()
        log("SUCCESS: app.close()")
    except Exception as e:
        log(f"WARN: app.close(): {e}")

    return 0

if __name__ == "__main__":
    sys.exit(main())
