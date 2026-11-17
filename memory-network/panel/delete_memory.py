#!/usr/bin/env python3
"""Delete one Omi conversation from the local memory network.

This is the safe companion to the panel's delete button. The panel
itself never deletes files; run this on the computer instead.

Usage:
  python3 panel/delete_memory.py <conversation_id> [--yes]

It deletes:
  data/raw/conversations/<id>.json
  data/processed/<id>.json
then rebuilds the layers, graph and timeline and regenerates
the panel (panel.html). Without --yes it only prints what it
would delete and exits.
"""
import pathlib
import subprocess
import sys

BASE = pathlib.Path(__file__).resolve().parent.parent

def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    yes = "--yes" in sys.argv
    if len(args) != 1:
        print("Usage: python3 panel/delete_memory.py <conversation_id> [--yes]")
        sys.exit(2)
    cid = args[0]
    raw = BASE / "data" / "raw" / "conversations" / f"{cid}.json"
    proc = BASE / "data" / "processed" / f"{cid}.json"
    targets = [p for p in (raw, proc) if p.exists()]
    if not targets:
        print(f"No local files found for {cid}; nothing deleted.")
        sys.exit(0)
    print("Will delete:")
    for p in targets:
        print(f"  {p}")
    if not yes:
        print("Run again with --yes to confirm.")
        sys.exit(0)
    for p in targets:
        p.unlink()
    print("Deleted. Rebuilding layers, graph and timeline...")
    subprocess.run([sys.executable, "process.py"], cwd=BASE, check=True)
    subprocess.run([sys.executable, "build_derived.py"], cwd=BASE, check=True)
    subprocess.run([sys.executable, "panel/build_panel.py"], cwd=BASE, check=True)
    print("Done. Reload panel.html to see the updated counts.")

if __name__ == "__main__":
    main()
