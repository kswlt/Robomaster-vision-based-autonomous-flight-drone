# Decisions

## D-001: Begin with a read-only NX audit

- Status: accepted
- Decision: Complete Phase 0 before installation, compilation, or system configuration.
- Reason: Preserve the Jetson BSP/L4T environment and establish evidence-backed baselines.
- Reversibility: fully reversible.

## D-002: Do not advance VIO work with the attached D435

- Status: accepted
- Decision: Block Phase 1/2 until a D435i or equivalent camera/IMU source is attached.
- Reason: USB descriptors verify D435 PID `8086:0b07`; no HID/IIO IMU nodes exist. Video-only D435 cannot validate the D435i stereo-inertial architecture.
- Reversibility: attach D435i and repeat enumeration; a separately approved depth-only scope is possible.
