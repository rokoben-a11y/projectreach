#!/usr/bin/env python3
"""Private prebundle repack. Fixtures are inert and must not resemble commercial game files."""
import hashlib
import importlib.util
import json
import plistlib
import stat
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('repack_prebundled_game', ROOT / 'scripts' / 'repack-prebundled-game.py')
REPACK = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(REPACK)
BUNDLE_ID = REPACK.BUNDLE_ID
allowed_private = REPACK.allowed_private
repack = REPACK.repack

SECRET = b'SUPER-SECRET-PRODUCT-KEY-DO-NOT-LOG'
STOCK = b'inert-stock-bytes'


def identity_for(body):
    return {
        'schema': 1,
        'profile': 'custom-en-1.0.10.0621',
        'stock_files': {
            'maps/example.bin': {'size': len(body), 'sha256': hashlib.sha256(body).hexdigest()},
        },
    }


def write_app(root, *, mac=False, modules=True, bundle=BUNDLE_ID):
    app = root / 'HaloPad.app'
    base = app / 'Contents' / 'Resources' if mac else app
    if mac:
        (app / 'Contents' / 'MacOS').mkdir(parents=True)
        exe = app / 'Contents' / 'MacOS' / 'HaloPad'
        plist = app / 'Contents' / 'Info.plist'
    else:
        app.mkdir(parents=True)
        exe = app / 'HaloPad'
        plist = app / 'Info.plist'
    exe.write_bytes(b'not-a-mach-o')
    exe.chmod(0o755)
    info = {
        'CFBundleIdentifier': bundle,
        'CFBundleShortVersionString': '0.3.15',
        'CFBundleVersion': '1',
        'CFBundleExecutable': 'HaloPad',
    }
    plist.write_bytes(plistlib.dumps(info))
    if modules:
        module = base / 'data' / 'modules' / 'haloce'
        module.mkdir(parents=True)
        (module / 'image.bin').write_bytes(b'module-image')
        (base / 'data' / 'core-identity.json').write_text(json.dumps(identity_for(STOCK)) + '\n')
    return app


def write_game(root, body=STOCK, extra=True):
    game = root / 'game'
    (game / 'maps').mkdir(parents=True)
    (game / 'maps' / 'example.bin').write_bytes(body)
    if extra:
        (game / 'product-key.txt').write_bytes(SECRET)
        (game / 'notes.txt').write_bytes(SECRET)
    return game


def run_script(app, game, ipa):
    return subprocess.run([sys.executable, str(ROOT / 'scripts' / 'repack-prebundled-game.py'),
                           '--app', str(app), '--game', str(game), '--ipa', str(ipa)],
                          capture_output=True, text=True)


class PrebundledRepackTests(unittest.TestCase):
    def test_paths_inside_tracked_source_are_refused(self):
        self.assertFalse(allowed_private(ROOT / 'port' / 'ios'))
        self.assertTrue(allowed_private(ROOT / 'generated' / 'not-created.ipa'))
        self.assertTrue(allowed_private(Path(tempfile.gettempdir()) / 'halopad-outside.ipa'))

    def test_unsigned_ipa_embeds_matching_stock_and_preserves_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            app = write_app(root)
            game = write_game(root)
            ipa = root / 'HaloPad-prebundled.ipa'
            before = (app / 'Info.plist').read_bytes()
            result = run_script(app, game, ipa)
            output = result.stdout + result.stderr
            self.assertEqual(result.returncode, 0, output)
            self.assertNotIn(SECRET.decode(), output)
            self.assertNotIn(hashlib.sha256(STOCK).hexdigest(), output)
            self.assertNotIn(str(game), output)
            self.assertIn('unsigned ipa written: HaloPad-prebundled.ipa', result.stdout)
            self.assertIn('skipped non-stock files: 2', result.stdout)
            self.assertEqual((app / 'Info.plist').read_bytes(), before)
            self.assertFalse((app / 'bundled-game').exists())
            with zipfile.ZipFile(ipa) as archive:
                names = archive.namelist()
                blob = b''.join(archive.read(name) for name in names)
            self.assertIn('Payload/HaloPad.app/bundled-game/maps/example.bin', names)
            self.assertIn('Payload/HaloPad.app/data/modules/haloce/image.bin', names)
            self.assertNotIn(SECRET, blob)
            info = plistlib.loads(zipfile.ZipFile(ipa).read('Payload/HaloPad.app/Info.plist'))
            self.assertEqual(info['CFBundleIdentifier'], BUNDLE_ID)
            self.assertEqual(info['CFBundleShortVersionString'], '0.3.15')
            self.assertEqual(info['CFBundleVersion'], '1')
            mode = zipfile.ZipFile(ipa).getinfo('Payload/HaloPad.app/HaloPad').external_attr >> 16
            self.assertTrue(mode & stat.S_IXUSR)

    def test_mac_shell_uses_resources_bundled_game(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            app = write_app(root, mac=True)
            ipa = root / 'HaloPad-mac.ipa'
            self.assertEqual(repack(app, write_game(root, extra=False), ipa), (1, 0))
            with zipfile.ZipFile(ipa) as archive:
                self.assertIn('Payload/HaloPad.app/Contents/Resources/bundled-game/maps/example.bin', archive.namelist())
                self.assertIn('Payload/HaloPad.app/Contents/Resources/data/modules/haloce/image.bin', archive.namelist())

    def test_mismatch_names_the_inventory_path_without_a_hash(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            app = write_app(root)
            game = write_game(root, body=b'different-bytes')
            result = run_script(app, game, root / 'out.ipa')
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('maps/example.bin', result.stderr)
            self.assertNotIn(hashlib.sha256(STOCK).hexdigest(), result.stderr)
            self.assertNotIn(SECRET.decode(), result.stdout + result.stderr)
            self.assertFalse((root / 'out.ipa').exists())

    def test_shell_without_modules_is_not_a_custom_edition_build(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = run_script(write_app(root, modules=False), write_game(root), root / 'out.ipa')
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('no Custom Edition modules', result.stderr)

    def test_bundle_id_and_tracked_paths_stay_put(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = run_script(write_app(root / 'wrong-id', bundle='dev.halopad.HaloPad.robby'), write_game(root), root / 'out.ipa')
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(BUNDLE_ID, result.stderr)
            tracked = run_script(write_app(root / 'tracked'), ROOT / 'port', root / 'out.ipa')
            self.assertNotEqual(tracked.returncode, 0)
            self.assertIn('outside tracked source', tracked.stderr)

    def test_symlink_stock_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            game = write_game(root, extra=False)
            outside = root / 'outside.bin'
            outside.write_bytes(STOCK)
            link = game / 'maps' / 'example.bin'
            link.unlink()
            link.symlink_to(outside)
            result = run_script(write_app(root), game, root / 'out.ipa')
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse((root / 'out.ipa').exists())
            self.assertNotIn(SECRET.decode(), result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main()
