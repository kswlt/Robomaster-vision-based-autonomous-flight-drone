#!/usr/bin/env python3
"""Validate a kalibr-style camera-IMU chain with the SAME reader OpenVINS uses.

OpenVINS parses these with cv::FileStorage, whose dialect is '%YAML:1.0' with an
optional trailing extension list.  Standard PyYAML rejects that, so validating
with PyYAML produces false failures.  This uses OpenCV, and additionally checks
that every field OpenVINS reads is present and well-formed.
"""
import sys
import numpy as np
import cv2


def main():
    path = sys.argv[1]
    fs = cv2.FileStorage(path, cv2.FILE_STORAGE_READ)
    if not fs.isOpened():
        print('FAIL: OpenCV could not open %s' % path)
        return 1
    print('OpenCV FileStorage opened OK: %s' % path)

    ok = True
    for cam in ('cam0', 'cam1'):
        if not fs.getNode(cam).empty():
            pass
        node = fs.getNode(cam)
        if node.empty():
            print('  FAIL: missing %s' % cam)
            ok = False
            continue
        ts = node.getNode('timeshift_cam_imu')
        T = node.getNode('T_imu_cam').mat()
        intr = node.getNode('intrinsics').mat()
        res = node.getNode('resolution').mat()
        dist = node.getNode('distortion_coeffs').mat()
        topic = node.getNode('rostopic').string()
        model = node.getNode('camera_model').string()
        dmodel = node.getNode('distortion_model').string()
        print('  %s:' % cam)
        if ts.empty():
            print('     timeshift_cam_imu : MISSING')
            ok = False
        else:
            print('     timeshift_cam_imu : %s' % ts.real())
        if T is None or T.shape != (4, 4):
            print('     T_imu_cam         : FAIL shape=%s' % (None if T is None else T.shape))
            ok = False
        else:
            R = T[0:3, 0:3]
            det = np.linalg.det(R)
            orth = np.abs(R @ R.T - np.eye(3)).max()
            print('     T_imu_cam         : 4x4 ok, det(R)=%.6f, |R R^T - I|max=%.2e' % (det, orth))
            print('     translation       : [%.6f %.6f %.6f]' % tuple(T[0:3, 3]))
            if abs(det - 1.0) > 1e-4 or orth > 1e-4:
                print('       FAIL: rotation is not a proper orthonormal matrix')
                ok = False
        if intr is None or intr.size != 4:
            print('     intrinsics        : FAIL %s' % (None if intr is None else intr.shape))
            ok = False
        else:
            print('     intrinsics        : [%.4f %.4f %.4f %.4f]' % tuple(intr.ravel()))
        if res is None or res.size != 2:
            print('     resolution        : FAIL')
            ok = False
        else:
            print('     resolution        : [%d %d]' % (int(res.ravel()[0]), int(res.ravel()[1])))
        print('     distortion        : model=%s coeffs=%s' % (
            dmodel, None if dist is None else list(np.round(dist.ravel(), 6))))
        print('     camera_model      : %s' % model)
        print('     rostopic          : %s' % topic)
        if not topic:
            print('       FAIL: empty rostopic')
            ok = False

    # stereo baseline implied by the two extrinsics
    t0 = fs.getNode('cam0').getNode('T_imu_cam').mat()[0:3, 3]
    t1 = fs.getNode('cam1').getNode('T_imu_cam').mat()[0:3, 3]
    print('  implied stereo baseline (|t1 - t0|) = %.4f mm' % (np.linalg.norm(t1 - t0) * 1e3))
    print('  hardware stereo baseline           = 50.1375 mm')
    fs.release()
    print('RESULT: %s' % ('OK' if ok else 'FAIL'))
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
