#!/bin/sh
set -eu
for f in app.js engine.js board.js report.js; do node --input-type=module --check < "$f"; done
mkdir -p dist
for f in index.html style.css app.js engine.js board.js report.js; do cp "$f" "dist/$f"; done
