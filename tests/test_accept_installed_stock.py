#!/usr/bin/env python3
"""Installed Custom Edition stock must match the locked profile before translation."""
import hashlib
import importlib.util
import json
import pathlib
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
UPLOAD = pathlib.Path('/home/ubuntu/.cursor/projects/workspace/uploads/old-stock-inventory_0579.json')
SPEC = importlib.util.spec_from_file_location('accept_installed_stock', ROOT / 'scripts' / 'accept-installed-stock.py')
ACCEPT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ACCEPT)

# Hashes named by the old personal IPA inventory for the locked 1.10 client.
OLD_IPA_LOCKED = {
    'haloce.exe': 'feea46fce285ec071016cf5534abe47ecf36f6cfac8f1973ee6919851ea5a037',
    'Keystone.dll': 'cfefc87686617ed110bccc7947895f452c410e367db096980473ed5d9d05d713',
    'ksimeui.dll': 'ae238ebbb61a363a86fb20cd1cb7e07df2f6d2e07e456bdf1f0b75a79e7cc81c',
    'controls/Controls.dll': 'ab96837c2886a701a79179be6f98b5ae53e4972ef5403592ce625514767af646',
}


def sha(body):
    return hashlib.sha256(body).hexdigest()


def product_file(directory):
    path = directory / 'product-id.txt'
    path.write_text(
        'value HKLM\\Software\\Microsoft\\Microsoft Games\\Halo CE 1 504944 616200\n'
        'value HKLM\\Software\\Microsoft\\Microsoft Games\\Halo CE 3 4469676974616c50726f647563744944 636400\n')
    return path


class InstalledStockTests(unittest.TestCase):
    def test_old_ipa_inventory_matches_the_locked_profile(self):
        profile = json.loads((ROOT / 'config/profiles/custom-en-1.0.10.0621.json').read_text())
        self.assertEqual(OLD_IPA_LOCKED['haloce.exe'], profile['accepted_sha256'])
        modules = {module['file']: module['sha256'] for module in profile['modules'].values() if 'root' not in module}
        for name, digest in OLD_IPA_LOCKED.items():
            if name == 'haloce.exe':
                continue
            self.assertEqual(modules[name], digest)
        if UPLOAD.is_file():
            listed = {row['path']: row['sha256'] for row in json.loads(UPLOAD.read_text())['stock'] if 'sha256' in row}
            for name, digest in OLD_IPA_LOCKED.items():
                self.assertEqual(listed[name], digest)

    def test_stage_accepts_matching_bytes_and_rejects_the_rest(self):
        exe = b'locked-client'
        dll = b'locked-keystone'
        library = b'redistributable'
        profile = {
            'id': 'custom-en-1.0.10.0621',
            'executable': 'haloce.exe',
            'accepted_sha256': sha(exe),
            'modules': {'keystone': {'file': 'Keystone.dll', 'sha256': sha(dll)}},
        }
        reference_files = (('system32/msxml4.dll', sha(library)),)
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            game = root / 'bundled-game'
            (game / 'maps').mkdir(parents=True)
            (game / 'haloce.exe').write_bytes(exe)
            (game / 'Keystone.dll').write_bytes(dll)
            (game / 'maps' / 'example.map').write_bytes(b'map')
            (game / 'product-key.txt').write_bytes(b'SUPER-SECRET-PRODUCT-KEY-DO-NOT-LOG')
            reference = root / 'reference'
            (reference / 'system32').mkdir(parents=True)
            (reference / 'system32' / 'msxml4.dll').write_bytes(library)
            out = root / 'staged'
            ref_out = root / 'ref-out'
            self.assertTrue(ACCEPT.stage(game, reference, profile, out, ref_out, reference_files))
            self.assertEqual((out / 'haloce.exe').read_bytes(), exe)
            self.assertFalse((out / 'product-key.txt').exists())
            manifest = json.loads((out / 'MANIFEST.json').read_text())
            self.assertEqual(manifest['origin'], 'installed-stock')
            listed = {row['path']: row['sha256'] for row in manifest['files']}
            self.assertEqual(listed['haloce.exe'], sha(exe))
            (game / 'haloce.exe').write_bytes(b'different')
            with self.assertRaises(ACCEPT.StockError):
                ACCEPT.stage(game, reference, profile, root / 'other', ref_out, reference_files)
            self.assertFalse((root / 'other').exists())

    def test_old_modules_and_bad_product_id_are_refused(self):
        exe = b'locked-client'
        profile = {'id': 'custom-en-1.0.10.0621', 'executable': 'haloce.exe',
                   'accepted_sha256': sha(exe), 'modules': {}}
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            game = root / 'bundled-game'
            (game / 'modules' / 'haloce').mkdir(parents=True)
            (game / 'haloce.exe').write_bytes(exe)
            (game / 'modules' / 'haloce' / 'image.bin').write_bytes(b'old-translation')
            with self.assertRaisesRegex(ACCEPT.StockError, 'old translated modules'):
                ACCEPT.check_game(game, profile)
            secret = root / 'not-a-product-id.txt'
            secret.write_text('SUPER-SECRET-PRODUCT-KEY-DO-NOT-LOG\n')
            with self.assertRaises(ACCEPT.StockError) as caught:
                ACCEPT.product_id_text(secret)
            self.assertNotIn('SUPER-SECRET', str(caught.exception))
            self.assertTrue(ACCEPT.product_id_text(product_file(root)).startswith('value '))

    def test_tracked_source_is_not_a_stock_root(self):
        with self.assertRaisesRegex(ACCEPT.StockError, 'outside tracked source'):
            ACCEPT.stage(ROOT / 'port', ROOT / 'config', {'executable': 'haloce.exe', 'accepted_sha256': 'abc',
                                                          'id': 'custom-en-1.0.10.0621', 'modules': {}},
                         ROOT / 'docs', ROOT / 'scripts')


if __name__ == '__main__':
    unittest.main()
