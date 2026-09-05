# NX User-Space librealsense

- Version: `v2.58.4`; backend: V4L2.
- Install: `/home/nvidia/opt/librealsense-v4l2-2.58.4`.
- Runtime: set `LD_LIBRARY_PATH=/home/nvidia/opt/librealsense-v4l2-2.58.4/lib`.
- Verification: `rs-enumerate-devices -s` detects D435 serial `938422073656`, firmware `5.17.3.10`.
- No DKMS, kernel, L4T, BSP, udev rule, or system package was changed.
