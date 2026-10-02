#!/bin/sh
set -eu
for f in app.js math.js performance.js renderer.js viewer.js; do node --check "$f"; done
mkdir -p dist
cp index.html style.css app.js math.js performance.js renderer.js viewer.js dist/
