#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PX4 -> ROS IMU clock mapping with explicit, auditable diagnostics.

Why this module exists
----------------------
The IMU topic that OpenVINS consumes is stamped by this bridge, so the mapping
below decides the entire inertial time axis.  The physical decomposition is:

    arrival_offset = t_ros_receive - t_px4_sensor
                   = true_clock_offset
                   + USB / MAVLink transport delay
                   + Linux scheduling latency
                   + Python / pymavlink parsing latency

Failure modes found in the field
--------------------------------
1. 'lower' (legacy): offset only ever decreased.  With a slowly falling
   arrival_offset this accumulated ~1 ms/s of time-axis drift.  The resulting
   dt sequence looks perfectly clean, which is exactly why it went unnoticed:
   stationary periods look stable and the error only shows up once the platform
   moves.

2. 'ema005' (current): a per-packet EMA with alpha=0.05 at ~200 Hz has a ~0.1 s
   time constant, i.e. a ~1.6 Hz cutoff.  Transport/scheduler jitter below
   1.6 Hz is written straight into the IMU timestamps, corrupting inertial
   pre-integration.

3. Both of the above leave the IMU axis advancing at the *PX4* clock rate while
   camera stamps advance at the *host* rate.  A -1000 ppm difference is 3.6 s
   per hour, so any fixed `timeshift_cam_imu` has a shelf life of seconds.

Strategy 'slow' (default) addresses all three:

    stamp = offset_ref + (sensor_time - ref_sensor) * scale_a

  * offset_ref : low quantile (P5) of arrival_offset over a sliding window
                 -> robust to packet jitter and to isolated stalls
                 -> followed by a long-time-constant EMA (tau_s)
  * scale_a    : 1 + slope of arrival_offset vs sensor_time, from a long-window
                 robust regression -> the frequency ratio host/px4

