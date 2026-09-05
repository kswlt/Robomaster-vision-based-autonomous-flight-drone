# Architecture

## Development Platform

Windows desktop and WSL maintain the source-of-truth repository. A wired Ethernet link connects the development host to the Jetson Orin NX.

## Intended Validation Runtime

Intel RealSense D435i left IR + right IR + IMU → stereo-inertial VIO → 6DoF pose and velocity.

Depth is initially an independently evaluated auxiliary signal, not a modification to the VIO filter equations.
