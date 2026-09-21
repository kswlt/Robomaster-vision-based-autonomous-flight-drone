#!/bin/bash
# E2E-RL web_vis launcher — delegates to the systemd unit (auto-restarts on
# crash and after a reboot; the old nohup+pkill approach died silently when
# unattended-upgrades rebooted the board).
sudo systemctl restart web_vis.service
sleep 5
systemctl is-active web_vis.service
ps aux | grep web_vis | grep -v grep | head -1
echo "---LOG---"
tail -10 /home/orangepi/kswlt_e2d/web_vis.log
echo "---STATUS---"
curl -s --max-time 3 http://127.0.0.1:8080/status | head -c 200
echo ""