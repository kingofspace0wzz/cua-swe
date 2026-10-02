#!/bin/sh
set -eu
for f in app.js engine.js boundary.js viewer.js; do node --input-type=module --check < "$f"; done
mkdir -p dist
for f in index.html style.css app.js engine.js boundary.js viewer.js LICENSE; do cp "$f" "dist/$f"; done
