#!/bin/bash
echo "=== Python packages ==="
pip3 list 2>/dev/null | grep -iE "rknn|onnx|opencv|numpy|torch|pyserial|pillow"
echo ""
echo "=== Python version ==="
python3 --version
echo ""
echo "=== NPU device ==="
ls -la /dev/dri/renderD* 2>/dev/null
echo ""
echo "=== RKNPU kernel module ==="
lsmod | grep -i rknpu
echo ""
echo "=== Disk ==="
df -h / | tail -1
echo ""
echo "=== RAM ==="
free -h | head -2
echo ""
echo "=== CPU info ==="
cat /proc/cpuinfo | grep "model name" | head -1
echo "Cores: $(nproc)"
echo ""
echo "=== Temperature ==="
cat /sys/class/thermal/thermal_zone0/temp 2>/dev/null && echo " (mC)"
echo ""
echo "=== Git ==="
git --version