Every timestamp repair is counted and logged; nothing is silently rewritten.
"""
from __future__ import annotations

import bisect
import collections
import math
import time

# arrival_offset quantile used as the offset estimator.  arrival_offset has a
# hard lower bound (zero transport delay), so a low quantile approximates the
# true clock offset while staying robust to individual slow packets.
OFFSET_QUANTILE = 0.05

# consecutive gated samples after which we conclude the gate (not the data) is
# wrong and force the estimate to follow again.
MAX_CONSECUTIVE_GATED = 20

# consecutive +1 us repairs after which the clock mapping is considered broken.
MAX_CONSECUTIVE_REPAIRS = 5

# A 200 Hz sensor has a 4.93 ms nominal spacing; anything below this in the
# mapped output means the mapping failed, not that two samples were genuinely
# near-simultaneous.
MIN_PLAUSIBLE_DT = 1e-4  # 100 us

# Physically plausible bound on the PX4-vs-host frequency difference (ppm).
MAX_ABS_DRIFT_PPM = 5000.0


class ImuClockMapper:
    """Stateful PX4-boot-clock -> ROS-system-clock mapper."""

    MODES = ('lower', 'ema005', 'slow')

    def __init__(self,
                 mode='slow',
                 nominal_rate=200.0,
                 bootstrap_s=3.0,
                 tau_s=30.0,
                 gate_s=0.050,
                 jump_s=0.5,
                 win_s=20.0,
                 slope_win_s=90.0,
                 slope_interval_s=5.0,
                 scale_smooth=0.3,
                 decim=5,
                 logger=None):
        if mode not in self.MODES:
            raise ValueError('unknown mode %r (expected one of %s)' % (mode, self.MODES))
        self.mode = mode
        self.nominal_rate = float(nominal_rate)
        self.bootstrap_n = max(20, int(bootstrap_s * self.nominal_rate))
        self.tau_s = float(tau_s)
        self.alpha = 1.0 / max(1.0, self.tau_s * self.nominal_rate)
        self.gate_s = float(gate_s)
        self.jump_s = float(jump_s)
        self.win_s = float(win_s)
        self.slope_win_s = float(slope_win_s)
        self.slope_interval_s = float(slope_interval_s)
        self.scale_smooth = float(scale_smooth)
        self.decim = max(1, int(decim))
        self.logger = logger
        self.reset()

    # ------------------------------------------------------------------ state
    def reset(self, reason='startup'):
        # --- generic ---
        self.last_sensor_time = None
        self.last_stamp = None
        self.ref_sensor = None
        self.n = 0
        # --- offset estimation ---
        self.offset = None            # current best offset estimate (seconds)
        self.offset_ref = None        # offset at ref_sensor
        self.scale_a = 1.0            # host_rate / px4_rate
        self.scale_ppm = 0.0
        self.boot = []                # bootstrap arrival offsets (raw list)
        self.boot_sorted = []
        self.bootstrapped = False
        # --- sliding window low quantile ---
        self.win = collections.deque()        # (sensor_time, arrival_offset)
        self.win_sorted = []
        # --- slope window ---
        self.slope_pts = collections.deque()  # (sensor_time, arrival_offset)
        self.last_slope_t = None
        self.slope_updates = 0
        # --- counters ---
        self.n_clock_reset = 0
        self.n_gated = 0
        self.n_gate_forced = 0
        self.n_repair = 0
        self.n_repair_consec = 0
        self.n_repair_consec_max = 0
        self.n_repair_bad_dt = 0
        self.n_fatal_reset = 0
        self.consec_gated = 0
        self.last_repair_reason = ''
        # --- diagnostics ---
        self.dt_hist = []
        self.ao_hist = []
        self.offset_hist = []
        self.t_start = time.time()
        self.reset_reason = reason

    # ------------------------------------------------------------- internals
    def _log(self, level, msg):
        if self.logger is None:
            return
        fn = getattr(self.logger, level, None)
        if fn is None:
            return
        try:
            fn(msg)
        except Exception:
            pass

    @staticmethod
    def _quantile_sorted(v, q):
        if not v:
            return None
        i = int(q * (len(v) - 1))
        return v[min(max(i, 0), len(v) - 1)]

    @staticmethod
    def _lsq(t, y):
        n = len(t)
        if n < 2:
            return None
        mt = sum(t) / n
        my = sum(y) / n
        num = 0.0
        den = 0.0
        for i in range(n):
            dt = t[i] - mt
            num += dt * (y[i] - my)
            den += dt * dt
        if den <= 0:
            return None
        a = num / den
        return a, my - a * mt

    def _robust_slope(self):
        """Two-pass least squares over the slope window (drops the worst 20%)."""
        pts = list(self.slope_pts)
        if len(pts) < 40:
            return None
        t = [p[0] for p in pts]
        y = [p[1] for p in pts]
        r = self._lsq(t, y)
        if r is None:
            return None
        a, b = r
        res = sorted(abs(y[i] - (a * t[i] + b)) for i in range(len(t)))
        thr = res[int(0.80 * (len(res) - 1))] * 1.5 + 1e-9
        tt = [t[i] for i in range(len(t)) if abs(y[i] - (a * t[i] + b)) <= thr]
        yy = [y[i] for i in range(len(t)) if abs(y[i] - (a * t[i] + b)) <= thr]
        if len(tt) < 20:
            return None
        return self._lsq(tt, yy)

    def _update_slow(self, sensor_time, arrival_offset):
        """Sliding-window P5 offset + long-window frequency ratio."""
        # ---- decimated sliding window for the low quantile ----
        if self.n % self.decim == 0:
            self.win.append((sensor_time, arrival_offset))
            bisect.insort(self.win_sorted, arrival_offset)
            # evict entries older than win_s
            while self.win and (sensor_time - self.win[0][0]) > self.win_s:
                _, old = self.win.popleft()
                i = bisect.bisect_left(self.win_sorted, old)
                if i < len(self.win_sorted) and self.win_sorted[i] == old:
                    self.win_sorted.pop(i)
            self.slope_pts.append((sensor_time, arrival_offset))
            while self.slope_pts and (sensor_time - self.slope_pts[0][0]) > self.slope_win_s:
                self.slope_pts.popleft()

        offset_q = self._quantile_sorted(self.win_sorted, OFFSET_QUANTILE)
        if offset_q is None:
            offset_q = arrival_offset

        if not self.bootstrapped:
            self.boot.append(arrival_offset)
            if len(self.boot) >= self.bootstrap_n and len(self.win_sorted) >= 20:
                self.bootstrapped = True
                self.offset = offset_q
                self.offset_ref = offset_q
                self.ref_sensor = sensor_time
                self._log('info',
                          'IMU clock bootstrap complete after %d samples: '
                          'offset=%.6f s (P%d of arrival_offset over the window)'
                          % (len(self.boot), offset_q, int(OFFSET_QUANTILE * 100)))
            else:
                self.offset = offset_q
            return

        # ---- frequency-ratio estimate (slow, robust) ----
        if (self.last_slope_t is None or
                abs(sensor_time - self.last_slope_t) >= self.slope_interval_s):
            r = self._robust_slope()
            if r is not None:
                a = r[0]
                lim = MAX_ABS_DRIFT_PPM * 1e-6
                a = min(max(a, -lim), lim)
                # smooth the target ratio: an unsmoothed ratio changes the axis
                # slope between consecutive samples and injects dt jitter.
                self.scale_a += self.scale_smooth * ((1.0 + a) - self.scale_a)
                self.scale_ppm = (self.scale_a - 1.0) * 1e6
                self.slope_updates += 1
                self.last_slope_t = sensor_time

        # ---- residual offset tracking (long time constant, gated) ----
        pred = self.offset_ref + (sensor_time - self.ref_sensor) * (self.scale_a - 1.0)
        lag = offset_q - pred
        if abs(lag) > self.gate_s:
            self.consec_gated += 1
            self.n_gated += 1
            if self.consec_gated >= MAX_CONSECUTIVE_GATED:
                self.offset_ref += self.alpha * lag
                self.consec_gated = 0
                self.n_gate_forced += 1
        else:
            self.offset_ref += self.alpha * lag
            self.consec_gated = 0
        self.offset = pred

    # ------------------------------------------------------------------- api
    def update(self, sensor_time, arrival_time):
        """Map one PX4 sample.  Returns (stamp_seconds, diag_dict)."""
        self.n += 1
        arrival_offset = arrival_time - sensor_time
        self.ao_hist.append(arrival_offset)
        diag = {
            'seq': self.n,
            'sensor_time': sensor_time,
            'arrival_time': arrival_time,
            'arrival_offset': arrival_offset,
            'mode': self.mode,
            'bootstrapped': self.bootstrapped,
            'gated': False,
            'clock_reset': False,
            'repaired': False,
            'repaired_orig_dt': None,
            'final_dt': None,
            'scale_ppm': self.scale_ppm,
        }

        # ---- PX4 time base discontinuity ----
        if (self.last_sensor_time is not None and
                sensor_time < self.last_sensor_time - self.jump_s):
            self.n_clock_reset += 1
            self._log('warn',
                      'PX4 IMU time base jumped backwards (%.3f s); re-anchoring '
                      'clock mapping (reset #%d)'
                      % (sensor_time - self.last_sensor_time, self.n_clock_reset))
            diag['clock_reset'] = True
            self.reset(reason='timebase_backward')
            self.offset = arrival_offset
            self.offset_ref = arrival_offset
            self.ref_sensor = sensor_time

        # ---- offset / timescale estimation ----
        if self.mode == 'lower':
            if self.offset is None or arrival_offset < self.offset:
                self.offset = arrival_offset
            self.scale_a = 1.0
        elif self.mode == 'ema005':
            if self.offset is None:
                self.offset = arrival_offset
            else:
                self.offset += 0.05 * (arrival_offset - self.offset)
            self.scale_a = 1.0
        else:
            self._update_slow(sensor_time, arrival_offset)

        if self.offset is None:
            self.offset = arrival_offset
        if self.offset_ref is None:
            self.offset_ref = self.offset
            self.ref_sensor = sensor_time
        diag['clock_offset'] = self.offset

        # ---- stamp ----
        if self.mode == 'slow' and self.bootstrapped:
            # stamp must land in the HOST domain: anchor at ref_sensor, then
            # advance at the estimated host/px4 frequency ratio.
            stamp = ((self.ref_sensor + self.offset_ref) +
                     (sensor_time - self.ref_sensor) * self.scale_a)
        else:
            stamp = sensor_time + self.offset

        if abs(stamp - arrival_time) > self.jump_s:
            self._log('warn',
                      'mapped IMU stamp deviates %.3f s from arrival time; '
                      're-anchoring clock mapping' % (stamp - arrival_time))
            self.offset = arrival_time - sensor_time
            self.offset_ref = self.offset
            self.ref_sensor = sensor_time
            self.scale_a = 1.0
            stamp = arrival_time
            self.last_stamp = None
            diag['clock_reset'] = True
            self.n_clock_reset += 1

        # ---- monotonicity guard: explicit, counted, never silent ----
        dt = None
        if self.last_stamp is not None:
            if stamp <= self.last_stamp:
                orig_dt = stamp - self.last_stamp
                self.n_repair += 1
                self.n_repair_consec += 1
                self.n_repair_consec_max = max(self.n_repair_consec_max,
                                               self.n_repair_consec)
                diag['repaired'] = True
                diag['repaired_orig_dt'] = orig_dt
                self.last_repair_reason = 'non-monotonic (dt=%.9f)' % orig_dt
                stamp = self.last_stamp + 1e-6
                dt = 1e-6
                if self.n_repair_consec >= MAX_CONSECUTIVE_REPAIRS:
                    self._log('error',
                              'IMU clock mapping broken: %d consecutive '
                              'non-monotonic timestamps (last original dt=%.9f s); '
                              'resetting clock mapping'
                              % (self.n_repair_consec, orig_dt))
                    self.n_fatal_reset += 1
                    self.reset(reason='consecutive_repairs')
                    self.offset = arrival_time - sensor_time
                    self.offset_ref = self.offset
                    self.ref_sensor = sensor_time
                    stamp = arrival_time
                    dt = None
            else:
                self.n_repair_consec = 0
                dt = stamp - self.last_stamp
        else:
            self.n_repair_consec = 0

        if dt is not None and dt < MIN_PLAUSIBLE_DT:
            self.n_repair_bad_dt += 1

        diag['final_dt'] = dt
        self.last_stamp = stamp
        if not diag['clock_reset']:
            self.last_sensor_time = sensor_time
        self.offset_hist.append((sensor_time, self.offset))
        if len(self.offset_hist) > 20000:
            del self.offset_hist[:10000]
        if dt is not None:
            self.dt_hist.append(dt)
            if len(self.dt_hist) > 20000:
                del self.dt_hist[:10000]
        return stamp, diag

    # -------------------------------------------------------------- reporting
    @staticmethod
    def _stats(values):
        if not values:
            return None
        v = sorted(values)
        n = len(v)

        def q(p):
            return v[min(n - 1, max(0, int(p * (n - 1))))]
        mean = sum(v) / n
        var = sum((x - mean) ** 2 for x in v) / n
        return dict(n=n, mean=mean, std=math.sqrt(var), min=v[0], p50=q(0.50),
                    p95=q(0.95), p99=q(0.99), max=v[-1])

    def offset_slope(self):
        if len(self.offset_hist) < 50:
            return None
        t = [p[0] for p in self.offset_hist]
        y = [p[1] for p in self.offset_hist]
        r = self._lsq(t, y)
        return None if r is None else r[0]

    def summary(self):
        return {
            'mode': self.mode,
            'samples': self.n,
            'bootstrapped': self.bootstrapped,
            'clock_offset_final': self.offset,
            'scale_a': self.scale_a,
            'scale_ppm': self.scale_ppm,
            'slope_updates': self.slope_updates,
            'offset_slope_s_per_s': self.offset_slope(),
            'n_clock_reset': self.n_clock_reset,
            'n_gated': self.n_gated,
            'n_gate_forced': self.n_gate_forced,
            'n_repairs': self.n_repair,
            'n_repairs_consecutive_max': self.n_repair_consec_max,
            'n_repairs_bad_dt': self.n_repair_bad_dt,
            'n_fatal_resets': self.n_fatal_reset,
            'last_repair_reason': self.last_repair_reason,
            'arrival_offset': self._stats(self.ao_hist),
            'dt': self._stats(self.dt_hist),
            'reset_reason': self.reset_reason,
        }

    def summary_text(self):
        s = self.summary()
        L = ['IMU_CLOCK mode=%s samples=%d bootstrapped=%s'
             % (s['mode'], s['samples'], s['bootstrapped'])]
        L.append('  clock_offset_final=%.9f s  offset_slope=%.3e s/s  scale=%+.1f ppm (updates=%d)'
                 % (s['clock_offset_final'] or float('nan'),
                    s['offset_slope_s_per_s'] or float('nan'),
                    s['scale_ppm'], s['slope_updates']))
        ao = s['arrival_offset']
        if ao:
            L.append('  arrival_offset: mean=%.6f std=%.6f min=%.6f p50=%.6f p95=%.6f p99=%.6f max=%.6f'
                     % (ao['mean'], ao['std'], ao['min'], ao['p50'], ao['p95'],
                        ao['p99'], ao['max']))
        d = s['dt']
        if d:
            L.append('  final dt     : mean=%.9f std=%.9f min=%.9f p50=%.9f p95=%.9f p99=%.9f max=%.9f'
                     % (d['mean'], d['std'], d['min'], d['p50'], d['p95'], d['p99'], d['max']))
            L.append('  final rate   : %.3f Hz (nominal %.1f)'
                     % (1.0 / d['mean'] if d['mean'] else 0.0, self.nominal_rate))
        L.append('  repairs=%d (max consecutive %d, implausible-dt %d) resets=%d '
                 'gated=%d gate_forced=%d clock_resets=%d'
                 % (s['n_repairs'], s['n_repairs_consecutive_max'],
                    s['n_repairs_bad_dt'], s['n_fatal_resets'], s['n_gated'],
                    s['n_gate_forced'], s['n_clock_reset']))
        return '\n'.join(L)


def simulate(mode, samples, **kw):
    """Offline replay of a mapping strategy over recorded (sensor, arrival) pairs.

    Returns (dts, stamps, summary_text, scale_ppm).
    """
    m = ImuClockMapper(mode=mode, **kw)
    dts, stamps = [], []
    for st, at in samples:
        s, d = m.update(st, at)
        stamps.append(s)
        if d['final_dt'] is not None:
            dts.append(d['final_dt'])
    return dts, stamps, m.summary_text(), m.scale_ppm


def _gen(rate=200.0, duration=120.0, drift_ppm=-1000.0, base_latency=0.003,
         jitter=0.002, stall_p=0.001, latency_ramp=0.0, seed=7):
    """Synthesise (sensor_time, arrival_time) pairs.

    latency_ramp: additional linear drift of the *transport* delay in s/s; this
    is indistinguishable from clock drift unless an external clock reference
    exists, and is what makes the low-quantile estimator the honest choice.
    """
    import random
    random.seed(seed)
    nominal = 1.0 / rate
    samples = []
    t_px4 = 100000.0
    t_host = 1790000000.0
    n = int(rate * duration)
    for i in range(n):
        lat = base_latency + latency_ramp * (i * nominal) + abs(random.gauss(0, jitter))
        if random.random() < stall_p:
            lat += random.uniform(0.05, 0.3)
        samples.append((t_px4, t_host + lat))
        t_px4 += nominal
        t_host += nominal * (1.0 + drift_ppm * 1e-6)
    return samples


SCENARIOS = [
    ('neg drift -1000ppm', dict(drift_ppm=-1000.0)),
    ('pos drift +1000ppm', dict(drift_ppm=+1000.0)),
    ('zero drift + latency ramp +50ppm', dict(drift_ppm=0.0, latency_ramp=50e-6)),
    ('heavy jitter 8ms', dict(drift_ppm=-500.0, jitter=0.008, stall_p=0.005)),
    ('LONG 600s pos drift +1000ppm', dict(drift_ppm=+1000.0, duration=600.0)),
    ('LONG 600s neg drift -1000ppm', dict(drift_ppm=-1000.0, duration=600.0)),
]


def _selftest():
    import statistics
    print('%-9s %-34s %10s %10s %10s %12s' % (
        'mode', 'scenario', 'dt_std', 'dt_p99', 'dt_max', 'axis_err_ppm'))
    print('-' * 92)
    for name, kw in SCENARIOS:
        samples = _gen(**kw)
        true_span_host = samples[-1][1] - samples[0][1]
        for mode in ImuClockMapper.MODES:
            dts, stamps, txt, scale = simulate(mode, samples, nominal_rate=200.0)
            d = sorted(dts)
            n = len(d)
            span = stamps[-1] - stamps[0]
            axis_err = ((span / true_span_host) - 1.0) * 1e6
            print('%-9s %-34s %10.3e %10.6f %10.6f %12.1f' % (
                mode, name, statistics.pstdev(dts), d[int(0.99 * (n - 1))],
                d[-1], axis_err))
    print()
    print('axis_err_ppm = (mapped IMU axis advance)/(true host advance) - 1.')
    print('Camera stamps advance in the host domain, so |axis_err_ppm| is the rate')
    print('at which the camera/IMU alignment drifts: 1000 ppm = 3.6 s per hour.')
    print()
    print('=' * 92)
    print('DETAIL: neg drift -1000ppm')
    print('=' * 92)
    samples = _gen(drift_ppm=-1000.0)
    for mode in ImuClockMapper.MODES:
        _, _, txt, _ = simulate(mode, samples, nominal_rate=200.0)
        print('-' * 92)
        print(txt)
    print()
    print('=' * 92)
    print('DETAIL: positive drift (+1000 ppm) -- exposes the direction dependence')
    print('of the legacy lower-envelope rule')
    print('=' * 92)
    samples = _gen(drift_ppm=+1000.0)
    for mode in ImuClockMapper.MODES:
        _, _, txt, _ = simulate(mode, samples, nominal_rate=200.0)
        print('-' * 92)
        print(txt)


if __name__ == '__main__':
    _selftest()
