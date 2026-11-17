#!/usr/bin/env python3
"""Export Screenpipe captures to the JSON format screenpipe_ingest.py reads.

Run this ON the Windows notebook where Screenpipe runs, not on the
Linux VM (the VM has no Screenpipe and nothing to capture). It only
reads Screenpipe's local data and writes one JSON file. Copy that file
to the VM (U 盘 / 局域网 / 其他本地方式，不要走云盘同步）and run:

  python3 screenpipe/screenpipe_ingest.py --input <导出的文件.json>

Two modes (both read-only):
  1. api (default): GET http://127.0.0.1:3030/search with
     content_type=audio and content_type=ocr. This is the official
     way; it never touches the live SQLite file.
  2. db: read a COPY of ~/.screenpipe/db.sqlite (copy the file first,
     never point it at the live database while Screenpipe is recording).
     Opens the copy with a read-only URI and fails closed if the
     expected columns are missing (Screenpipe's schema changes between
     versions; verified against the 2026-09-01 schema: frames.full_text
     and audio_transcriptions.transcription).

Only text is exported (screen text + audio transcriptions). No
screenshots, no audio files, no passwords. The export contains
everything on screen / everything said, so treat the file as private:
keep it local, delete it after ingest.

Usage (Windows, Screenpipe running):
  python export_from_screenpipe.py --out export-2026-11-17.json
  python export_from_screenpipe.py --out export-2026-11-17.json --since 2026-11-17 --until 2026-11-18
  python export_from_screenpipe.py --mode db --db-copy C:\\temp\\db.sqlite --out export.json
"""
import argparse
import json
import sqlite3
import sys
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

API_BASE = "http://127.0.0.1:3030"


def iso(value):
    if not value:
        return ""
    return str(value)


def api_search(content_type, since, until, limit=500):
    """Query the local Screenpipe REST API. Returns raw item dicts."""
    url = (f"{API_BASE}/search?content_type={content_type}"
           f"&limit={limit}&start_time={since}&end_time={until}")
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))


def items_from_api_payload(payload):
    """Pull the item list out of a /search response, tolerating shape drift.

    Known shapes: {"data": [...]} and {"content": {"items": [...]}}.
    Each item's text lives under content.text (screen) or
    content.transcription (audio). Raises if nothing recognisable.
    """
    if isinstance(payload, dict):
        if isinstance(payload.get("data"), list):
            return payload["data"]
        content = payload.get("content")
        if isinstance(content, dict) and isinstance(content.get("items"), list):
            return content["items"]
    raise RuntimeError(
        "unexpected /search response shape; top-level keys: "
        + ", ".join(sorted(payload.keys()) if isinstance(payload, dict) else []))


def record_from_api_item(item):
    """Map one API item to the export record format. Returns None to skip."""
    content = item.get("content") or item
    kind = (content.get("type") or item.get("type") or "").lower()
    if kind in ("audio", "transcription"):
        kind = "audio"
        text = content.get("transcription") or content.get("text") or ""
    else:
        kind = "screen"
        text = content.get("text") or content.get("transcription") or ""
    if not (text or "").strip():
        return None
    return {
        "kind": kind,
        "id": content.get("frame_id") or content.get("id") or item.get("id"),
        "timestamp": iso(content.get("timestamp") or item.get("timestamp")),
        "app": content.get("app_name"),
        "window": content.get("window_name"),
        "device": content.get("device"),
        "speaker": content.get("speaker_id"),
        "text": text,
    }


def export_via_api(since, until):
    records = []
    for content_type in ("audio", "ocr"):
        payload = api_search(content_type, since, until)
        for item in items_from_api_payload(payload):
            rec = record_from_api_item(item)
            if rec:
                records.append(rec)
    records.sort(key=lambda r: r.get("timestamp") or "")
    return records


def check_columns(conn, table, required):
    cols = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
    missing = [c for c in required if c not in cols]
    if missing:
        raise RuntimeError(
            f"table {table} is missing columns {missing} "
            f"(found: {sorted(cols)}). Screenpipe schema changed; "
            "check the installed version before continuing.")
    return cols


