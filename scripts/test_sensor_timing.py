"""Synthetic regression fixtures; these are NOT hardware validation results."""
import unittest
from analyze_sensor_timing import summarize, nearest_distances


class TimingTests(unittest.TestCase):
    def test_pairs_cannot_reuse_right_frame(self):
        s = summarize([0, 100, 200], [0, 200], [0, 100, 200], 0.000001)
        self.assertEqual(s['stereo']['paired_count'], 2)
        self.assertEqual(s['stereo']['unmatched_left_count'], 1)

    def test_backwards_duplicates_and_large_epoch(self):
        base = 1789310000 * 10**9
        s = summarize([base,base+100,base+100,base+50], [], [])
        self.assertEqual(s['camera_left']['negative_timestamp_count'], 1)
        self.assertEqual(s['camera_left']['duplicate_timestamp_count'], 1)
        self.assertEqual(s['camera_nearest_imu_sec']['left']['count'], 0)

    def test_nearest_handles_boundaries(self):
        self.assertAlmostEqual(nearest_distances([5,15,30],[10,20])[2], 10e-9)

    def test_missing_stereo_pair_not_hidden_by_censoring(self):
        s = summarize([0, 33000000], [10000000, 43000000], [0,10000000])
        self.assertEqual(s['stereo']['paired_count'], 0)
        self.assertEqual(s['stereo']['frame_pairing_mismatch_count'], 4)
        self.assertAlmostEqual(s['stereo']['all_left_nearest_right_sec']['mean'], .01)


if __name__ == '__main__':
    unittest.main()
