#!/bin/bash
# protect_board_fs.sh — harden the Orange Pi 5 root fs against power-loss
# corruption.  Run with:  bash protect_board_fs.sh  (sudo will be used).
#
# Why: the board was hard-powered-off repeatedly; /etc/fstab had
#   commit=600,errors=remount-ro  AND the ext4 superblock default mount
#   options were journal_data_writeback, and fsck never ran
#   (Maximum mount count -1).  Power loss then routinely left deployed
#   files (web_vis.py, start_webvis.sh) corrupted / all-zero.
#
# What this does:
#   1) fstab: commit=600 -> commit=30, add data=ordered (takes effect on
#      next boot; current session stays writeback until then)
#   2) superblock defaults -> journal_data_ordered (belt and suspenders;
#      effective even if fstab is ever lost)
#   3) periodic fsck: every 30 mounts or 30 days
#   4) immutable flag on deploy-critical files (must chattr -i before
#      redeploying them!)
set -e

ROOT_DEV=/dev/mmcblk1p1
DIR=/home/orangepi/kswlt_e2d

echo "[1/4] fstab -> commit=30, data=ordered"
sudo cp /etc/fstab /etc/fstab.bak.$(date +%Y%m%d)
sudo sed -i -E 's/(UUID=[^ ]+ \/ ext4 [^ ]*)commit=600/\1commit=30/' /etc/fstab
if ! grep -q 'data=ordered' /etc/fstab; then
  sudo sed -i -E 's/(UUID=[^ ]+ \/ ext4 [^ ]*)errors=remount-ro/\1data=ordered,errors=remount-ro/' /etc/fstab
fi
grep -E ' / ext4' /etc/fstab

echo "[2/4] ext4 superblock default -> journal_data_ordered"
sudo tune2fs -o journal_data_ordered $ROOT_DEV

echo "[3/4] periodic fsck (30 mounts / 30 days)"
sudo tune2fs -c 30 -i 30d $ROOT_DEV

echo "[4/4] immutable deploy files"
sudo chattr +i $DIR/web_vis.py $DIR/upstream_obs.py \
              $DIR/upstream_avoidance.onnx $DIR/upstream_avoidance.onnx.data \
              $DIR/start_webvis.sh /etc/systemd/system/web_vis.service
lsattr $DIR/web_vis.py $DIR/start_webvis.sh /etc/systemd/system/web_vis.service

echo
echo "NOTE: files are immutable. Before redeploying an updated file:"
echo "  sudo chattr -i <file>   # then upload, then chattr +i again"
echo "NOTE: always shut down with 'sudo poweroff' and wait for the LED to"
echo "      go out before removing power — nothing survives a hard power cut."
