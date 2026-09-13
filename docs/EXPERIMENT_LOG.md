# Experiment Log

Format: date | commit | config | checkpoint | episodes | metrics | conclusion

---

## 2026-09-14 — Environment & Asset Audit

- **Commit**: (initial skeleton, pending push)
- **Config**: N/A (audit phase)
- **Checkpoint**: N/A
- **Episodes**: 0
- **Metrics**:
  - STL: 124,995 triangles, extents 29.15×16.05×18.04 raw
  - Unit calibrated: meters (official 28×15m battlefield)
  - Stray artifact: 8 vertices at z≈18
  - Armor bracket: 135×38mm, diag 125mm
  - WSL2 GPU: RTX 4060 Laptop, 8GB, driver 591.86
- **Conclusion**: Environment ready for DiffPhys training in WSL2. Isaac Sim blocked by disk space (30.9GB free, need ~40GB). Asset geometry fully analyzed.

---

## (Template for future entries)

## YYYY-MM-DD — Experiment Name

- **Commit**: `<sha>`
- **Config**: `<config file / key params>`
- **Checkpoint**: `<path>`
- **Episodes**: `<N>`
- **Metrics**:
  - target_hit_rate: `<value>`
  - wrong_collision_rate: `<value>`
  - ...
- **Conclusion**: `<what worked, what didn't, next step>`
