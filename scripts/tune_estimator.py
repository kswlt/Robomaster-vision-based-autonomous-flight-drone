#!/usr/bin/env python3
"""Apply validated tracking/ZUPT/init tuning to estimator_config.yaml in place."""
import re

P = "/home/orangepi/vio_ws/src/open_vins/config/d430/estimator_config.yaml"
s = open(P).read()

# exact key: value replacements (whole token, comment preserved)
repl = [
    (r'^(\s*max_msckf_in_update:\s*)25(\s)', r'\g<1>75\g<2>'),
    (r'^(\s*zupt_chi2_multipler:\s*)0(\s)', r'\g<1>0.5\g<2>'),
    (r'^(\s*zupt_max_velocity:\s*)0\.1(\s)', r'\g<1>0.02\g<2>'),
    (r'^(\s*zupt_max_disparity:\s*)0\.5(\s)', r'\g<1>0.15\g<2>'),
    (r'^(\s*init_max_disparity:\s*)10\.0(\s)', r'\g<1>0.3\g<2>'),
    (r'^(\s*init_max_features:\s*)50(\s)', r'\g<1>100\g<2>'),
    (r'^(\s*num_pts:\s*)100(\s)', r'\g<1>200\g<2>'),
    (r'^(\s*fast_threshold:\s*)20(\s)', r'\g<1>12\g<2>'),
    (r'^(\s*track_frequency:\s*)21\.0(\s)', r'\g<1>30.0\g<2>'),
]
for pat, rep in repl:
    s, n = re.subn(pat, rep, s, count=1, flags=re.MULTILINE)
    print(("OK  " if n else "MISS"), pat)

open(P,"w").write(s)
print("\n--- key params now ---")
for key in ["max_msckf_in_update","zupt_chi2_multipler","zupt_max_velocity",
            "zupt_max_disparity","init_max_disparity","init_max_features",
            "num_pts","fast_threshold","track_frequency",
            "calib_cam_extrinsics","calib_cam_intrinsics","calib_cam_timeoffset"]:
    for ln in s.splitlines():
        if ln.strip().startswith(key+":"):
            print(ln)
            break
