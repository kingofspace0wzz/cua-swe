#!/bin/sh
set -eu
# Keep the mounted output directory; replace only this application's files.
node --check app.js
node --check routing.js
mkdir -p dist
cp index.html app.js routing.js style.css dist/
