#!/usr/bin/env python3
"""Stage an already-installed Custom Edition 1.10 tree for a new translation.

The executable and profile modules must match the locked profile hashes.
Maps and other stock files are copied for the signed inventory. Old translated
modules are never an input. Product-id text is checked for shape only and is
not printed.
"""
import argparse
import datetime
import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROFILE_PATH = ROOT / 'config/profiles/custom-en-1.0.10.0621.json'
STOCK_OUT = ROOT / 'ref/inputs/custom-original'
REFERENCE_OUT = ROOT / 'ref/inputs/reference-machine'
REFERENCE_FILES = (
    ('system32/msxml4.dll', '9808f05f0da3775f07a88fd614f038e6f4ac5ff680c73d5fd40116a5a247a53d'),
    ('system32/msxml4r.dll', '4e75a8e8cbc8486cafc73b208532c6969c23731ecf0c93e66a4ac076136de750'),
)
DENY_NAMES = {'product-key.txt', 'product-id.txt'}
PRODUCT_ID_PATH = 'HKLM\\Software\\Microsoft\\Microsoft Games\\Halo CE'
PRODUCT_ID_NAMES = {'504944', '4469676974616c50726f647563744944'}


class StockError(Exception):
    pass


def fold(value):
    return unicodedata.normalize('NFC', value).casefold()


def digest(path):
    hashed = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            hashed.update(block)
    return hashed.hexdigest()


def private_path(path):
    path = path.resolve()
    try:
        relative = path.relative_to(ROOT)
    except ValueError:
        return True
    return subprocess.run(['git', '-C', str(ROOT), 'check-ignore', '-q', '--no-index', str(relative)]).returncode == 0


def index_files(root):
    if root.is_symlink() or not root.is_dir():
        raise StockError('stock path is not a directory')
    found = {}
    for directory, dirnames, filenames in os.walk(root, followlinks=False):
        dirnames.sort()
        for name in filenames:
            path = Path(directory) / name
            if path.is_symlink() or not stat.S_ISREG(path.lstat().st_mode):
                raise StockError('stock tree contains a link or special file')
            relative = path.relative_to(root).as_posix()
            if fold(Path(relative).name) in DENY_NAMES:
                continue
            key = fold(relative)
            if key in found:
                raise StockError('stock tree has an ambiguous path')
            found[key] = path
    return found


def require_hash(found, relative, expected):
    path = found.get(fold(relative))
    if path is None or digest(path) != expected:
        raise StockError(relative + ' does not match the locked profile')
    return path


def product_id_text(path):
    """Same two registry lines scripts/product-id.sh writes. Contents are not echoed."""
    lines = [line for line in path.read_text(errors='replace').splitlines() if line and not line.startswith('#')]
    names = set()
    for line in lines:
        fields = line.split(' ')
        if (len(fields) < 5 or fields[0] != 'value' or ' '.join(fields[1:-3]) != PRODUCT_ID_PATH
                or fields[-2] not in PRODUCT_ID_NAMES or fields[-3] not in ('1', '3')):
            raise StockError('product-id file is not the installer result HaloPad already accepts')
        names.add(fields[-2])
    if names != PRODUCT_ID_NAMES:
        raise StockError('product-id file is missing PID or DigitalProductID')
    return '\n'.join(lines) + '\n'


def locked_modules(profile):
    rows = [(profile['executable'], profile['accepted_sha256'])]
    for module in profile['modules'].values():
        if 'root' not in module:
            rows.append((module['file'], module['sha256']))
    return rows


def check_game(game, profile):
    found = index_files(game)
    for key in found:
        parts = key.split('/')
        if 'modules' in parts and parts[-1] == 'image.bin':
            raise StockError('old translated modules are not stock; pass bundled-game only')
    for relative, expected in locked_modules(profile):
        require_hash(found, relative, expected)
    return found


def check_reference(reference, files=REFERENCE_FILES):
    found = index_files(reference)
    for relative, expected in files:
        require_hash(found, relative, expected)
    return found


