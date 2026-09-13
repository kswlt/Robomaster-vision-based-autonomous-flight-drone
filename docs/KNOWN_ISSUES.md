# Known Issues

## Active

### 1. Isaac Sim cannot be installed (disk space)
- **Severity**: Blocker for milestones 1 & 4
- **Details**: Isaac Sim 6.1.0 standalone = 9.66GB download, ~30GB+ extracted. C: has 30.9GB free, E: has 15.4GB free.
- **Workaround**: sim/isaac code is fully written and syntax-valid; install Isaac when disk space is freed.
- **Fix**: Free ≥40GB on C: or attach a drive with ≥40GB free.

### 2. Armor module dimensions unconfirmed
- **Severity**: Medium
- **Details**: Provided images show the support bracket (135×38mm) but not the armor module (hit plate) dimensions. Using placeholder 0.135×0.055m.
- **Fix**: Consult official RMUC 2026 Robot Specification Manual, update configs/armor.yaml.

### 3. Armor target normal/orientation defaulted
- **Severity**: Medium
- **Details**: Default normal = [-1,0,0] (faces -x). Exact orientation needs STL face analysis or user confirmation.
- **Fix**: Run face-normal analysis on candidate armor plate components, or measure in Isaac GUI.

### 4. Visual Studio Build Tools not detected
- **Severity**: Low (DiffPhys runs in WSL2 with gcc)
- **Details**: vswhere reports no VS installations. Not needed for WSL2 CUDA extension builds. Would matter if building anything natively on Windows.
- **Fix**: Install Visual Studio Build Tools if native Windows compilation becomes needed.

### 5. Python 3.14 default (very new)
- **Severity**: Low
- **Details**: System default Python is 3.14.7. Some packages may lack wheels. Asset analysis works (numpy 2.5.2, trimesh 5.1.0). DiffPhys uses WSL2 Python 3.10.12.
- **Fix**: Use `py -3.11` if Windows-side packages fail on 3.14.

## Resolved

(none yet)
