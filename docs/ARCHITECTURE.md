# Architecture

## Development Platform

Windows/WSL source of truth connects through USB GbE `10.42.0.70/24` to Jetson `enP8p1s0` at `10.42.0.2/24`.

## Intended Validation Runtime

Intel RealSense D435i left IR + right IR + IMU → stereo-inertial VIO → 6DoF pose and velocity.

Depth is initially an independent auxiliary signal, not a change to VIO filter equations.

## Current Hardware Exception

The connected camera is D435 rather than D435i and has no IMU interface. It cannot feed the intended stereo-inertial pipeline.
