#!/bin/bash
set -e
echo "=== WSL network ==="
ip route | grep default || true
GATEWAY=$(ip route | grep default | awk '{print $3}' || echo "172.22.0.1")
echo "Gateway: $GATEWAY"
echo "=== Testing proxy at $GATEWAY:7890 ==="
curl -x http://$GATEWAY:7890 -s -o /dev/null -w '%{http_code}' https://pypi.org/simple/pip/ --connect-timeout 5 || echo "proxy failed"
echo ""
echo "=== Testing direct ==="
curl -s -o /dev/null -w '%{http_code}' https://pypi.org/simple/pip/ --connect-timeout 5 || echo "direct failed"
echo ""
echo "GATEWAY=$GATEWAY" > /tmp/wsl_gateway.txt
