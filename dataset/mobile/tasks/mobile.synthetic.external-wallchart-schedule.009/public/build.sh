#!/bin/sh
set -eu
for f in app.mjs schedule.mjs render.mjs integration.mjs; do node --check "$f"; done
mkdir -p dist
cp index.html style.css app.mjs schedule.mjs render.mjs integration.mjs guide.html dist/
