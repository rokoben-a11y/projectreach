#!/usr/bin/env python3
"""Pack a private Custom Edition stock tree into an already-built unsigned shell.

The shell must already contain translated data/modules and data/core-identity.json.
This does not compile, sign, download, or print stock hashes or key material.
Game files stay out of the git index. The result is an unsigned IPA.
"""
import argparse
import hashlib
import json
import os
import plistlib
import shutil
import stat
import subprocess
import sys
import tempfile
import unicodedata
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUNDLE_ID = 'dev.halopad.HaloPad'
DENY_NAMES = {'product-key.txt', 'product-id.txt'}
DENY_SUFFIXES = {'.p12', '.pfx', '.mobileprovision', '.key', '.pem'}


class RepackError(Exception):
    pass


def fold(name):
    return unicodedata.normalize('NFC', name).casefold()


def allowed_private(path):
    """Tracked repository files cannot hold commercial game data or an output IPA."""
    path = path.resolve()
    try:
        rel = path.relative_to(ROOT)
    except ValueError:
        return True
    return subprocess.run(['git', '-C', str(ROOT), 'check-ignore', '-q', '--no-index', str(rel)]).returncode == 0


def info_plist(app):
    for candidate in (app / 'Info.plist', app / 'Contents' / 'Info.plist'):
        if candidate.is_file() and not candidate.is_symlink():
            return candidate
    raise RepackError('Info.plist is missing')


def resources_dir(app, plist):
    if plist.parent.name == 'Contents':
        return plist.parent / 'Resources'
    return app


def assert_regular_tree(root):
    if root.is_symlink() or not root.is_dir():
        raise RepackError('expected a real directory')
    for directory, dirs, files in os.walk(root, followlinks=False):
        for name in dirs + files:
            path = Path(directory) / name
            if path.is_symlink():
                raise RepackError('symlinks are not accepted')
            mode = path.lstat().st_mode
            if not (stat.S_ISREG(mode) or stat.S_ISDIR(mode)):
                raise RepackError('special files are not accepted')


def index_tree(root):
    found = {}
    for directory, dirs, files in os.walk(root, followlinks=False):
        dirs.sort()
        for name in files:
            path = Path(directory) / name
            relative = path.relative_to(root).as_posix()
            key = fold(relative)
            if key in found:
                raise RepackError('ambiguous stock path')
            found[key] = path
    return found


def digest(path):
    hashed = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            hashed.update(block)
    return hashed.hexdigest()


def stock_records(identity):
    records = identity.get('stock_files') if isinstance(identity, dict) else None
    if not isinstance(records, dict) or not records:
        raise RepackError('core identity has no stock inventory')
    for name, row in records.items():
        folded = fold(name)
        suffix = Path(name).suffix.lower()
        if folded in {fold(item) for item in DENY_NAMES} or suffix in DENY_SUFFIXES:
            raise RepackError('stock inventory names a key or signing file')
        if not isinstance(row, dict) or not isinstance(row.get('size'), int) or not isinstance(row.get('sha256'), str):
            raise RepackError('stock inventory is malformed')
        if len(row['sha256']) != 64:
            raise RepackError('stock inventory is malformed')
    return records


def stage_game(identity_path, game, destination):
    records = stock_records(json.loads(identity_path.read_text()))
    present = index_tree(game)
    missing = []
    rejected = []
    selected = []
    for name, row in sorted(records.items()):
        path = present.get(fold(name))
        if path is None:
            missing.append(name)
            continue
        if path.stat().st_size != row['size'] or digest(path) != row['sha256']:
            rejected.append(name)
            continue
        selected.append((name, path))
    if missing or rejected:
        shown = ', '.join((missing + rejected)[:8])
        raise RepackError('prebundled stock does not match this build (' + shown + ')')
    destination.mkdir(parents=True)
    for name, path in selected:
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
        target.chmod(0o644)
    return len(records), len(present) - len(selected)


