#!/usr/bin/env python3
"""Build the entity graph and the timeline from processed items.

Reads data/processed/*.json (status ok only) and writes:
  data/graph.json    - nodes are entities, edges are relations,
                       every node and edge carries its source conversation ids
  data/timeline.json - chronological events from processed items

Nothing is invented here. A node or edge exists only if DeepSeek extracted
it from a real source text, and the source conversation id is kept on it.
Undated events are listed separately at the end of the timeline.
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parent
DATA = BASE / "data"
PROCESSED = DATA / "processed"


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def normalize(name):
    return " ".join(str(name).strip().split())


def main():
    nodes = {}
    edges = {}
    events = []
    for path in sorted(PROCESSED.glob("*.json")):
        try:
            rec = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if rec.get("status") != "ok":
            continue
        cid = rec["conversation_id"]
        for ent in rec.get("entities", []):
            name = normalize(ent.get("name", ""))
            if not name:
                continue
            node = nodes.setdefault(name, {
                "id": name, "label": name,
                "type": ent.get("type", "其他") or "其他", "sources": [],
            })
            if cid not in node["sources"]:
                node["sources"].append(cid)
        for rel in rec.get("relations", []):
            subj = normalize(rel.get("subject", ""))
            obj = normalize(rel.get("object", ""))
            relation = (rel.get("relation") or "").strip()
            if not subj or not obj or not relation:
                continue
            for name in (subj, obj):
                if name not in nodes:
                    nodes[name] = {"id": name, "label": name,
                                   "type": "其他", "sources": [cid]}
                elif cid not in nodes[name]["sources"]:
                    nodes[name]["sources"].append(cid)
            key = (subj, relation, obj)
            edge = edges.setdefault(key, {
                "source": subj, "target": obj, "relation": relation,
                "sources": [],
            })
            if cid not in edge["sources"]:
                edge["sources"].append(cid)
        for ev in rec.get("events", []):
            desc = (ev.get("description") or "").strip()
            if not desc:
                continue
            events.append({
                "date": ev.get("date"),
                "description": desc,
                "source_id": cid,
                "title": rec.get("title", ""),
                "source_date": (rec.get("source_created_at") or "")[:10],
            })
    dated = sorted(
        [e for e in events if e.get("date")],
        key=lambda e: (e["date"], e.get("source_date") or ""),
    )
    undated = sorted(
        [e for e in events if not e.get("date")],
        key=lambda e: (e.get("source_date") or "", e["description"]),
    )
    graph = {
        "generated_at": now_iso(),
        "node_count": len(nodes),
        "edge_count": len(edges),
        "nodes": sorted(nodes.values(), key=lambda n: n["id"]),
        "edges": sorted(edges.values(),
                        key=lambda e: (e["source"], e["relation"], e["target"])),
    }
    timeline = {
        "generated_at": now_iso(),
        "event_count": len(events),
        "events": dated + undated,
        "undated_count": len(undated),
    }
    (DATA / "graph.json").write_text(
        json.dumps(graph, ensure_ascii=False, indent=2), encoding="utf-8")
    (DATA / "timeline.json").write_text(
        json.dumps(timeline, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "generated_at": graph["generated_at"],
        "nodes": graph["node_count"], "edges": graph["edge_count"],
        "events": timeline["event_count"],
        "undated_events": timeline["undated_count"],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
