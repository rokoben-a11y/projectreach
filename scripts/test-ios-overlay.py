#!/usr/bin/env python3
"""Run the real overlay's timer/input handlers on a booted project Simulator.

The test captures the host boundary, without loading game data, presenting a window,
or sending input to a running app. Safe alongside a preview; does not boot or stop devices.
"""
import argparse
import datetime
import hashlib
import json
import os
import pathlib
import subprocess

ROOT = pathlib.Path(__file__).resolve().parents[1]


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--device', default='E129A00F-D338-4FDC-8AE8-BB243E9BA61B')
    args = ap.parse_args()
    now = datetime.datetime.now(datetime.timezone.utc)
    evidence = ROOT / 'docs/artifacts' / now.strftime('%Y-%m-%d') / 'G9' / ('overlay-' + now.strftime('%Y%m%dT%H%M%SZ'))
    evidence.mkdir(parents=True)
    sdk = subprocess.check_output(['xcrun', '--sdk', 'iphonesimulator', '--show-sdk-path'], text=True).strip()
    sources = [ROOT / 'tests/halo_overlay_test.m', ROOT / 'port/ios/HaloPadOverlay.m']
    exe = evidence / 'overlay-test'
    cmd = ['xcrun', 'clang', '-target', 'arm64-apple-ios17.0-simulator', '-isysroot', sdk,
           '-fobjc-arc', '-O1', '-I/opt/homebrew/include', *map(str, sources), '-framework', 'UIKit', '-framework', 'Foundation',
           '-framework', 'GameController', '-framework', 'QuartzCore', '-framework', 'CoreGraphics',
           # the overlay logs through the app's weak halopad_log (HP_LOG); this harness has none
           '-Wl,-U,_halopad_log', '-o', str(exe)]
    build = subprocess.run(cmd, capture_output=True, text=True)
    (evidence / 'build.txt').write_text(build.stdout + build.stderr)
    build.check_returncode()
    env = dict(os.environ, SIMCTL_CHILD_HALOPAD_OVERLAY_RENDER_DIR=str(evidence))
    result = subprocess.run(['xcrun', 'simctl', 'spawn', args.device, str(exe)],
                            env=env, capture_output=True, text=True, timeout=30)
    output = result.stdout + result.stderr
    (evidence / 'run.txt').write_text(output)
    inputs = sources + [ROOT / 'port/ios/HaloPadOverlay.h', ROOT / 'port/shared/hp_control_layout.h',
                        ROOT / 'port/runtime/halopad_input.h',
                        ROOT / 'port/xbox/xg_overlay_input.h', ROOT / 'port/xbox/xg_touch_input.h']
    (evidence / 'result.json').write_text(json.dumps({
        'device': args.device, 'exit': result.returncode, 'build_command': cmd,
        'sha256': {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs},
        'executable_sha256': hashlib.sha256(exe.read_bytes()).hexdigest(),
    }, indent=2) + '\n')
    print(output, end='')
    print('evidence', evidence.relative_to(ROOT))
    return result.returncode


if __name__ == '__main__':
    raise SystemExit(main())
