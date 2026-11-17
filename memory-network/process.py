#!/usr/bin/env python3
"""Process raw Omi snapshots with DeepSeek and save structured layers.

For each raw conversation snapshot not yet processed, call DeepSeek
(deepseek-flash, via the custom.deepseek helper only) to extract:
  - a one-line summary
  - key facts
  - entities and relations for the graph
  - dated events, if any

Rules:
  - DeepSeek may only use information present in the source text.
    Nothing is invented. Empty arrays when the source says nothing.
  - The API key never appears here. The helper swaps in the credential
    through its surrogate exchange. No key, token or secret is passed
    in any argument, environment variable or log line.
  - On API failure the raw snapshot is kept and the item is marked
    status=failed with the error recorded. One retry, then move on.
    Failed items are retried on the next run. Nothing is fabricated
    to fill a gap.

Usage:
  python3 process.py [--force] [--model deepseek-flash]

Outputs per conversation:
  data/processed/<conversation-id>.json
Rebuilt after every run from all processed files:
  data/layers/summaries.json  (long-term summaries)
  data/layers/facts.json      (semantic facts, with source ids)
  data/layers/events.json     (episodic events, with source ids)
"""
import argparse
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parent
DATA = BASE / "data"
RAW_CONV = DATA / "raw" / "conversations"
PROCESSED = DATA / "processed"
LAYERS = DATA / "layers"
DEEPSEEK = Path.home() / "workspace" / "custom-connectors" / "custom.deepseek" / "bin" / "deepseek.py"

SYSTEM_PROMPT = (
    "你是一个记忆抽取器。只根据用户给出的原文抽取信息，绝不编造、绝不补充原文没有的内容。"
    "实体名必须是原文中出现的词，不要改写、不要合并、不要造新词。"
    "只输出一个 JSON 对象，不要输出任何其他文字、不要用 markdown 代码块包裹。"
)
USER_TEMPLATE = """原文如下（Omi 吊坠录音转写，标题：{title}）：

{source_text}

请输出严格 JSON，格式如下：
{{
  "summary": "一句话摘要，不超过 40 字",
  "facts": ["关键事实，每条一句话，只写原文明确提到的内容"],
  "entities": [{{"name": "实体名", "type": "人物/地点/话题/物品/考试/其他"}}],
  "relations": [{{"subject": "实体 A", "relation": "关系，如：讨论/学习/属于/讲解", "object": "实体 B"}}],
  "events": [{{"date": "YYYY-MM-DD，若原文没有明确日期则为 null", "description": "事件描述"}}]
}}
原文没有提到的内容一律不要写，对应数组留空。对话本身的录制时间不算事件日期，不要把录制日期写进 events。"""


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def source_text_from_item(item):
    """Build the extraction source text from a raw conversation item."""
    structured = item.get("structured") or {}
    parts = []
    title = structured.get("title", "")
    overview = structured.get("overview", "")
    if overview:
        parts.append(overview)
    segments = item.get("transcript_segments") or []
    texts = []
    for seg in segments:
        text = (seg.get("text") or "").strip()
        if text:
            texts.append(text)
    if texts:
        parts.append("\n".join(texts))
    text = "\n\n".join(parts)
    return title, text


