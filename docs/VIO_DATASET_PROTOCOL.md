# Immutable validation recordings

Run on board: `bash scripts/record_vio_validation.sh MOTION SECONDS 'notes'`.
Destination `/home/orangepi/vio_data/<UTC>_<motion>/bag`; unique directory,
config snapshots, recorder log and SHA256 manifest remain on board. Do not
commit raw bags. Copy only manifests, metadata and small derived summaries.

USB preflight checks expected D430 serial and >=5000M. Before each dataset,
verify both image rates, camera calibration/profile and IMU availability.
An existing metadata.yaml alone does NOT validate a recording: require all
core topics, expected counts, full duration, no restarts, valid timestamps,
and no hardware/REC errors. Failed or interrupted bags are not A/B inputs.
Manifest status RECORDED_UNVALIDATED requires subsequent timing analysis and
operator motion confirmation. Record actual movement start/end intervals in
separate annotations; never infer ground truth from VIO outputs.

All motions: remain still >=5 s at beginning and end. Human operation required:

* STATIC: completely stationary 120 s.
* ROTATION_ONLY: fixed camera center; yaw ±90°, pitch ±45°, roll ±45°,
  return to initial attitude, then slow yaw 360°. Record individual intervals.
* TRANSLATION: straight 1 m out and back, preserve attitude.
* RECTANGLE: 2×2 m or 1×1 m closed loop; record measured dimensions.
* IMU_NOISE: stationary >=300 s.

Replay only derived experiment configurations in separate directories and ROS
domains; never overwrite baseline YAML. Keep the same immutable input hash
across candidates. Record binary/config hashes, replay rate, topic remaps,
initialization success, output trajectory, timing and actual ZUPT decisions.
Dynamic baseline is ZUPT OFF. All candidate comparisons are pending data.
