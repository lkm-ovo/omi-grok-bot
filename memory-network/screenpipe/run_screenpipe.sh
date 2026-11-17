#!/bin/bash
# Screenpipe pipeline: ingest an export, then run the existing pipeline.
# Safe to run again: ingest skips sessions already saved, process skips
# items already processed, builders rebuild from processed files.
#
#   bash screenpipe/run_screenpipe.sh                     # sample export
#   bash screenpipe/run_screenpipe.sh export-2026-11-17.json
set -u
cd "$(dirname "$0")/.."
INPUT="${1:-screenpipe/sample_export.json}"
echo "== screenpipe ingest: $INPUT =="
python3 screenpipe/screenpipe_ingest.py --input "$INPUT"
echo "== process (DeepSeek) =="
python3 process.py
echo "== build graph + timeline =="
python3 build_derived.py
echo "== rebuild panel =="
python3 panel/build_panel.py
echo "done."
