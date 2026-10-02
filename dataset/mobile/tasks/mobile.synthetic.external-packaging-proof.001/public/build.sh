#!/bin/sh
set -eu
node --check app.js
node --check geometry.js
mkdir -p dist
# dist may be a mounted output directory: never delete or rename it.
find dist -mindepth 1 -maxdepth 1 -exec rm -rf -- {} +
cp index.html app.js geometry.js style.css dist/
