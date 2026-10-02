#!/bin/sh
set -eu
for f in app.js adapter.js geometry.js model.js render.js viewer.js; do node --check "$f"; done
mkdir -p dist
for f in index.html style.css app.js adapter.js geometry.js model.js render.js viewer.js package.json; do cp "$f" "dist/$f"; done
