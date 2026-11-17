#!/usr/bin/env python3
"""Ingest Screenpipe captures into the memory network (source adapter).

Screenpipe runs on lkm's Windows notebook (his main computer), not on
this Linux VM. This script does NOT talk to Screenpipe, does NOT record
anything and does NOT install anything. It only reads a JSON export file
(produced on the Windows notebook by screenpipe/export_from_screenpipe.py
or by hand, see screenpipe/README.md) and converts each capture session
into the same raw-snapshot envelope that process.py already understands:

  data/raw/conversations/<screenpipe-id>.json
  {"source": "screenpipe", "tool": "screenpipe_ingest",
   "transcript_available": true, "item": {...}, "ingested_at": ...}

The item has exactly the fields process.py reads: id, created_at /
started_at / finished_at, structured.title / structured.overview and
transcript_segments[].text. So the existing pipeline needs no change:
process.py extracts summaries/facts/events with DeepSeek and
build_derived.py rebuilds the graph and timeline, with the Screenpipe
source id kept on every fact, node, edge and event.

Source ids are stable hashes of the session content, so re-running this
script on the same export adds 0 new files (de-duplication by id, like
the Omi ingest). Deleting a Screenpipe session works exactly like
deleting an Omi conversation: panel/delete_memory.py <id> --yes.

Export file format (JSON):
  {"exported_at": "RFC3339", "source": "screenpipe" | "screenpipe-sample",
   "records": [
     {"kind": "audio" | "screen", "id": <int|str>, "timestamp": "RFC3339",
      "app": "Godot" | null, "window": "..." | null,
      "device": "microphone" | null, "speaker": "..." | null,
      "text": "..."}]}

Grouping into sessions (one raw snapshot per session):
  - audio: contiguous chunks from the microphone / system audio, split
    when the gap between chunks exceeds 10 minutes or the text exceeds
    ~3500 characters (process.py truncates source text at 4000 chars).
  - screen: frames from the same app + window on the same calendar day,
    consecutive duplicate lines removed, split at ~3500 characters.

Usage:
  python3 screenpipe/screenpipe_ingest.py --input screenpipe/sample_export.json
  python3 screenpipe/screenpipe_ingest.py --input /path/to/export.json [--since 2026-11-01]
"""
import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
RAW_CONV = BASE / "data" / "raw" / "conversations"

AUDIO_GAP_SECONDS = 600
MAX_SESSION_CHARS = 3500


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def parse_ts(value):
    """Parse an RFC3339 timestamp; returns an aware datetime or None."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def session_id(prefix, kind, group_key, text):
    digest = hashlib.sha1(
        f"{kind}|{group_key}|{text}".encode("utf-8")).hexdigest()[:12]
    return f"{prefix}-{kind}-{digest}"


def make_item(sid, source, title, overview, segments, first_ts, last_ts):
    """Build the item in the shape process.py's source_text_from_item reads."""
    return {
        "id": sid,
        "created_at": first_ts.isoformat() if first_ts else "",
        "started_at": first_ts.isoformat() if first_ts else "",
        "finished_at": last_ts.isoformat() if last_ts else "",
        "language": "zh-CN",
        "source": source,
        "structured": {
            "title": title,
            "overview": overview,
            "category": "screenpipe",
        },
        "transcript_segments": segments,
    }


def segments_for(chunks, start_ts):
    """Turn text chunks into transcript segments with offsets in seconds."""
    segments = []
    for i, (text, speaker, ts, _device) in enumerate(chunks):
        offset = int((ts - start_ts).total_seconds()) if ts and start_ts else i * 30
        segments.append({
            "id": f"seg-{i}",
            "text": text,
            "speaker_id": speaker,
            "is_user": False,
            "start": max(offset, 0),
            "end": max(offset, 0) + 30,
        })
    return segments


def group_audio(records, prefix):
    """Group audio chunks into sessions. Returns a list of session dicts."""
    sessions, current, current_chars = [], [], 0
    for rec in records:
        text = (rec.get("text") or "").strip()
        if not text:
            continue
        ts = parse_ts(rec.get("timestamp"))
        gap = None
        if current and ts and current[-1][2]:
            gap = (ts - current[-1][2]).total_seconds()
        if current and ((gap is not None and gap > AUDIO_GAP_SECONDS)
                        or current_chars + len(text) > MAX_SESSION_CHARS):
            sessions.append(current)
            current, current_chars = [], 0
        current.append((text, rec.get("speaker"), ts, rec.get("device")))
        current_chars += len(text)
    if current:
        sessions.append(current)
    out = []
    for chunks in sessions:
        first_ts, last_ts = chunks[0][2], chunks[-1][2]
        date = first_ts.date().isoformat() if first_ts else "未知日期"
        hhmm = (lambda t: t.strftime("%H:%M") if t else "??:??")
        title = (f"Screenpipe 音频转写（{date} {hhmm(first_ts)}–{hhmm(last_ts)}）")
        device = chunks[0][3] or "系统音频/麦克风"
        overview = (f"Screenpipe 音频转写，设备 {device}，本地 Whisper 转写；{date} "
                    f"{hhmm(first_ts)}–{hhmm(last_ts)}。以下为转写文字。")
        if prefix == "screenpipe-sample":
            title = "示例 · " + title
            overview = "注意：这是示例导出，不是真实捕捉。" + overview
        text_all = "\n".join(c[0] for c in chunks)
        key = (first_ts.isoformat() if first_ts else date)
        sid = session_id(prefix, "audio", key, text_all)
        out.append((sid, title, overview, chunks, first_ts, last_ts))
    return out


