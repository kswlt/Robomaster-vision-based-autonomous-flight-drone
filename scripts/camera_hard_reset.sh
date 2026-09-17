#!/bin/bash
# Aggressive camera reset: kill all, unload uvcvideo, USB power cycle, reload

echo "=== STEP 1: Kill ALL camera-related processes ==="
# Kill vio-improve watchdog
sudo kill -9 1343 2>/dev/null
# Kill anything touching /dev/video*
for pid in $(sudo lsof -t /dev/video0 /dev/video1 /dev/video2 /dev/video3 2>/dev/null); do
    echo "Killing pid $pid using video device"
    sudo kill -9 $pid 2>/dev/null
done
pkill -9 -f 'watchdog_camera' 2>/dev/null
pkill -9 -f 'realsense' 2>/dev/null
pkill -9 -f 'vio_' 2>/dev/null
sleep 2

echo "Remaining camera processes:"
ps aux | grep -iE 'realsense|vio_|watchdog|camera' | grep -v grep || echo "  none"

echo ""
echo "=== STEP 2: Unload uvcvideo driver ==="
sudo modprobe -r uvcvideo 2>&1
sleep 2
lsmod | grep uvcvideo || echo "uvcvideo unloaded"
ls -la /dev/video* 2>/dev/null || echo "No /dev/video* (expected)"

echo ""
echo "=== STEP 3: USB port power cycle (authorized toggle) ==="
echo "Current authorized:"
cat /sys/bus/usb/devices/3-1/authorized 2>/dev/null
echo "Deauthorizing..."
echo 0 | sudo tee /sys/bus/usb/devices/3-1/authorized 2>&1
sleep 3
echo "lsusb after deauthorize:"
lsusb | grep -i 8086 || echo "  Device gone (expected)"
echo "Reauthorizing..."
echo 1 | sudo tee /sys/bus/usb/devices/3-1/authorized 2>&1
sleep 5
echo "lsusb after reauthorize:"
lsusb | grep -i 8086 || echo "  Device NOT reappeared!"

echo ""
echo "=== STEP 4: Reload uvcvideo ==="
sudo modprobe uvcvideo 2>&1
sleep 3
ls -la /dev/video* 2>/dev/null || echo "No /dev/video* after reload"

echo ""
echo "=== STEP 5: Clear dmesg ==="
sudo dmesg -C 2>&1

echo ""
echo "=== STEP 6: pyrealsense2 test (clean state) ==="
python3 -c "
import pyrealsense2 as rs
import numpy as np
import time

ctx = rs.context()
devices = ctx.query_devices()
print(f'Devices found: {len(devices)}')
for d in devices:
    print(f'  Name: {d.get_info(rs.camera_info.name)}')
    print(f'  Serial: {d.get_info(rs.camera_info.serial_number)}')
    print(f'  FW: {d.get_info(rs.camera_info.firmware_version)}')
    sensors = d.query_sensors()
    for s in sensors:
        print(f'  Sensor: {s.get_info(rs.camera_info.name)}')

if len(devices) == 0:
    print('NO DEVICES - camera USB not responding')
else:
    # Try hardware reset first
    print('Trying hardware_reset...')
    try:
        devices[0].hardware_reset()
        print('hardware_reset OK')
        sleep(3)
        # Re-query
        ctx2 = rs.context()
        devices2 = ctx2.query_devices()
        print(f'Devices after reset: {len(devices2)}')
    except Exception as e:
        print(f'hardware_reset failed: {e}')

    # Try depth stream
    print('Starting depth pipeline...')
    pipeline = rs.pipeline()
    config = rs.config()
    config.enable_stream(rs.stream.depth, 640, 480, rs.format.z16, 30)
    try:
        profile = pipeline.start(config)
        print('Pipeline started!')
        for i in range(5):
            frames = pipeline.wait_for_frames(timeout_ms=5000)
            depth = frames.get_depth_frame()
            if depth:
                img = np.asanyarray(depth.get_data())
                valid = (img > 0).sum()
                print(f'  Frame {i}: shape={img.shape}, valid={valid}/{img.size} ({100*valid/img.size:.1f}%)')
            else:
                print(f'  Frame {i}: no depth')
        pipeline.stop()
        print('DEPTH TEST PASSED!')
    except Exception as e:
        print(f'Depth pipeline FAILED: {type(e).__name__}: {e}')
" 2>&1

echo ""
echo "=== STEP 7: dmesg after test ==="
sudo dmesg | grep -iE 'uvc|usb 3-1|8086' | tail -20
