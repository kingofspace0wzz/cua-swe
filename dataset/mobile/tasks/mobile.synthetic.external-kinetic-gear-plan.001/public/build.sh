#!/bin/sh
set -eu
node --check app.mjs
node --check model.mjs
node --check plan.mjs
node --check viewer.mjs
mkdir -p dist
cp index.html style.css app.mjs model.mjs plan.mjs viewer.mjs help.json LICENSE dist/
