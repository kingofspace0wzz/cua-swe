#!/bin/sh
set -eu
for file in app.js geometry.js registration.js panorama.js; do node --check "$file"; done
mkdir -p dist
cp index.html style.css app.js geometry.js registration.js panorama.js dist/
