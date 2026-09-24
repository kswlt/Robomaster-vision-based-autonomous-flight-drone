#!/usr/bin/env python3
"""Regression: ZUPT local gate is AND (disparity AND chi2), not OR.

Fails if UpdaterZeroVelocity.cpp reverts to the upstream-style `||` that lets
either gate alone accept, or if chi2_multipler=0 is reintroduced with
try_zupt=true (permanent reject while logs still look "normal").

Does NOT change any threshold -- it only asserts the source semantics and the
frozen config values that made ZUPT work.
"""
import os
import re
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
UPDATER = os.path.join(_ROOT, 'ov_msckf', 'src', 'update', 'UpdaterZeroVelocity.cpp')
CONFIG = os.path.join(_ROOT, 'config', 'd430', 'estimator_config.yaml')


def fail(msg):
    print('FAIL: %s' % msg)
    return 1


def ok(msg):
    print('OK:   %s' % msg)
    return 0


def main():
    rc = 0
    src = open(UPDATER, encoding='utf-8', errors='replace').read()

    # Accept only when BOTH gates pass  <=>  reject if either fails.
    # Correct frozen local form: if (!disparity_passed || !inertial_passed) return false;
    # That is AND-accept (both required).  The upstream OR-accept form is
    # if (!disparity_passed && !inertial_passed) return false;  (reject only both-fail).
    if re.search(r'if\s*\(\s*!disparity_passed\s*&&\s*!inertial_passed\s*\)', src):
        rc |= fail('ZUPT reject is AND-of-failures (= OR accept): upstream bug shape')
    elif re.search(r'!disparity_passed\s*\|\|\s*!inertial_passed', src):
        rc |= ok('reject path is if (!disparity || !inertial) -> both must pass (AND)')
    else:
        rc |= fail('could not find local ZUPT reject conjunction in source')

    if 'chi2 <= chi2_limit' not in src and 'chi2 <=chi2_limit' not in src:
        # allow spacing variants
        if not re.search(r'chi2\s*<=\s*chi2_limit', src):
            rc |= fail('inertial chi2 comparison missing')
        else:
            rc |= ok('inertial gate compares chi2 <= chi2_limit')
    else:
        rc |= ok('inertial gate compares chi2 <= chi2_limit')

    if not os.path.isfile(CONFIG):
        rc |= fail('frozen config missing: %s' % CONFIG)
    else:
        cfg = open(CONFIG, encoding='utf-8', errors='replace').read()
        m_z = re.search(r'^try_zupt:\s*(\S+)', cfg, re.M)
        m_c = re.search(r'^zupt_chi2_multipler:\s*([\d.eE+-]+)', cfg, re.M)
        if not m_z or m_z.group(1) != 'true':
            rc |= fail('try_zupt must stay true (frozen), got %r' % (m_z.group(1) if m_z else None))
        else:
            rc |= ok('try_zupt: true (frozen)')
        if not m_c:
            rc |= fail('zupt_chi2_multipler missing from frozen config')
        else:
            chi2m = float(m_c.group(1))
            if chi2m <= 0.0:
                rc |= fail('zupt_chi2_multipler=%g makes chi2_limit=0 -> permanent reject' % chi2m)
            else:
                rc |= ok('zupt_chi2_multipler=%g > 0 (ZUPT can accept)' % chi2m)

    print()
    print('RESULT: %s' % ('PASS' if rc == 0 else 'FAIL'))
    return rc


if __name__ == '__main__':
    sys.exit(main())
