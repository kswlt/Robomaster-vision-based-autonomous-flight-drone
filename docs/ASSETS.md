# Assets

## Input Assets (preserved, read-only originals)

All originals backed up to `C:\RM_E2E_INPUT_BACKUP\` with SHA256 recorded.

### Arena STL

| Field | Value |
|-------|-------|
| File | `assets/source/arena/rmuc_2026_arena.stl` |
| Original name | `rmuc_2026 (1).stl` |
| SHA256 | `D7DBB7DD0862D81BE6FF2DFA004A20ED8839E39636E475E97EB06EF61E25CEF6` |
| Size | 6,249,834 bytes |
| Triangles | 124,995 |
| Vertices | 116,893 |
| Bounds (raw) | x[-14.58, 14.57], y[-8.04, 8.01], z[0.23, 18.27] |
| Extents (raw) | 29.15 × 16.05 × 18.04 |
| Watertight | No |
| Volume valid | No |
| Surface area | 5031.1 |
| Zero-area faces | 0 |

### Unit Calibration

**Unit = meters.** Calibrated against official RMUC 2026 battlefield specification:
- Official battlefield: **28m long × 15m wide** (from arena_spec_overview.png, section 4.1)
- STL raw extents: 29.15 × 16.05 (extra ~1.1m = perimeter wall thickness)
- Perimeter wall height: 2.4m (official); STL main geometry z ∈ [0.23, 3.6]
- Drawings unit: mm (per spec text)

**Stray artifact**: 8 vertices at z ∈ [17.99, 18.27] — export error, must be clipped at z_max=4.0.

### Arena Reference Images

| File | SHA256 | Content |
|------|--------|---------|
| `assets/source/arena/arena_render_iso.png` | `DC33DB99DA2F5BC28E84A341C734AD02ABDF48661A896B312B629E45E287C70D` | Isometric render of battlefield |
| `assets/source/arena/arena_spec_overview.png` | `12B60BC958F802C143E2C85B96E41E1EADC1AC29E3BFC23F74EE4AB79B2E14F7` | Section 4.1: 28m×15m, 2.4m walls, mm unit |

### Armor Reference Images

| File | SHA256 | Content |
|------|--------|---------|
| `assets/source/armor/armor_bracket_spec_1.png` | `905323B0A7127B2107C85E7D0BFA486709E4F17A6CAB255478535C810A4CDE31` | Armor support bracket: 135×38, diag 125, 5 installation faces |
| `assets/source/armor/armor_rigid_mount_spec_2.png` | `2E0100F781AD01C4DE38AFF439004AB7BE59288618B4ADDD9B1279779EA56819` | Rigid connection: 60N test, α≤2.5°, no relative movement |

### Armor Bracket Dimensions (from drawing)

| Dimension | Value (mm) | Value (m) |
|-----------|-----------|-----------|
| Width | 135 | 0.135 |
| Height | 38 | 0.038 |
| Diagonal | 125 | 0.125 |
| Thickness | TODO (not in images) | null |

### Armor Module (hit plate)

Dimensions **not fully confirmed** from provided images. Marked TODO in `configs/armor.yaml`.
Default placeholder: 0.135m × 0.055m × 0.01m — verify against official RMUC 2026 armor module spec.

## Analysis Artifacts

| File | Description |
|------|-------------|
| `assets/manifests/arena_analysis.json` | Full STL geometry report |
| `assets/manifests/arena_components.json` | 13,101 connected components with extents |
| `assets/manifests/armor_plate_candidates.json` | 998 plate-like component candidates |
| `assets/manifests/arena_preview_topdown.png` | Top-down vertex projection |
| `assets/manifests/arena_preview_side.png` | Side (x-z) projection |
| `assets/manifests/arena_preview_side_yz.png` | Side (y-z) projection |

## Analysis Scripts

| Script | Purpose |
|--------|---------|
| `scripts/analyze_arena_stl.py` | Basic STL geometry + scale hints |
| `scripts/analyze_arena_components.py` | Connected component analysis |
| `scripts/scan_armor_plates.py` | Plate-like component scan for armor targets |
| `scripts/preview_arena.py` | Render 2D projections for visual inspection |
