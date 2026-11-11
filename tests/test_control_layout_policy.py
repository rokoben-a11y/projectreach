#!/usr/bin/env python3
"""Shared touch-layout policy. Geometry is tested on the host; Halo bindings stay in the app."""
import json
import pathlib
import re
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
POLICY = ROOT / 'port/shared/control-layout-v1.json'
BINDINGS = ROOT / 'port/ios/halopad-control-bindings.json'
VECTORS = ROOT / 'tests/fixtures/control-layout-v1-vectors.json'
OVERLAY = ROOT / 'port/ios/HaloPadOverlay.m'
DUMP = ROOT / 'tests/control_layout_dump.c'


def load(path):
    return json.loads(path.read_text())


def boxes_overlap(a, b):
    dx = a[0] - (b[0] + b[2]) if a[0] > b[0] else b[0] - (a[0] + a[2])
    dy = a[1] - (b[1] + b[3]) if a[1] > b[1] else b[1] - (a[1] + a[3])
    return dx < -0.5 and dy < -0.5


def compile_dump():
    out = pathlib.Path(tempfile.mkdtemp(prefix='halopad-layout-')) / 'dump'
    subprocess.run(['cc', '-std=c11', '-Wall', '-Wextra', '-Werror', '-o', str(out), str(DUMP)],
                   check=True, cwd=ROOT)
    return json.loads(subprocess.check_output([str(out)], cwd=ROOT, text=True))


class ControlLayoutPolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.live = compile_dump()
        cls.policy = load(POLICY)
        cls.bindings = load(BINDINGS)
        cls.vectors = load(VECTORS)

    def test_live_dump_matches_vectors(self):
        self.assertEqual(self.live, self.vectors)

    def test_policy_is_geometry_only_and_excludes_playport(self):
        self.assertEqual(self.policy['id'], self.live['policy'])
        self.assertEqual(self.policy['version'], self.live['version'])
        self.assertEqual(self.policy['selection']['large_min_safe_width'], self.live['large_min_safe_width'])
        self.assertEqual(self.policy['selection']['large_min_safe_height'], self.live['large_min_safe_height'])
        self.assertEqual(self.policy['minimum_target_points'], self.live['minimum_target_points'])
        self.assertFalse(self.policy['selection']['uses_device_model'])
        self.assertEqual(self.policy['slots'], [slot['id'] for slot in self.bindings['slots']])
        self.assertIn('HaloPad', self.policy['consumers'])
        self.assertIn('KartPad', self.policy['future_consumers'])
        self.assertEqual(self.policy['excluded_consumers'], ['Playport'])
        self.assertNotIn('Playport', json.dumps(self.bindings))
        self.assertNotIn('fallback_actions', self.policy)
        self.assertNotRegex(json.dumps(self.policy), r'\bvk\b')

    def test_halo_bindings_match_overlay_table(self):
        block = OVERLAY.read_text().split('static const hp_control_def CONTROLS[] = {', 1)[1].split('};', 1)[0]
        rows = re.findall(r'\{"(\w+)",\s+"([^"]*)",\s+"[^"]*",\s+(-?\d+),\s+(\d),\s+(\d)\}', block)
        buttons = [slot for slot in self.bindings['slots'] if slot.get('kind') != 'stick']
        self.assertEqual([(row[0], row[1], int(row[2]), int(row[3]), int(row[4])) for row in rows],
                         [(slot['ident'], slot['caption'], slot['action'], int(slot['look']), slot['size']) for slot in buttons])
        move = OVERLAY.read_text()
        self.assertIn('static const uint32_t actions[4] = {19, 21, 20, 22};', move)
        self.assertEqual(self.bindings['slots'][0]['fallback_actions'], [19, 21, 20, 22])
        self.assertEqual(self.bindings['layout_policy'], self.policy['id'])

    def test_vectors_cover_both_size_classes_without_a_device_model(self):
        classes = {vector['size_class'] for vector in self.live['vectors']}
        self.assertEqual(classes, {'compact', 'large'})
        by_safe = {(tuple(vector['safe']), vector['left_handed']): vector for vector in self.live['vectors']}
        narrow = by_safe[((47.0, 0.0, 780.0, 340.0), 0)]
        wide = next(vector for vector in self.live['vectors'] if vector['size_class'] == 'large' and vector['safe'][2] >= 900)
        self.assertEqual(narrow['size_class'], 'compact')
        self.assertLess(self._bottom_gap(narrow), self._bottom_gap(wide))
        mirrored = by_safe[((47.0, 0.0, 780.0, 340.0), 1)]
        self.assertAlmostEqual(narrow['frames'][0][0] + narrow['frames'][0][2] / 2
                               + mirrored['frames'][0][0] + mirrored['frames'][0][2] / 2,
                               47.0 + 47.0 + 780.0, places=3)

    def test_every_vector_stays_inside_and_uncovered(self):
        for vector in self.live['vectors']:
            sx, sy, sw, sh = vector['safe']
            frames = vector['frames']
            self.assertEqual(len(frames), 15)
            for frame in frames:
                self.assertGreaterEqual(frame[0], sx - 0.05)
                self.assertGreaterEqual(frame[1], sy - 0.05)
                self.assertLessEqual(frame[0] + frame[2], sx + sw + 0.05)
                self.assertLessEqual(frame[1] + frame[3], sy + sh + 0.05)
                self.assertGreaterEqual(min(frame[2], frame[3]), 44)
            for i, left in enumerate(frames):
                for right in frames[i + 1:]:
                    self.assertFalse(boxes_overlap(left, right), vector['safe'])
            self.assertGreaterEqual(frames[2][2], frames[3][2])
        roomy = self.live['vectors'][0]
        self.assertGreater(roomy['frames'][2][2], roomy['frames'][3][2])

    def test_regular_scene_anchors_the_grip_to_the_keyboard_band(self):
        same = [vector for vector in self.live['vectors'] if vector['safe'][2] == 867.0 and vector['safe'][3] == 635.0]
        raised = next(vector for vector in same if not vector['bottom_band'])
        band = next(vector for vector in same if vector['bottom_band'])
        self.assertEqual(raised['size_class'], 'large')
        self.assertLess(self._bottom_gap(band), band['safe'][3] * 0.34)
        self.assertGreater(self._bottom_gap(raised), raised['safe'][3] * 0.34)
        grip_top = min(frame[1] for frame in band['frames'])
        _, sy, _, sh = band['safe']
        self.assertGreater(grip_top, sy + sh * 0.40)

    def test_bottom_band_stays_off_the_fold_and_camera(self):
        for case in self.live['avoidance']:
            frames = case['frames']
            self.assertEqual(len(frames), 15)
            for frame in frames:
                self.assertGreaterEqual(min(frame[2], frame[3]), 44)
                for region in case['regions']:
                    self.assertFalse(boxes_overlap(frame, region), (frame, region))
            for i, left in enumerate(frames):
                for right in frames[i + 1:]:
                    self.assertFalse(boxes_overlap(left, right))
            horizontal = [region for region in case['regions'] if region[2] >= region[3] and region[2] > 100]
            for region in horizontal:
                fold_bottom = region[1] + region[3]
                for frame in frames:
                    self.assertGreaterEqual(frame[1], fold_bottom - 0.05)

    def test_overlay_chooses_the_bottom_band_from_size_classes(self):
        text = OVERLAY.read_text()
        method = text.split('- (BOOL)innerBottomBand', 1)[1].split('\n}', 1)[0]
        self.assertIn('UIUserInterfaceSizeClassRegular', method)
        self.assertIn('horizontalSizeClass', method)
        self.assertIn('verticalSizeClass', method)
        self.assertIn('coordinateSpace.bounds', method)
        self.assertNotIn('userInterfaceIdiom', method)
        self.assertNotIn('UIScreen', method)
        self.assertNotIn('700', method)
        self.assertIn('reservedRegionsOfKind:', text)
        self.assertIn('.bottom_band = [self innerBottomBand]', text)

    def test_reserved_regions_pass_a_kind_object(self):
        """UIKit 27.1: -reservedRegionsOfKind:(UIViewReservedRegionKind *)kind options:. An integer kind crashed the CE screen."""
        text = OVERLAY.read_text()
        method = text.split('- (int)copyReservedRegions:', 1)[1].split('\n}\n', 1)[0]
        self.assertIn('@available(iOS 27.1, *)', method)
        self.assertIn('[UIViewReservedRegionKind divisionRegionKind]', method)
        self.assertIn('[UIViewReservedRegionKind occlusionRegionKind]', method)
        self.assertIn('reservedRegionsOfKind:kind options:UIViewReservedRegionQueryOptionsNone', method)
        self.assertNotIn('NSInvocation', text)
        self.assertNotIn('NSSelectorFromString(@"reservedRegions', text)
        self.assertNotRegex(text, r'setArgument:&kind')

    def _bottom_gap(self, vector):
        _, sy, _, sh = vector['safe']
        move = vector['frames'][0]
        return (sy + sh) - (move[1] + move[3] / 2)


if __name__ == '__main__':
    unittest.main()
