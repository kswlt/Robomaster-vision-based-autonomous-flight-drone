# Architecture

## Development Platform

Windows/WSL source of truth connects through USB GbE `10.42.0.70/24` to Jetson `enP8p1s0` at `10.42.0.2/24`.

## Intended Validation Runtime

Stage A: D435 left IR + right IR → Pure Stereo VO → metric pose.

Stage B: D435 stereo + PX4 flight-controller IMU → Stereo-Inertial VIO.

Stage C: Stereo VO and Stereo-Inertial VIO A/B benchmarks → impact-aware estimator supervisor. On impact, invalidate the old pose, recover sensors, initialize a new local frame, then use a known marker/AprilTag to restore the field frame.

Depth remains outside the baseline estimator: initially it supports feature-depth lookup, obstacle range, health checks, target range, and recovery assistance.

## Hardware Fact

The connected camera is Intel RealSense D435. It has stereo IR, depth, and RGB, but no internal IMU. Future VIO therefore uses the PX4 flight-controller IMU.
