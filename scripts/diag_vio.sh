#!/bin/bash
echo "=== start_vio_systemd.sh ==="
cat /home/orangepi/kswlt/tools/start_vio_systemd.sh 2>/dev/null || echo "not found"

echo ""
echo "=== watchdog_camera.service ==="
systemctl cat watchdog_camera.service 2>/dev/null || echo "not found"

echo ""
echo "=== vio.service ==="
systemctl cat vio.service 2>/dev/null || echo "not found"

echo ""
echo "=== kswlt directory structure ==="
ls -la /home/orangepi/kswlt/ 2>/dev/null || echo "not found"
ls -la /home/orangepi/kswlt/tools/ 2>/dev/null || echo "no tools dir"
