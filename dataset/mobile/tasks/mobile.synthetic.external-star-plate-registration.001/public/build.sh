#!/bin/sh
set -eu
for f in app.js geometry.js raster.js integration.js guide.js; do node --check "$f"; done
mkdir -p dist
cp index.html style.css app.js geometry.js raster.js integration.js guide.js package.json dist/
