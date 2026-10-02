#!/usr/bin/env python3
"""Write a Mobile runtime configuration from a local Python/Chromium installation."""
import argparse
import json
from pathlib import Path
import shutil
import sys


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, default=Path('mobile-runtime-config.local.json'))
    p.add_argument('--output-root', type=Path, default=Path('artifacts/mobile'))
    p.add_argument('--browsers', type=Path, default=Path.home() / '.cache/ms-playwright')
    p.add_argument('--bwrap', type=Path, default=Path(shutil.which('bwrap') or '/usr/bin/bwrap'))
    args = p.parse_args()
    if sys.prefix == sys.base_prefix:
        p.error('run from the virtual environment used for evaluation')
    if not args.browsers.is_dir() or not args.bwrap.is_file():
        p.error('install Playwright Chromium and bubblewrap first')
    config = {'output_root': str(args.output_root.resolve()),
              'python': str(Path(sys.executable).absolute()), 'venv': sys.prefix,
              'browsers': str(args.browsers.resolve()), 'bwrap': str(args.bwrap.resolve()),
              'browser_bwrap': str(args.bwrap.resolve())}
    with args.output.open('x') as f:
        json.dump(config, f, indent=2); f.write('\n')
    print(args.output.resolve())


if __name__ == '__main__':
    main()
