#!/bin/bash
# Stop VIO system and test D430 depth capture

echo "=== STEP 1: Stop watchdog + vio services ==="
echo "orangepi" | sudo -S systemctl stop watchdog_camera.service 2>&1
echo "orangepi" | sudo -S systemctl stop vio.service 2>&1
sleep 2

echo "=== STEP 2: Kill any remaining realsense/ros processes ==="
pkill -9 -f 'realsense2_camera' 2>/dev/null
pkill -9 -f 'ov_msckf' 2>/dev/null
pkill -9 -f 'vio_bridge_combined' 2>/dev/null
pkill -9 -f 'start_vio_systemd' 2>/dev/null
sleep 3

echo "=== STEP 3: Verify camera is free ==="
ps aux | grep -iE 'realsense|ov_msckf|vio_bridge' | grep -v grep || echo "All VIO processes stopped"
ls -la /dev/video* 2>/dev/null

echo "=== STEP 4: Clear dmesg ring (recent) ==="
echo "orangepi" | sudo -S dmesg -C 2>&1 || echo "dmesg clear skipped"

echo "=== STEP 5: pyrealsense2 depth test ==="
cd ~/kswlt_e2d
python3 -c "
import pyrealsense2 as rs
import numpy as np
import time

print('pyrealsense2 version:', rs.__version__)
print('Creating pipeline...')
pipeline = rs.pipeline()
config = rs.config()

# Try depth stream at 640x480 Z16
config.enable_stream(rs.stream.depth, 640, 480, rs.format.z16, 30)

print('Starting pipeline (640x480 Z16 @30)...')
try:
    profile = pipeline.start(config)
    print('Pipeline started OK!')
    
    # Get depth sensor and scale
    depth_sensor = profile.get_device().first_depth_sensor()
    depth_scale = depth_sensor.get_depth_scale()
    print(f'Depth scale: {depth_scale}')
    
    # Capture 5 frames
    for i in range(5):
        frames = pipeline.wait_for_frames(timeout_ms=5000)
        depth_frame = frames.get_depth_frame()
        if depth_frame:
            depth_image = np.asanyarray(depth_frame.get_data())
            valid = (depth_image > 0)
            print(f'Frame {i}: shape={depth_image.shape}, valid_px={valid.sum()}/{depth_image.size} ({100*valid.mean():.1f}%), mean_depth={depth_image[valid].mean()*depth_scale:.2f}m' if valid.any() else f'Frame {i}: shape={depth_image.shape}, no valid pixels')
        else:
            print(f'Frame {i}: no depth frame')
    
    pipeline.stop()
    print('Depth test PASSED!')
except Exception as e:
    print(f'Depth test FAILED: {type(e).__name__}: {e}')
" 2>&1

echo ""
echo "=== STEP 6: Check dmesg for new UVC errors ==="
echo "orangepi" | sudo -S dmesg | grep -i uvc | tail -10 || echo "No new UVC errors"

echo ""
echo "=== STEP 7: v4l2 capture test (video0, Z16 640x480) ==="
v4l2-ctl -d /dev/video0 --set-fmt-video=width=640,height=480,pixelformat=Z16 --stream-mmap --stream-count=5 2>&1 || echo "v4l2 test failed"