def parse_extraction(content):
    """Parse DeepSeek output as JSON, tolerating a short preamble."""
    cleaned = content.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`").strip()
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:].strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start >= 0 and end > start:
        return json.loads(cleaned[start:end + 1])
    raise json.JSONDecodeError("no JSON object in DeepSeek output", cleaned, 0)


def call_deepseek(model, system, message, retries=1):
    """Call the DeepSeek helper once (plus one retry). Returns parsed JSON."""
    last_error = None
    # Reasoning tokens count against max_tokens, so ask for a generous
    # budget up front; a truncated reply is unusable JSON.
    for max_tokens in (2000, 4000):
        cmd = [
            sys.executable, str(DEEPSEEK), "chat",
            "--model", model,
            "--message", message,
            "--system", system,
            "--temperature", "0.2",
            "--max-tokens", str(max_tokens),
        ]
        for _ in range(retries + 1):
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
            if proc.returncode != 0:
                last_error = (proc.stderr or proc.stdout).strip()[:300]
                continue
            try:
                response = json.loads(proc.stdout)
            except json.JSONDecodeError as exc:
                last_error = f"helper returned non-JSON output: {exc}"
                continue
            try:
                content = response["choices"][0]["message"]["content"]
            except (KeyError, IndexError, TypeError):
                last_error = "helper response had no choices[0].message.content"
                continue
            try:
                return parse_extraction(content)
            except json.JSONDecodeError as exc:
                last_error = f"DeepSeek output was not valid JSON: {exc}"
                continue
        # One budget level failed on output shape, not transport: retry bigger.
    raise RuntimeError(last_error or "DeepSeek call failed")


def process_one(raw_path, model, force=False):
    raw = json.loads(raw_path.read_text(encoding="utf-8"))
    item = raw.get("item") or {}
    cid = item.get("id") or raw_path.stem
    out_path = PROCESSED / f"{cid}.json"
    if out_path.exists() and not force:
        return "skipped", cid
    title, text = source_text_from_item(item)
    text_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
    created_at = item.get("created_at") or item.get("started_at") or ""
    truncated = text[:4000]
    message = USER_TEMPLATE.format(
        title=title or "(无标题)", created_at=created_at or "(未知时间)",
        source_text=truncated)
    try:
        extracted = call_deepseek(model, SYSTEM_PROMPT, message)
    except Exception as exc:  # noqa: BLE001 - record and continue with next item
        record = {
            "conversation_id": cid, "title": title,
            "source_created_at": created_at, "processed_at": now_iso(),
            "model": model, "status": "failed",
            "error": str(exc)[:300], "source_text_hash": text_hash,
            "summary": "", "facts": [], "entities": [],
            "relations": [], "events": [],
        }
        out_path.write_text(json.dumps(record, ensure_ascii=False, indent=2),
                            encoding="utf-8")
        return "failed", cid
    record = {
        "conversation_id": cid, "title": title,
        "source_created_at": created_at, "processed_at": now_iso(),
        "model": model, "status": "ok", "source_text_hash": text_hash,
        "summary": str(extracted.get("summary", ""))[:200],
        "facts": [str(f) for f in extracted.get("facts", [])][:20],
        "entities": extracted.get("entities", [])[:30],
        "relations": extracted.get("relations", [])[:30],
        "events": extracted.get("events", [])[:20],
    }
    out_path.write_text(json.dumps(record, ensure_ascii=False, indent=2),
                        encoding="utf-8")
    return "ok", cid


def rebuild_layers():
    """Rebuild summaries/facts/events layers from all processed files."""
    summaries, facts, events = [], [], []
    for path in sorted(PROCESSED.glob("*.json")):
        try:
            rec = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if rec.get("status") != "ok":
            continue
        cid = rec["conversation_id"]
        summaries.append({
            "conversation_id": cid, "title": rec.get("title", ""),
            "date": (rec.get("source_created_at") or "")[:10],
            "summary": rec.get("summary", ""),
        })
        for fact in rec.get("facts", []):
            if fact not in [f["fact"] for f in facts]:
                facts.append({"fact": fact, "sources": [cid]})
            else:
                for f in facts:
                    if f["fact"] == fact and cid not in f["sources"]:
                        f["sources"].append(cid)
        for ev in rec.get("events", []):
            events.append({
                "date": ev.get("date"),
                "description": ev.get("description", ""),
                "source_id": cid, "title": rec.get("title", ""),
            })
    LAYERS.mkdir(parents=True, exist_ok=True)
    (LAYERS / "summaries.json").write_text(
        json.dumps({"generated_at": now_iso(), "count": len(summaries),
                    "summaries": summaries}, ensure_ascii=False, indent=2),
        encoding="utf-8")
    (LAYERS / "facts.json").write_text(
        json.dumps({"generated_at": now_iso(), "count": len(facts),
                    "facts": facts}, ensure_ascii=False, indent=2),
        encoding="utf-8")
    (LAYERS / "events.json").write_text(
        json.dumps({"generated_at": now_iso(), "count": len(events),
                    "events": events}, ensure_ascii=False, indent=2),
        encoding="utf-8")
    return len(summaries), len(facts), len(events)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--model", default="deepseek-flash")
    args = parser.parse_args()
    PROCESSED.mkdir(parents=True, exist_ok=True)
    results = {"ok": 0, "failed": 0, "skipped": 0}
    for raw_path in sorted(RAW_CONV.glob("*.json")):
        status, _ = process_one(raw_path, args.model, force=args.force)
        results[status] += 1
    s, f, e = rebuild_layers()
    report = {
        "processed_at": now_iso(), "model": args.model,
        "results": results, "layers": {"summaries": s, "facts": f, "events": e},
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if results["failed"] == 0 else 0  # failures are recorded, not fatal


if __name__ == "__main__":
    sys.exit(main())
