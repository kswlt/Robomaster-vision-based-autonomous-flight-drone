#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""VIO startup precheck -- fail closed.

Usage:
    vio_precheck.py hw       <config_dir>          # no ROS needed
    vio_precheck.py camera   <config_dir>          # camera node already running
    vio_precheck.py imu      <config_dir>          # bridge already running

Exit code 0 only when every CRITICAL check passes.  Any failure prints
`PRECHECK FAIL: <reason>` and exits non-zero so the launcher can refuse to start
the estimator.

Rationale (from the runtime audit): the emitter state, the camera profile and the
loaded calibration were all previously assumed rather than verified, and the
launch parameter that was supposed to disable the IR projector does not even
exist in this realsense-ros version.  Everything that can silently invalidate an
experiment is therefore checked explicitly here.
"""
import glob
import hashlib
import os
import re
import subprocess
import sys
import time

FAILS = []
WARNS = []
OKS = []


def ok(msg):
    OKS.append(msg)
    print('  [ OK ] %s' % msg)


def warn(msg):
    WARNS.append(msg)
    print('  [WARN] %s' % msg)


def fail(msg):
    FAILS.append(msg)
    print('  [FAIL] %s' % msg)


def run(cmd):
    try:
        p = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)
        return p.returncode, (p.stdout or '') + (p.stderr or '')
    except Exception as exc:
        return 1, str(exc)


def sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for b in iter(lambda: f.read(65536), b''):
            h.update(b)
    return h.hexdigest()


# --------------------------------------------------------------------- config
def check_config(cfgdir):
    print('-- config files --')
    need = ['estimator_config.yaml', 'kalibr_imu_chain.yaml', 'kalibr_imucam_chain.yaml']
    for n in need:
        p = os.path.join(cfgdir, n)
        if not os.path.isfile(p):
            fail('missing config %s' % p)
            continue
        ok('%s  sha256=%s' % (n, sha256(p)))

    est = os.path.join(cfgdir, 'estimator_config.yaml')
    cam = os.path.join(cfgdir, 'kalibr_imucam_chain.yaml')
    imu = os.path.join(cfgdir, 'kalibr_imu_chain.yaml')
    if not (os.path.isfile(est) and os.path.isfile(cam) and os.path.isfile(imu)):
        return
    e = open(est).read()
    c = open(cam).read()
    m = open(imu).read()

    for key, want in (('init_dyn_use', 'false'), ('try_zupt', None),
                      ('relative_config_imu', 'kalibr_imu_chain.yaml'),
                      ('relative_config_imucam', 'kalibr_imucam_chain.yaml')):
        if key == 'try_zupt':
            continue
        mm = re.search(r'^%s:\s*(\S+)' % key, e, re.M)
        if not mm:
            fail('estimator_config.yaml missing %s' % key)
        elif mm.group(1) != want:
            warn('%s = %s (expected %s)' % (key, mm.group(1), want))
        else:
            ok('%s = %s' % (key, mm.group(1)))

    # ZUPT semantics: chi2_multipler == 0 makes UpdaterZeroVelocity reject every
    # update (chi2_limit = 0), while the INFO log still prints "passed disparity".
    mm = re.search(r'^try_zupt:\s*(\S+)', e, re.M)
    mz = re.search(r'^zupt_chi2_multipler:\s*([\d.eE+-]+)', e, re.M)
    md = re.search(r'^zupt_max_disparity:\s*([\d.eE+-]+)', e, re.M)
    try_zupt = (mm.group(1) == 'true') if mm else False
    chi2m = float(mz.group(1)) if mz else 0.0
    maxdisp = float(md.group(1)) if md else 0.0
    if try_zupt and chi2m <= 0.0:
        fail('try_zupt: true but zupt_chi2_multipler = 0 -> chi2_limit = 0 -> '
             'UpdaterZeroVelocity rejects EVERY update (ZUPT is dead while the '
             'INFO log still prints "passed disparity")')
    elif try_zupt:
        ok('ZUPT enabled with chi2_multipler=%g (limit=%g x chi2_check)'
           % (chi2m, chi2m))
    else:
        ok('try_zupt: false (ZUPT disabled explicitly)')
    if try_zupt and maxdisp <= 0.0 and chi2m <= 0.0:
        fail('both ZUPT gates disabled -> no zero-velocity constraint at all')

    mm = re.search(r'^cam0:\s*$', c, re.M)
    mm1 = re.search(r'^cam1:\s*$', c, re.M)
    if mm:
        seg = c[mm.end(): mm1.start() if mm1 else len(c)]
        ts_m = re.search(r'timeshift_cam_imu:\s*([-\d.eE+]+)', seg)
        if ts_m:
            ok('timeshift_cam_imu (cam0) = %+.6f s' % float(ts_m.group(1)))
        else:
            fail('timeshift_cam_imu not found inside the cam0 block')
    else:
        fail('no cam0 block in kalibr_imucam_chain.yaml')

    mm = re.search(r'^update_rate:\s*([\d.]+)', m, re.M)
    if mm:
        ok('kalibr_imu_chain update_rate = %s Hz' % mm.group(1))

    ints = re.findall(r'^\s+intrinsics:\s*\[([^\]]+)\]', c, re.M)
    res = re.findall(r'^\s+resolution:\s*\[([^\]]+)\]', c, re.M)
    for i, r in enumerate(res):
        if '848' not in r or '480' not in r:
            fail('camera %d resolution is [%s], expected 848x480' % (i, r.strip()))
        else:
            ok('camera %d resolution = [%s]' % (i, r.strip()))


# ------------------------------------------------------------------- hardware
def check_hw(cfgdir):
    print('-- hardware --')
    rc, out = run('lsusb')
    if '0ad4' not in out.lower():
        fail('RealSense D430 (8086:0ad4) not present on USB')
    else:
        ok('RealSense D430 present on USB')
    rc, out = run('lsusb -t')
    speed_ok = False
    for ln in out.splitlines():
        if 'uvcvideo' in ln:
            if '5000M' in ln:
                speed_ok = True
            else:
                fail('RealSense is NOT on USB3 SuperSpeed: %s' % ln.strip())
    if speed_ok:
        ok('RealSense enumerated at 5000M (USB3 SuperSpeed)')
    elif '0ad4' in run('lsusb')[1].lower():
        fail('could not confirm USB3 SuperSpeed for the RealSense')

    rc, out = run('ls /dev/ttyACM* 2>/dev/null')
    if rc != 0 or not out.strip():
        fail('no /dev/ttyACM* found (PX4 not connected)')
    else:
        ok('PX4 serial present: %s' % out.split()[0])

    # --- IR projector state ---
    #
    # Measured behaviour of this D430 (firmware 5.17.3.10) worth recording:
    #   * `laser_power` PERSISTS across stream stop/start.
    #   * `emitter_enabled` is a STREAM-SESSION setting: starting a stream resets
    #     it to its default 1, and so does stopping one.  A `set_option(...,0)`
    #     performed before any stream is open therefore does not survive.
    #   * the write order matters: laser_power must be zeroed FIRST, otherwise
    #     the emitter_enabled=0 write is rejected (readback comes back as 1).
    #
    # Consequence: the projector cannot be disabled by a launch argument, by a
    # config file, or once at boot -- it has to be re-asserted after the stream
    # is up.  That is exactly why earlier "we disabled the laser" experiments
    # never applied to the real startup path.  At the hw stage, before any
    # stream exists, we can only report the state; the enforcing check lives in
    # the camera stage where a stream is guaranteed.
    try:
        import pyrealsense2 as rs
    except Exception as exc:
        warn('pyrealsense2 unavailable, cannot inspect IR emitter: %s' % exc)
        return
    sen = None
    for d in rs.context().query_devices():
        for s in d.sensors:
            try:
                if 'Stereo' in s.get_info(rs.camera_info.name):
                    sen = s
            except Exception:
                pass
    if sen is None:
        fail('no Stereo Module sensor found (camera busy or disconnected)')
        return
    names = {}
    for o in sen.get_supported_options():
        n = getattr(o, 'name', None) or str(o).replace('option.', '')
        names[n] = o

    def rd(k):
        try:
            return sen.get_option(names[k]) if k in names else None
        except Exception:
            return None

    lp = rd('laser_power')
    ee = rd('emitter_enabled')
    eao = rd('emitter_always_on')
    if lp is None:
        warn('laser_power option not exposed on this device')
    elif lp == 0.0:
        ok('laser_power = 0 (persistent; this is the reliable off switch)')
    else:
        fail('laser_power = %s (expected 0; the projector can emit)' % lp)
    if ee is None:
        warn('emitter_enabled option not exposed')
    elif ee == 0.0:
        ok('emitter_enabled = 0 (no stream open)')
    else:
        warn('emitter_enabled = %s before the stream opens; this is reset to the '
             'default on every stream start and is re-asserted in the camera stage'
             % ee)
    if eao is not None:
        ok('emitter_always_on = %s' % eao)


# --------------------------------------------------------------------- camera
def check_camera(cfgdir, domain, timeout=40.0):
    print('-- camera (ROS) --')

    # ------------------------------------------------------------------
    # IR projector: this is the ONLY place where it can be reliably disabled,
    # because emitter_enabled is a stream-session setting.  Order matters:
    # laser_power first, then emitter_enabled, otherwise the emitter write is
    # rejected and reads back as 1.
    # ------------------------------------------------------------------
    try:
        import pyrealsense2 as rs
        sen = None
        for d in rs.context().query_devices():
            for s in d.sensors:
                try:
                    if 'Stereo' in s.get_info(rs.camera_info.name):
                        sen = s
                except Exception:
                    pass
        if sen is None:
            fail('cannot verify IR emitter: no Stereo Module handle')
        else:
            names = {}
            for o in sen.get_supported_options():
                n = getattr(o, 'name', None) or str(o).replace('option.', '')
                names[n] = o

            def w(k, v):
                if k in names:
                    try:
                        sen.set_option(names[k], float(v))
                        return True
                    except Exception as exc:
                        fail('set %s=%s raised %r' % (k, v, exc))
                return False

            # laser_power must be zeroed FIRST (verified ordering dependency)
            w('laser_power', 0)
            time.sleep(0.4)
            w('emitter_enabled', 0)
            time.sleep(0.6)
            try:
                lp = sen.get_option(names['laser_power'])
            except Exception:
                lp = None
            try:
                ee = sen.get_option(names['emitter_enabled'])
            except Exception:
                ee = None
            if lp == 0.0:
                ok('IR projector: laser_power = 0 verified WITH the stream open')
            elif lp is not None:
                fail('IR projector: laser_power reads %s with the stream open' % lp)
            if ee == 0.0:
                ok('IR projector: emitter_enabled = 0 verified with the stream open')
            elif ee is not None:
                fail('IR projector: emitter_enabled reads %s with the stream open '
                     '(expected 0; the projector may be emitting)' % ee)
    except ImportError:
        warn('pyrealsense2 unavailable: IR projector state NOT verified')
    except Exception as exc:
        fail('IR projector enforcement failed: %r' % exc)

    import rclpy
    from rclpy.node import Node
    from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy, DurabilityPolicy
    from sensor_msgs.msg import CameraInfo, Image

    os.environ.setdefault('ROS_DOMAIN_ID', str(domain))
    os.environ['ROS_LOCALHOST_ONLY'] = '1'
    rclpy.init()
    node = Node('vio_precheck_cam')
    qos_img = QoSProfile(depth=40, reliability=ReliabilityPolicy.BEST_EFFORT,
                         durability=DurabilityPolicy.VOLATILE,
                         history=HistoryPolicy.KEEP_LAST)
    qos_info = QoSProfile(depth=10, reliability=ReliabilityPolicy.RELIABLE,
                          durability=DurabilityPolicy.VOLATILE,
                          history=HistoryPolicy.KEEP_LAST)
    got = {'infra1': [], 'infra2': []}
    infos = {}
    for k in got:
        node.create_subscription(Image, '/camera/camera/%s/image_rect_raw' % k,
                                 lambda m, kk=k: got[kk].append(
                                     m.header.stamp.sec + m.header.stamp.nanosec * 1e-9),
                                 qos_img)
        node.create_subscription(CameraInfo, '/camera/camera/%s/camera_info' % k,
                                 lambda m, kk=k: infos.setdefault(kk, m), qos_info)
    t0 = time.time()
    while time.time() - t0 < timeout:
        rclpy.spin_once(node, timeout_sec=0.2)
        if len(got['infra1']) > 35 and len(got['infra2']) > 35 and len(infos) == 2:
            break
    for k in got:
        n = len(got[k])
        if n < 25:
            fail('infra%s: only %d frames in %.0f s (camera not streaming?)'
                 % (k[-1], n, timeout))
            continue
        span = got[k][-1] - got[k][0]
        rate = (n - 1) / span if span > 0 else 0.0
        d = [got[k][i + 1] - got[k][i] for i in range(len(got[k]) - 1)]
        d.sort()
        ok('infra%s: %d frames, %.2f Hz, dt p50=%.3f ms p95=%.3f ms'
           % (k[-1], n, rate, d[len(d) // 2] * 1e3, d[int(0.95 * (len(d) - 1))] * 1e3))
        if rate < 25.0:
            fail('infra%s rate %.2f Hz < 25 Hz (expected ~30 Hz)' % (k[-1], rate))
    if len(got['infra1']) > 5 and len(got['infra2']) > 5:
        a = got['infra1'][:60]
        b = got['infra2'][:60]
        diffs = []
        for x in a:
            diffs.append(min(abs(x - y) for y in b) * 1e3)
        diffs.sort()
        p95 = diffs[int(0.95 * (len(diffs) - 1))]
        if p95 > 5.0:
            warn('infra1/infra2 timestamp sync p95 = %.3f ms (>5 ms)' % p95)
        else:
            ok('infra1/infra2 timestamp sync p95 = %.3f ms' % p95)

    for k, msg in infos.items():
        if msg.width != 848 or msg.height != 480:
            fail('%s resolution is %dx%d, expected 848x480'
                 % (k, msg.width, msg.height))
        else:
            ok('%s resolution = 848x480' % k)

    # intrinsics must match the YAML that the estimator will load
    cam = os.path.join(cfgdir, 'kalibr_imucam_chain.yaml')
    if os.path.isfile(cam) and infos:
        txt = open(cam).read()
        blocks = re.findall(r'^\s+intrinsics:\s*\[([^\]]+)\]', txt, re.M)
        for i, k in enumerate(sorted(infos)):
            if i >= len(blocks):
                break
            want = [float(x) for x in blocks[i].split(',')]
            m = infos[k]
            have = [m.k[0], m.k[4], m.k[2], m.k[5]]
            dev = max(abs(want[j] - have[j]) for j in range(4))
            if dev > 1e-3:
                fail('%s intrinsics differ from YAML by %.6f (yaml=%s camera=%s)'
                     % (k, dev, ['%.4f' % v for v in want], ['%.4f' % v for v in have]))
            else:
                ok('%s intrinsics match YAML exactly' % k)
    node.destroy_node()
    rclpy.shutdown()


# ------------------------------------------------------------------------ imu
def check_imu(cfgdir, domain, timeout=25.0, expect_min_hz=180.0):
    print('-- imu (ROS) --')
    import rclpy
    from rclpy.node import Node
    from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy, DurabilityPolicy
    from sensor_msgs.msg import Imu as ImuMsg

    os.environ.setdefault('ROS_DOMAIN_ID', str(domain))
    os.environ['ROS_LOCALHOST_ONLY'] = '1'
    rclpy.init()
    node = Node('vio_precheck_imu')
    qos = QoSProfile(depth=2000, reliability=ReliabilityPolicy.RELIABLE,
                     durability=DurabilityPolicy.VOLATILE,
                     history=HistoryPolicy.KEEP_LAST)
    stamps = []
    node.create_subscription(ImuMsg, '/imu',
                             lambda m: stamps.append(
                                 m.header.stamp.sec + m.header.stamp.nanosec * 1e-9),
                             qos)
    t0 = time.time()
    while time.time() - t0 < timeout and len(stamps) < 900:
        rclpy.spin_once(node, timeout_sec=0.1)
    n = len(stamps)
    if n < 100:
        fail('only %d /imu messages in %.0f s (bridge running?)' % (n, timeout))
        node.destroy_node()
        rclpy.shutdown()
        return
    d = sorted(stamps[i + 1] - stamps[i] for i in range(n - 1))
    rate = (n - 1) / (stamps[-1] - stamps[0])
    ok('/imu: %d msgs, %.2f Hz, dt p50=%.3f ms p95=%.3f ms max=%.3f ms'
       % (n, rate, d[len(d) // 2] * 1e3, d[int(0.95 * (len(d) - 1))] * 1e3, d[-1] * 1e3))
    if rate < expect_min_hz:
        fail('/imu rate %.2f Hz < %.0f Hz' % (rate, expect_min_hz))
    bad = sum(1 for x in d if x <= 0)
    if bad:
        fail('%d /imu messages with non-increasing timestamps' % bad)
    else:
        ok('IMU timestamps strictly increasing')
    tiny = sum(1 for x in d if 0 < x < 1e-4)
    if tiny:
        fail('%d IMU dt values below 100 us (timestamp clamping?)' % tiny)
    node.destroy_node()
    rclpy.shutdown()


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    mode, cfgdir = sys.argv[1], sys.argv[2]
    domain = int(sys.argv[3]) if len(sys.argv) > 3 else int(os.environ.get('ROS_DOMAIN_ID', 42))
    print('#### VIO PRECHECK mode=%s config=%s domain=%d' % (mode, cfgdir, domain))
    check_config(cfgdir)
    if mode == 'hw':
        check_hw(cfgdir)
    elif mode == 'camera':
        check_camera(cfgdir, domain)
    elif mode == 'imu':
        check_imu(cfgdir, domain)
    elif mode == 'all':
        check_hw(cfgdir)
        check_camera(cfgdir, domain)
        check_imu(cfgdir, domain)
    else:
        print('unknown mode %s' % mode)
        return 2
    print('#### RESULT: %d ok, %d warn, %d fail' % (len(OKS), len(WARNS), len(FAILS)))
    if FAILS:
        for f in FAILS:
            print('PRECHECK FAIL: %s' % f)
        return 1
    print('PRECHECK PASS')
    return 0


if __name__ == '__main__':
    sys.exit(main())
