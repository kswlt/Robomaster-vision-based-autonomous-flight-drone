# Decisions

## D-001: Begin with a read-only NX audit

- Status: accepted
- Decision: Complete Phase 0 before installation, compilation, or system configuration.
- Reason: Preserve the Jetson BSP/L4T environment and establish evidence-backed baselines.
- Reversibility: fully reversible.

## D-002: Correct camera fact and VIO IMU source

- Status: accepted
- Decision: Treat the attached D435 as correct project hardware. Do not seek an internal camera IMU; future VIO uses the PX4 flight-controller IMU.
- Reason: USB descriptors verify D435 PID `8086:0b07`; D435 has no internal IMU by design.
- Reversibility: future hardware changes can be evaluated independently.

## D-003: Establish Pure Stereo VO before PX4-IMU VIO

- Status: accepted
- Decision: Implement and benchmark a reproducible D435 Pure Stereo VO baseline before integrating PX4 IMU, MAVLink time synchronization, or camera-IMU extrinsics.
- Reason: Severe impact may saturate or corrupt IMU measurements. Stereo tracking and recovery must be measured independently before deciding how IMU should participate in recovery.
- Consequence: The development sequence is Stereo VO → PX4 Stereo-Inertial VIO → A/B benchmark → impact-aware hybrid estimator supervisor.
- Reversibility: PX4 IMU integration remains a planned subsequent stage, not a rejected approach.