def export_via_db(db_copy, since, until):
    """Read a COPY of db.sqlite, read-only. Never use the live file."""
    uri = Path(db_copy).resolve().as_uri() + "?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    try:
        frame_cols = check_columns(
            conn, "frames",
            ["id", "timestamp", "app_name", "window_name"])
        audio_cols = check_columns(
            conn, "audio_transcriptions",
            ["id", "timestamp", "transcription"])
        records = []
        has_ocr_table = conn.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='table' AND name='ocr_text'").fetchone() is not None
        if "full_text" in frame_cols:
            rows = conn.execute(
                "SELECT id, timestamp, app_name, window_name, full_text "
                "FROM frames WHERE full_text IS NOT NULL "
                "AND TRIM(full_text) <> '' "
                "AND timestamp >= ? AND timestamp < ? ORDER BY timestamp",
                (since, until))
            for fid, ts, app, window, text in rows:
                records.append({"kind": "screen", "id": fid, "timestamp": iso(ts),
                                "app": app, "window": window, "device": None,
                                "speaker": None, "text": text})
        elif has_ocr_table:
            rows = conn.execute(
                "SELECT f.id, f.timestamp, f.app_name, f.window_name, o.text "
                "FROM frames f JOIN ocr_text o ON o.frame_id = f.id "
                "WHERE o.text IS NOT NULL AND TRIM(o.text) <> '' "
                "AND f.timestamp >= ? AND f.timestamp < ? ORDER BY f.timestamp",
                (since, until))
            for fid, ts, app, window, text in rows:
                records.append({"kind": "screen", "id": fid, "timestamp": iso(ts),
                                "app": app, "window": window, "device": None,
                                "speaker": None, "text": text})
        else:
            raise RuntimeError(
                "frames table has neither full_text nor an ocr_text table; "
                "schema changed, refusing to guess.")
        device_col = ("device" if "device" in audio_cols else None)
        speaker_col = ("speaker_id" if "speaker_id" in audio_cols else None)
        rows = conn.execute(
            f"SELECT id, timestamp, transcription"
            f"{', device' if device_col else ''}"
            f"{', speaker_id' if speaker_col else ''} "
            "FROM audio_transcriptions "
            "WHERE transcription IS NOT NULL AND TRIM(transcription) <> '' "
            "AND timestamp >= ? AND timestamp < ? ORDER BY timestamp",
            (since, until))
        for row in rows:
            rec = {"kind": "audio", "id": row[0], "timestamp": iso(row[1]),
                   "app": None, "window": None,
                   "device": row[3] if device_col else None,
                   "speaker": row[4] if speaker_col else None,
                   "text": row[2]}
            records.append(rec)
        records.sort(key=lambda r: r.get("timestamp") or "")
        return records
    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    parser.add_argument("--mode", choices=["api", "db"], default="api")
    parser.add_argument("--db-copy", default=None,
                        help="path to a COPY of db.sqlite (mode=db only)")
    parser.add_argument("--since", default=None,
                        help="RFC3339 start, default 24h ago")
    parser.add_argument("--until", default=None,
                        help="RFC3339 end, default now")
    args = parser.parse_args()
    now = datetime.now(timezone.utc)
    until = args.until or now.isoformat()
    since = args.since or (now - timedelta(hours=24)).isoformat()
    if args.mode == "db":
        if not args.db_copy:
            print("--mode db needs --db-copy <path to a COPY of db.sqlite>",
                  file=sys.stderr)
            return 2
        records = export_via_db(args.db_copy, since, until)
    else:
        records = export_via_api(since, until)
    export = {"exported_at": now.isoformat(), "source": "screenpipe",
              "since": since, "until": until, "records": records}
    Path(args.out).write_text(json.dumps(export, ensure_ascii=False, indent=2),
                              encoding="utf-8")
    print(json.dumps({"out": args.out, "mode": args.mode,
                      "records": len(records)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