def write_manifest(destination, found, root, profile_id):
    files = []
    for path in sorted(found.values(), key=lambda item: fold(item.relative_to(root).as_posix())):
        relative = path.relative_to(root).as_posix()
        files.append({'path': relative, 'size': path.stat().st_size, 'sha256': digest(path), 'origin': 'installed-stock'})
    document = {
        'schema': 1,
        'profile': profile_id,
        'created_utc': datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
        'origin': 'installed-stock',
        'file_count': len(files),
        'files': files,
    }
    (destination / 'MANIFEST.json').write_text(json.dumps(document, indent=2) + '\n')
    return len(files)


def stage_tree(found, source, destination):
    if destination.exists():
        exe = destination / 'haloce.exe'
        if not exe.is_file():
            raise StockError('refusing to replace an incomplete stock directory')
        return False
    destination.mkdir(parents=True)
    for path in found.values():
        relative = path.relative_to(source)
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
    return True


def stage(game, reference, profile, stock_out=STOCK_OUT, reference_out=REFERENCE_OUT, reference_files=REFERENCE_FILES):
    if not private_path(game) or not private_path(reference) or not private_path(stock_out) or not private_path(reference_out):
        raise StockError('stock and reference paths must stay outside tracked source')
    found = check_game(game, profile)
    reference_found = check_reference(reference, reference_files)
    if stock_out.exists():
        existing = stock_out / profile['executable']
        if not existing.is_file() or digest(existing) != profile['accepted_sha256']:
            raise StockError('refusing to replace stock that does not match the locked profile')
        copied = False
    else:
        stage_tree(found, game, stock_out)
        write_manifest(stock_out, index_files(stock_out), stock_out, profile['id'])
        copied = True
    if not (stock_out / 'MANIFEST.json').is_file():
        write_manifest(stock_out, index_files(stock_out), stock_out, profile['id'])
    for relative, expected in reference_files:
        target = reference_out / relative
        if target.is_file() and digest(target) == expected:
            continue
        if target.exists():
            raise StockError('refusing to replace ' + relative)
        source = reference_found[fold(relative)]
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    return copied


def bundle_app(app, game):
    sys.path.insert(0, str(ROOT / 'scripts'))
    from halopad_package import read_identity, sources_for
    plist = app / 'Contents' / 'Info.plist'
    resources = app / 'Contents' / 'Resources' if plist.is_file() else app
    identity = read_identity(resources / 'data')
    selected = sources_for(game, identity['stock_files'])
    destination = resources / 'bundled-game'
    if destination.exists():
        raise StockError('the app already contains bundled-game')
    for name, path in selected.items():
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
    return len(selected)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--game', type=Path)
    parser.add_argument('--reference', type=Path)
    parser.add_argument('--product-id-file', type=Path)
    parser.add_argument('--stage', action='store_true')
    parser.add_argument('--bundle-app', type=Path)
    parser.add_argument('--profile', type=Path, default=PROFILE_PATH)
    parser.add_argument('--stock-out', type=Path, default=STOCK_OUT)
    parser.add_argument('--reference-out', type=Path, default=REFERENCE_OUT)
    args = parser.parse_args()
    try:
        profile = json.loads(args.profile.read_text())
        if args.product_id_file:
            product_id_text(args.product_id_file)
            print('product-id file accepted')
        if args.stage:
            if not args.game or not args.reference or not args.product_id_file:
                raise StockError('installed stock needs the game directory, reference directory, and product-id file')
            copied = stage(args.game, args.reference, profile, args.stock_out, args.reference_out)
            print('installed stock accepted' + ('' if copied else ' (already staged)'))
        if args.bundle_app:
            count = bundle_app(args.bundle_app, args.game or STOCK_OUT)
            print(f'bundled-game files: {count}')
    except StockError as exc:
        print('installed stock rejected: ' + str(exc), file=sys.stderr)
        return 3
    return 0


if __name__ == '__main__':
    sys.exit(main())
