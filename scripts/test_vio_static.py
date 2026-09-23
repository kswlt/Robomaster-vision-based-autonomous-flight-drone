import unittest
from score_vio_static import score


class StaticScoreTests(unittest.TestCase):
    def test_complete_stationary(self):
        r=score([0,120000000000],[[0,0,0],[0,0,0]],[[0,0,0],[0,0,0]],[[0,0,0],[0,0,0]])
        self.assertEqual(r['status'],'PASS_STATIC_ENGINEERING_GATE')

    def test_short_stationary_cannot_pass(self):
        r=score([0,119000000000],[[0,0,0],[0,0,0]],[[0,0,0],[0,0,0]],[[0,0,0],[0,0,0]])
        self.assertFalse(r['complete_window'])

    def test_return_to_origin_does_not_hide_excursion(self):
        r=score([0,60000000000,120000000000],[[0,0,0],[1,0,0],[0,0,0]],[[0,0,0]]*3,[[0,0,0]]*3)
        self.assertAlmostEqual(r['position_endpoint_drift_m'],0)
        self.assertEqual(r['position_peak_drift_m'],1)
        self.assertNotEqual(r['status'],'PASS_STATIC_ENGINEERING_GATE')


if __name__=='__main__':
    unittest.main()
