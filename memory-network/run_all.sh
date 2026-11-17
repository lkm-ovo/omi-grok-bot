#!/bin/bash
# Run the full memory-network pipeline, step by step: ingest, process, build.
# Each step is safe to run again. Ingest skips items already saved,
# process skips items already processed, builders rebuild from processed files.
set -u
cd "$(dirname "$0")"
echo "== ingest =="
python3 ingest.py
echo "== process =="
python3 process.py
echo "== build graph + timeline =="
python3 build_derived.py
echo "done."
