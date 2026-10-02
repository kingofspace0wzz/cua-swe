#!/bin/sh
set -eu
for f in app.js wallet.js provider.js viewer.js; do node --check "$f"; done
mkdir -p dist
find dist -mindepth 1 -maxdepth 1 -exec rm -rf {} +
cp index.html style.css app.js wallet.js provider.js viewer.js dist/