def group_screen(records, prefix):
    """Group screen frames by (app, window, day). Returns session dicts."""
    groups = {}
    for rec in records:
        text = (rec.get("text") or "").strip()
        if not text:
            continue
        ts = parse_ts(rec.get("timestamp"))
        date = ts.date().isoformat() if ts else "未知日期"
        key = (rec.get("app") or "未知应用", rec.get("window") or "", date)
        groups.setdefault(key, []).append((text, None, ts, None))
    out = []
    for (app, window, date), chunks in sorted(groups.items()):
        # De-duplicate consecutive identical lines, keep order.
        seen, deduped = set(), []
        for text, speaker, ts, device in chunks:
            lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
            kept = [ln for ln in lines if ln not in seen]
            for ln in kept:
                seen.add(ln)
            if kept:
                deduped.append(("\n".join(kept), speaker, ts, device))
        # Split oversized groups into parts of ~MAX_SESSION_CHARS.
        parts, current, chars = [], [], 0
        for text, speaker, ts, device in deduped:
            if current and chars + len(text) > MAX_SESSION_CHARS:
                parts.append(current)
                current, chars = [], 0
            current.append((text, speaker, ts, device))
            chars += len(text)
        if current:
            parts.append(current)
        for part_no, part in enumerate(parts, start=1):
            first_ts, last_ts = part[0][2], part[-1][2]
            title = f"Screenpipe 屏幕捕捉 · {app}（{date}）"
            if len(parts) > 1:
                title += f"（第 {part_no} 部分）"
            overview = (f"Screenpipe 屏幕捕捉：应用 {app}，窗口 {window or '（未记录）'}；"
                        f"{date}。以下为屏幕文字（无障碍树，OCR 兜底）。")
            if prefix == "screenpipe-sample":
                title = "示例 · " + title
                overview = "注意：这是示例导出，不是真实捕捉。" + overview
            text_all = "\n".join(c[0] for c in part)
            key = f"{app}|{window}|{date}|part{part_no}"
            sid = session_id(prefix, "screen", key, text_all)
            out.append((sid, title, overview, part, first_ts, last_ts))
    return out


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True,
                        help="Screenpipe JSON export file (see README.md)")
    parser.add_argument("--since", default=None,
                        help="only records on/after YYYY-MM-DD")
    args = parser.parse_args()
    path = Path(args.input)
    if not path.exists():
        print(f"input file not found: {path}", file=sys.stderr)
        return 2
    export = json.loads(path.read_text(encoding="utf-8"))
    prefix = ("screenpipe-sample" if export.get("source") == "screenpipe-sample"
              else "screenpipe")
    records = export.get("records") or []
    since = None
    if args.since:
        since = datetime.fromisoformat(args.since).date()
    kept = []
    for rec in records:
        ts = parse_ts(rec.get("timestamp"))
        if since and ts and ts.date() < since:
            continue
        kept.append(rec)
    audio = sorted([r for r in kept if r.get("kind") == "audio"],
                   key=lambda r: r.get("timestamp") or "")
    screen = sorted([r for r in kept if r.get("kind") == "screen"],
                    key=lambda r: r.get("timestamp") or "")
    sessions = group_audio(audio, prefix) + group_screen(screen, prefix)
    RAW_CONV.mkdir(parents=True, exist_ok=True)
    new, skipped, ids = 0, 0, []
    for sid, title, overview, chunks, first_ts, last_ts in sessions:
        out_path = RAW_CONV / f"{sid}.json"
        if out_path.exists():
            skipped += 1
            continue
        item = make_item(sid, prefix, title, overview,
                         segments_for(chunks, first_ts), first_ts, last_ts)
        payload = {
            "source": prefix,
            "tool": "screenpipe_ingest",
            "transcript_available": True,
            "item": item,
            "ingested_at": now_iso(),
        }
        out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                            encoding="utf-8")
        new += 1
        ids.append(sid)
    print(json.dumps({
        "input": str(path), "source": prefix,
        "records_read": len(records), "records_used": len(kept),
        "sessions": len(sessions), "new": new, "skipped": skipped,
        "new_ids": ids,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