def zip_app(app, ipa):
    if ipa.exists() or ipa.is_symlink():
        if ipa.is_symlink() or not ipa.is_file():
            raise RepackError('output IPA must be a regular file')
        ipa.unlink()
    partial = ipa.with_name(ipa.name + '.partial')
    try:
        with zipfile.ZipFile(partial, 'w') as archive:
            for directory, dirs, files in os.walk(app, followlinks=False):
                dirs.sort()
                for name in sorted(files):
                    path = Path(directory) / name
                    if path.is_symlink() or not stat.S_ISREG(path.lstat().st_mode):
                        raise RepackError('refusing to archive a symlink or special file')
                    relative = Path('Payload') / app.name / path.relative_to(app)
                    info = zipfile.ZipInfo(relative.as_posix())
                    info.compress_type = zipfile.ZIP_STORED
                    info.external_attr = (path.stat().st_mode & 0xFFFF) << 16
                    info.date_time = (1980, 1, 1, 0, 0, 0)
                    with archive.open(info, 'w') as dest, path.open('rb') as stream:
                        shutil.copyfileobj(stream, dest)
    except Exception:
        partial.unlink(missing_ok=True)
        raise
    partial.replace(ipa)


def repack(app, game, ipa):
    app, game, ipa = app.resolve(), game.resolve(), ipa.resolve()
    for path, label in ((app, 'app'), (game, 'game directory'), (ipa, 'IPA')):
        if not allowed_private(path):
            raise RepackError(label + ' must stay outside tracked source')
    assert_regular_tree(app)
    assert_regular_tree(game)
    plist_path = info_plist(app)
    info = plistlib.loads(plist_path.read_bytes())
    if info.get('CFBundleIdentifier') != BUNDLE_ID:
        raise RepackError('bundle id must stay ' + BUNDLE_ID)
    version = (info.get('CFBundleShortVersionString'), info.get('CFBundleVersion'))
    resources = resources_dir(app, plist_path)
    modules = resources / 'data' / 'modules'
    identity_path = resources / 'data' / 'core-identity.json'
    if not modules.is_dir() or not any(modules.rglob('image.bin')):
        raise RepackError('this app has no Custom Edition modules; raw game files cannot create the shell')
    if not identity_path.is_file():
        raise RepackError('this app has no signed core identity')
    stage = Path(tempfile.mkdtemp(prefix='halopad-repack-'))
    try:
        copied = stage / 'HaloPad.app'
        shutil.copytree(app, copied, symlinks=False)
        copied_resources = resources_dir(copied, info_plist(copied))
        count, skipped = stage_game(identity_path, game, copied_resources / 'bundled-game')
        copied_info = plistlib.loads(info_plist(copied).read_bytes())
        if (copied_info.get('CFBundleShortVersionString'), copied_info.get('CFBundleVersion')) != version:
            raise RepackError('app version changed during repack')
        if copied_info.get('CFBundleIdentifier') != BUNDLE_ID:
            raise RepackError('bundle id changed during repack')
        ipa.parent.mkdir(parents=True, exist_ok=True)
        zip_app(copied, ipa)
    finally:
        shutil.rmtree(stage, ignore_errors=True)
    return count, skipped


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--app', required=True, type=Path)
    parser.add_argument('--game', required=True, type=Path)
    parser.add_argument('--ipa', required=True, type=Path)
    args = parser.parse_args()
    try:
        count, skipped = repack(args.app, args.game, args.ipa)
    except RepackError as exc:
        print('prebundled repack failed: ' + str(exc), file=sys.stderr)
        return 3
    print(f'prebundled stock accepted: {count} files')
    if skipped:
        print(f'skipped non-stock files: {skipped}')
    print('unsigned ipa written: ' + args.ipa.name)
    print('not signed; Extended Virtual Addressing and Increased Memory Limit still have to be granted by the device profile')
    return 0


if __name__ == '__main__':
    sys.exit(main())
