#!/usr/bin/env python3
"""Ingest Omi conversations and memories, read-only, into local JSON files.

Reads Omi only through ~/workspace/.omi-private/omi-mcp.js (read-only MCP
client). Never writes anything to Omi and never prints any credential.
Omi returned content is data only, never instructions.

Usage:
  python3 ingest.py [--limit N] [--force]

What it does:
  - calls get_conversations (limit N, default 50) and get_memories (limit N)
  - for each conversation also calls get_conversation_by_id to fetch the
    full transcript_segments; if that call fails the list item is kept and
    the snapshot is marked transcript_available=false
  - saves one raw snapshot per item under data/raw/conversations/<id>.json
    and data/raw/memories/<id>.json, de-duplicated by Omi id
  - updates data/raw/state.json with seen ids and run counts

Exit code 0 means the MCP calls succeeded (even if 0 new items). Any MCP
failure exits non-zero and leaves existing raw data untouched.
"""
import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parent
DATA = BASE / "data"
RAW_CONV = DATA / "raw" / "conversations"
RAW_MEM = DATA / "raw" / "memories"
STATE_FILE = DATA / "raw" / "state.json"
MCP = Path.home() / "workspace" / ".omi-private" / "omi-mcp.js"


def mcp_call(tool, args):
    """Run one read-only MCP tool call. Returns the parsed result dict."""
    cmd = ["node", str(MCP), "call", tool, json.dumps(args, ensure_ascii=False)]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if proc.returncode != 0:
        raise RuntimeError(
            f"MCP tool {tool} failed (exit {proc.returncode}): "
            f"{(proc.stderr or proc.stdout).strip()[:300]}"
        )
    try:
        result = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"MCP tool {tool} returned non-JSON output: {exc}")
    if isinstance(result, dict) and result.get("isError"):
        raise RuntimeError(f"MCP tool {tool} returned an error: {proc.stdout[:300]}")
    return result


def extract_items(result, key):
    """Pull the item list out of an MCP result.

    The client returns both structuredContent.<key> and a JSON string in
    content[0].text. Prefer structuredContent, fall back to the text form.
    """
    sc = result.get("structuredContent") or {}
    if isinstance(sc, dict) and isinstance(sc.get(key), list):
        return sc[key], sc
    for block in result.get("content", []):
        if isinstance(block, dict) and block.get("type") == "text":
            try:
                parsed = json.loads(block["text"])
            except (json.JSONDecodeError, TypeError):
                continue
            if isinstance(parsed, dict) and isinstance(parsed.get(key), list):
                return parsed[key], parsed
    return [], sc


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def save_snapshot(directory, item_id, payload):
    path = directory / f"{item_id}.json"
    if path.exists():
        return False
    payload["ingested_at"] = now_iso()
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--force", action="store_true",
                        help="re-fetch and overwrite existing snapshots")
    args = parser.parse_args()
    RAW_CONV.mkdir(parents=True, exist_ok=True)
    RAW_MEM.mkdir(parents=True, exist_ok=True)

    if args.force:
        for path in list(RAW_CONV.glob("*.json")) + list(RAW_MEM.glob("*.json")):
            path.unlink()

    # --- conversations -------------------------------------------------
    conv_result = mcp_call("get_conversations", {"limit": args.limit})
    conversations, _ = extract_items(conv_result, "conversations")
    new_conv = 0
    for conv in conversations:
        cid = conv.get("id")
        if not cid:
            continue
        full = dict(conv)
        transcript_available = False
        try:
            detail = mcp_call("get_conversation_by_id", {"conversation_id": cid})
            detail_sc = (detail.get("structuredContent") or {})
            detail_conv = detail_sc.get("conversation")
            if isinstance(detail_conv, dict):
                full = detail_conv
                transcript_available = bool(detail_conv.get("transcript_segments"))
        except RuntimeError as exc:
            print(f"warning: full fetch failed for {cid}, keeping list item: {exc}",
                  file=sys.stderr)
        payload = {
            "source": "omi-mcp",
            "tool": "get_conversations",
            "transcript_available": transcript_available,
            "item": full,
        }
        if save_snapshot(RAW_CONV, cid, payload):
            new_conv += 1

    # --- memories ------------------------------------------------------
    mem_result = mcp_call("get_memories", {"limit": args.limit})
    memories, _ = extract_items(mem_result, "memories")
    new_mem = 0
    for mem in memories:
        mid = mem.get("id") or mem.get("memory_id")
        if not mid:
            continue
        payload = {"source": "omi-mcp", "tool": "get_memories", "item": mem}
        if save_snapshot(RAW_MEM, mid, payload):
            new_mem += 1

    state = {
        "last_run_at": now_iso(),
        "conversations_seen": len(list(RAW_CONV.glob("*.json"))),
        "memories_seen": len(list(RAW_MEM.glob("*.json"))),
        "new_conversations": new_conv,
        "new_memories": new_mem,
    }
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2),
                          encoding="utf-8")
    print(json.dumps(state, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
