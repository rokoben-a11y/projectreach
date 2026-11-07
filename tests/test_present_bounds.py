#!/usr/bin/env python3
"""Presentation uses the view's real bounds. Fill has no bars on a non-4:3 view."""
import json
import pathlib
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
DUMP = ROOT / 'tests' / 'present_bounds_dump.c'
APP = (ROOT / 'port/ios/HaloPadApp.m').read_text()
HOST = (ROOT / 'port/apple/halopad_host_ios.m').read_text()
OVERLAY = (ROOT / 'port/ios/HaloPadOverlay.m').read_text()


def frames():
    out = pathlib.Path(tempfile.mkdtemp(prefix='halopad-present-')) / 'dump'
    subprocess.run(['cc', '-std=c11', '-Wall', '-Wextra', '-Werror', '-o', str(out), str(DUMP)],
                   check=True, cwd=ROOT)
    rows = {}
    for line in subprocess.check_output([str(out)], text=True).splitlines():
        row = json.loads(line)
        rows[row['name']] = row
    return rows


class PresentBoundsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows = frames()

    def test_fill_matches_non_phone_bounds(self):
        for name in ('wide-fill', 'tall-fill', 'inner-fill', 'phone-fill'):
            row = self.rows[name]
            self.assertEqual(row['frame'], [0.0, 0.0, row['view'][0], row['view'][1]])

    def test_fit_insets_a_wide_view(self):
        row = self.rows['wide-fit']
        x, y, w, h = row['frame']
        self.assertGreater(x, 0)
        self.assertEqual(y, 0)
        self.assertLess(w, row['view'][0])
        self.assertEqual(h, row['view'][1])
        inner = self.rows['inner-fit']['frame']
        self.assertGreater(inner[0], 0)
        self.assertLess(inner[2], 900)

    def test_shell_fills_unless_the_player_chooses_original(self):
        self.assertIn('@"HaloPad.aspect": @1', OVERLAY)
        self.assertIn('hp_present_frame', APP)
        self.assertIn('kCAGravityResize;', HOST)
        self.assertNotIn('kCAGravityResizeAspect;', HOST)


if __name__ == '__main__':
    unittest.main()
