#!/bin/sh
set -eu
# The only protected public file: dependency-free build wrapper.
for f in *.js; do node --check "$f"; done
mkdir -p dist
cp -- *.html *.css *.js dist/
