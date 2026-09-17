#!/bin/bash
# Thorough camera diagnostic with VIO stopped

echo "=== Confirm VIO still stopped ==="
ps aux | grep -iE 'realsense|ov_msckf|vio_bridge|watchdog_camera' | grep -v grep || echo "VIO fully stopped"
systemctl is-active watchdog_camera.service vio.service 2>&1

echo ""
echo "=== USB device state ==="
lsusb -t
echo "---"
lsusb -v -d 8086:0ad4 2>&1 | head -30

echo ""
echo "=== TEST 1: Infrared capture (video2, GREY 640x480) ==="
python3 -c "
import cv2
import numpy as np
cap = cv2.VideoCapture('/dev/video2', cv2.CAP_V4L2)
cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'GREY'))
cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
print('Camera opened:', cap.isOpened())
if cap.isOpened():
    for i in range(5):
        ret, frame = cap.read()
        if ret:
            print(f'IR frame {i}: shape={frame.shape}, mean={frame.mean():.1f}, min={frame.min()}, max={frame.max()}')
        else:
            print(f'IR frame {i}: read FAILED')
    cap.release()
else:
    print('Cannot open /dev/video2')
" 2>&1

echo ""
echo "=== TEST 2: Depth via v4l2 direct (video0) ==="
python3 -c "
import v4l2
import fcntl
import os

dev = '/dev/video0'
fd = os.open(dev, os.O_RDWR)
print(f'Opened {dev}, fd={fd}')

# Query capabilities
cap = v4l2.v4l2_capability()
fcntl.ioctl(fd, v4l2.VIDIOC_QUERYCAP, cap)
print(f'Driver: {cap.driver.decode()}, Card: {cap.card.decode()}')
print(f'Capabilities: {hex(cap.capabilities)}')

# Try format
fmt = v4l2.v4l2_format()
fmt.type = v4l2.V4L2_BUF_TYPE_VIDEO_CAPTURE
fmt.fmt.pix.width = 640
fmt.fmt.pix.height = 480
fmt.fmt.pix.pixelformat = v4l2.V4L2_PIX_FMT_Z16
try:
    fcntl.ioctl(fd, v4l2.VIDIOC_S_FMT, fmt)
    print(f'S_FMT OK: {fmt.fmt.pix.width}x{fmt.fmt.pix.height}, fmt={hex(fmt.fmt.pix.pixelformat)}')
except Exception as e:
    print(f'S_FMT FAILED: {e}')

os.close(fd)
" 2>&1

echo ""
echo "=== TEST 3: Full USB power cycle ==="
# Find the USB device path
USB_BUS="003"
USB_DEV="002"
# Get the sysfs path
SYSFS_PATH=$(find /sys/bus/usb/devices/ -maxdepth 1 -name "3-1" 2>/dev/null)
echo "Sysfs path: $SYSFS_PATH"
if [ -n "$SYSFS_PATH" ]; then
    echo "Unbinding USB device..."
    echo "3-1" | sudo tee /sys/bus/usb/drivers/usb/unbind 2>&1
    sleep 3
    echo "lsusb after unbind:"
    lsusb | grep -i 8086 || echo "Device gone (expected)"
    echo "Rebinding USB device..."
    echo "3-1" | sudo tee /sys/bus/usb/drivers/usb/bind 2>&1
    sleep 5
    echo "lsusb after rebind:"
    lsusb | grep -i 8086 || echo "Device NOT reappeared!"
    ls -la /dev/video* 2>/dev/null
fi

echo ""
echo "=== TEST 4: pyrealsense2 after USB reset ==="
python3 -c "
import pyrealsense2 as rs
ctx = rs.context()
devices = ctx.query_devices()
print(f'Devices found: {len(devices)}')
for d in devices:
    print(f'  - {d.get_info(rs.camera_info.name)} (SN: {d.get_info(rs.camera_info.serial_number)})')
    sensors = d.query_sensors()
    for s in sensors:
        print(f'    Sensor: {s.get_info(rs.camera_info.name)}')
if len(devices) > 0:
    print('Trying depth stream...')
    pipeline = rs.pipeline()
    config = rs.config()
    config.enable_stream(rs.stream.depth, 640, 480, rs.format.z16, 30)
    try:
        profile = pipeline.start(config)
        frames = pipeline.wait_for_frames(timeout_ms=5000)
        depth = frames.get_depth_frame()
        if depth:
            import numpy as np
            img = np.asanyarray(depth.get_data())
            print(f'Depth frame OK: shape={img.shape}, valid={(img>0).sum()}/{img.size}')
        pipeline.stop()
        print('DEPTH TEST PASSED!')
    except Exception as e:
        print(f'Depth stream FAILED: {e}')
" 2>&1

echo ""
echo "=== DMESG after all tests ==="
sudo dmesg | tail -30
