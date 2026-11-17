#!/bin/bash
# Serve the memory network locally so the panel loads live JSON files.
# The panel also works by double-clicking panel.html (it falls back
# to an embedded snapshot), but this server is the way to see fresh
# data without rebuilding the panel.
# Usage: bash panel/serve.sh
# Then open: http://localhost:8321/panel/panel.html
set -e
cd "$(dirname "$0")/.."
echo "Serving http://localhost:8321/panel/panel.html (Ctrl-C to stop)"
python3 -m http.server 8321
