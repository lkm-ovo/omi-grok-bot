#!/usr/bin/env python3
"""Regenerate panel.html from the real data files.

Reads ../data/graph.json, ../data/timeline.json,
../data/layers/summaries.json, facts.json, events.json,
validates counts, and writes panel.html with the data embedded
so double-clicking the file works (file:// fetch is blocked
in most browsers). When served over http, the panel also tries
to fetch the live JSON files first and falls back to the
embedded snapshot.

Run after every run_all.sh:
  python3 panel/build_panel.py
"""
import json
import pathlib
import sys

BASE = pathlib.Path(__file__).resolve().parent.parent
DATA = BASE / "data"

def load(name):
    p = DATA / name
    with open(p, encoding="utf-8") as f:
        return json.load(f)

def main():
    graph = load("graph.json")
    timeline = load("timeline.json")
    summaries = load("layers/summaries.json")
    facts = load("layers/facts.json")
    events = load("layers/events.json")

    # Validate against the header counts in the files.
    assert len(graph["nodes"]) == graph["node_count"] == 22, graph["node_count"]
    assert len(graph["edges"]) == graph["edge_count"] == 14, graph["edge_count"]
    assert summaries["count"] == len(summaries["summaries"]) == 2
    assert facts["count"] == len(facts["facts"]) == 11
    assert events["count"] == len(events["events"]) == 4
    assert timeline["event_count"] == len(timeline["events"]) == 4

    embedded = {
        "graph": graph,
        "timeline": timeline,
        "summaries": summaries,
        "facts": facts,
        "events": events,
    }
    embedded_json = json.dumps(embedded, ensure_ascii=False)

    html = TEMPLATE.replace("__EMBEDDED_JSON__", embedded_json)
    # Safety: the generated page must not contain a secret.
    for needle in ("sk-", "omi_mcp_"):
        if needle in html:
            print(f"ERROR: generated HTML contains {needle!r}", file=sys.stderr)
            sys.exit(1)

    out = pathlib.Path(__file__).resolve().parent / "panel.html"
    out.write_text(html, encoding="utf-8")
    print(f"Wrote {out}")
    print("counts: summaries=2 facts=11 events=4 nodes=22 edges=14")

TEMPLATE = r"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Omi 记忆网络 · 可视化面板</title>
<style>
  * { box-sizing: border-box; }
  body { font-family: -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif; margin: 0; background: #f6f7f9; color: #222; }
  header { background: #1a1a2e; color: #fff; padding: 18px 22px; }
  header h1 { margin: 0 0 6px; font-size: 20px; }
  header p { margin: 2px 0; color: #c9c9d6; font-size: 13px; }
  .wrap { max-width: 1020px; margin: 0 auto; padding: 16px; }
  .counts { display: flex; flex-wrap: wrap; gap: 8px; margin: 12px 0; }
  .chip { background: #fff; border: 1px solid #ddd; border-radius: 999px; padding: 6px 12px; font-size: 13px; }
  .searchbar { display: flex; gap: 8px; margin: 12px 0; }
  .searchbar input { flex: 1; padding: 10px 12px; font-size: 15px; border: 1px solid #ccc; border-radius: 8px; }
  .searchbar button { padding: 10px 16px; font-size: 14px; border: 1px solid #ccc; background: #fff; border-radius: 8px; cursor: pointer; }
  .tabs { display: flex; gap: 6px; flex-wrap: wrap; margin: 12px 0; }
  .tabs button { padding: 9px 14px; font-size: 14px; border: 1px solid #ccc; background: #fff; border-radius: 8px; cursor: pointer; }
  .tabs button.active { background: #1a1a2e; color: #fff; border-color: #1a1a2e; }
  section { display: none; background: #fff; border: 1px solid #e2e2e2; border-radius: 12px; padding: 16px; margin-bottom: 16px; }
  section.active { display: block; }
  h2 { margin: 0 0 10px; font-size: 17px; }
  .hint { color: #666; font-size: 13px; line-height: 1.6; }
  .card { border: 1px solid #e8e8e8; border-radius: 10px; padding: 12px; margin: 10px 0; background: #fff; }
  .card .meta { color: #777; font-size: 12px; margin-top: 6px; word-break: break-all; }
  .del { float: right; border: 1px solid #e0a0a0; color: #a33; background: #fff; border-radius: 6px; padding: 4px 9px; cursor: pointer; font-size: 12px; }
  .delbox { background: #fff7e6; border: 1px solid #f0c36d; border-radius: 8px; padding: 10px; margin-top: 8px; font-size: 13px; line-height: 1.7; white-space: pre-wrap; word-break: break-all; }
  mark { background: #ffe08a; padding: 0 1px; }
  svg text { font-size: 12px; }
  .node { cursor: pointer; }
  .node circle { stroke: #fff; stroke-width: 2; }
  .legend { font-size: 13px; color: #555; }
  .detail { background: #eef2ff; border: 1px solid #c7d2fe; border-radius: 10px; padding: 12px; margin-top: 12px; }
  .hidden { display: none !important; }
  .empty { color: #888; padding: 14px 0; }
  footer { color: #888; font-size: 12px; text-align: center; padding: 18px; line-height: 1.7; }
  code { background: #f0f0f0; padding: 1px 5px; border-radius: 4px; }
</style>
</head>
<body>
<header>
  <h1>Omi 记忆网络 · 可视化面板</h1>
  <p>全部数据只存在本机，不联网，不调用 DeepSeek，不调用 Omi。面板只读，不会改你的记忆。</p>
  <p id="generated"></p>
</header>
<div class="wrap">
  <div class="counts" id="counts"></div>
  <div class="searchbar">
    <input id="q" type="search" placeholder="搜索摘要、事实、事件……（例如：精读 / 翻译 / 第22题）">
    <button id="clearBtn" type="button">清空</button>
  </div>
  <p class="hint" id="searchInfo"></p>
  <div class="tabs" role="tablist">
    <button data-tab="graph" class="active" type="button">图谱</button>
    <button data-tab="timeline" type="button">时间线</button>
    <button data-tab="summaries" type="button">摘要</button>
    <button data-tab="facts" type="button">事实</button>
    <button data-tab="events" type="button">事件</button>
  </div>

  <section id="tab-graph" class="active">
    <h2>图谱 <span class="legend" id="graphMeta"></span></h2>
    <p class="hint">点击一个节点，下面会显示它的类型、来源对话、相连的关系，以及提到它的事实。颜色：话题=蓝，考试=橙，地点=绿，其他=灰。</p>
    <svg id="graphSvg" width="100%" viewBox="0 0 960 560" role="img" aria-label="实体关系图"></svg>
    <div id="nodeDetail"></div>
    <h3>关系列表</h3>
    <div id="edgeList"></div>
  </section>

  <section id="tab-timeline">
    <h2>时间线</h2>
    <p class="hint">有日期的事件按日期排在前面，没有明确日期的事件排在最后。现在 4 个事件都没有明确日期，所以都在“未注明日期”里。</p>
    <div id="timelineList"></div>
  </section>

  <section id="tab-summaries">
    <h2>摘要</h2>
    <div id="summaryList"></div>
  </section>

  <section id="tab-facts">
    <h2>事实</h2>
    <div id="factList"></div>
  </section>

  <section id="tab-events">
    <h2>事件</h2>
    <div id="eventList"></div>
  </section>

  <section id="tab-help">
    <h2>删除说明</h2>
    <p class="hint">面板本身不直接删文件，这样才安全。想删一段记忆，按下面两步在电脑上操作。</p>
  </section>
</div>
<footer>本地面板 · 数据来源：~/workspace/omi-memory-network/data/ · 刷新方法见同目录 PANEL_README.md</footer>

<script>
window.__EMBEDDED__ = __EMBEDDED_JSON__;

const TYPE_COLOR = {"话题": "#2563eb", "考试": "#ea7c28", "地点": "#16a34a", "其他": "#9ca3af"};
const $ = (s) => document.querySelector(s);
const $$ = (s) => Array.from(document.querySelectorAll(s));

function esc(s) {
  return String(s == null ? "" : s).replace(/[&<>"']/g, (c) => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
}
function highlight(text, q) {
  const t = esc(text);
  if (!q) return t;
  const qe = q.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  return t.replace(new RegExp("(" + qe + ")", "gi"), "<mark>$1</mark>");
}
function shortId(id) { return id ? String(id).slice(0, 8) : ""; }

function deleteBox(kind, sourceId, label) {
  const file = "data/raw/conversations/" + sourceId + ".json";
  const proc = "data/processed/" + sourceId + ".json";
  return "<div class='delbox'>删除“" + esc(label) + "”的办法（面板不直接删文件）：\n"
    + "1. 在电脑上删除这两个文件：\n   " + esc(file) + "\n   " + esc(proc) + "\n"
    + "2. 再跑一次处理，重建图谱和时间线：\n   cd ~/workspace/omi-memory-network\n   python3 process.py\n   python3 build_derived.py\n   python3 panel/build_panel.py\n"
    + "也可以用助手脚本（先看清它要删的文件，确认后再跑）：\n   python3 panel/delete_memory.py " + esc(sourceId) + " --yes\n"
    + "删完后刷新本页面，数字会跟着变。</div>";
}
function bindDeleteButtons(root) {
  root.querySelectorAll("[data-del]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const box = btn.parentElement.querySelector(".delbox-slot");
      const kind = btn.getAttribute("data-del");
      const sid = btn.getAttribute("data-sid");
      const label = btn.getAttribute("data-label") || kind;
      if (box.innerHTML) { box.innerHTML = ""; return; }
      box.innerHTML = deleteBox(kind, sid, label);
    });
  });
}

let DATA = window.__EMBEDDED__;
let currentTab = "graph";

async function tryFetchLive() {
  // Served over http: prefer the live files. On file:// this throws and
  // the embedded snapshot below is used instead.
  try {
    const [g, t, s, f, e] = await Promise.all([
      fetch("../data/graph.json").then((r) => { if (!r.ok) throw new Error("graph"); return r.json(); }),
      fetch("../data/timeline.json").then((r) => { if (!r.ok) throw new Error("timeline"); return r.json(); }),
      fetch("../data/layers/summaries.json").then((r) => { if (!r.ok) throw new Error("summaries"); return r.json(); }),
      fetch("../data/layers/facts.json").then((r) => { if (!r.ok) throw new Error("facts"); return r.json(); }),
      fetch("../data/layers/events.json").then((r) => { if (!r.ok) throw new Error("events"); return r.json(); })
    ]);
    DATA = {graph: g, timeline: t, summaries: s, facts: f, events: e};
    document.getElementById("generated").textContent = "数据来源：实时文件（通过本地服务加载）";
  } catch (err) {
    document.getElementById("generated").textContent = "数据来源：内嵌快照（直接双击打开时使用）· 生成时间 " + esc(DATA.graph.generated_at || "");
  }
}

function renderCounts() {
  const g = DATA.graph, s = DATA.summaries, f = DATA.facts, e = DATA.events;
  document.getElementById("counts").innerHTML =
    "<span class='chip'>对话 " + (s.summaries ? s.summaries.length : 0) + "</span>"
    + "<span class='chip'>摘要 " + s.count + "</span>"
    + "<span class='chip'>事实 " + f.count + "</span>"
    + "<span class='chip'>事件 " + e.count + "</span>"
    + "<span class='chip'>图谱节点 " + g.node_count + "</span>"
    + "<span class='chip'>图谱边 " + g.edge_count + "</span>"
    + "<span class='chip'>记忆 0 条</span>";
  document.getElementById("graphMeta").textContent = "（" + g.node_count + " 个节点，" + g.edge_count + " 条边）";
}

function renderGraph() {
  const svg = document.getElementById("graphSvg");
  const nodes = DATA.graph.nodes, edges = DATA.graph.edges;
  const cx = 480, cy = 280, R = 210;
  const pos = {};
  nodes.forEach((n, i) => {
    const a = (2 * Math.PI * i) / Math.max(nodes.length, 1) - Math.PI / 2;
    pos[n.id] = [cx + R * Math.cos(a), cy + R * 0.85 * Math.sin(a)];
  });
  let out = "";
  edges.forEach((ed) => {
    const a = pos[ed.source], b = pos[ed.target];
    if (!a || !b) return;
    const mx = (a[0] + b[0]) / 2, my = (a[1] + b[1]) / 2;
    out += "<line x1='" + a[0] + "' y1='" + a[1] + "' x2='" + b[0] + "' y2='" + b[1] + "' stroke='#cbd5e1' stroke-width='1.5'/>"
      + "<text x='" + mx + "' y='" + my + "' fill='#64748b' text-anchor='middle'>" + esc(ed.relation) + "</text>";
  });
  nodes.forEach((n) => {
    const p = pos[n.id], color = TYPE_COLOR[n.type] || "#9ca3af";
    out += "<g class='node' data-node='" + esc(n.id) + "'><circle cx='" + p[0] + "' cy='" + p[1] + "' r='26' fill='" + color + "'/>"
      + "<text x='" + p[0] + "' y='" + (p[1] + 4) + "' fill='#fff' text-anchor='middle'>" + esc(n.label.length > 5 ? n.label.slice(0, 5) : n.label) + "</text>"
      + "<title>" + esc(n.label) + "（" + esc(n.type) + "）</title></g>";
  });
  svg.innerHTML = out;
  svg.querySelectorAll(".node").forEach((el) => {
    el.addEventListener("click", () => showNode(el.getAttribute("data-node")));
  });
  document.getElementById("edgeList").innerHTML = edges.map((ed) =>
    "<div class='card'>" + esc(ed.source) + " — " + esc(ed.relation) + " → " + esc(ed.target)
    + "<div class='meta'>来源对话：" + ed.sources.map(esc).join(", ") + "</div></div>").join("");
}

function showNode(nodeId) {
  const n = DATA.graph.nodes.find((x) => x.id === nodeId);
  if (!n) return;
  const relatedEdges = DATA.graph.edges.filter((e) => e.source === nodeId || e.target === nodeId);
  const relatedFacts = DATA.facts.facts.filter((f) =>
    f.fact.includes(nodeId) || f.sources.some((s) => n.sources.includes(s)));
  document.getElementById("nodeDetail").innerHTML =
    "<div class='detail'><b>" + esc(n.label) + "</b> · 类型：" + esc(n.type)
    + "<br>来源对话：" + n.sources.map(esc).join(", ")
    + "<br>相连关系：" + (relatedEdges.map((e) => esc(e.source + " — " + e.relation + " → " + e.target)).join("；") || "无")
    + "<br>相关事实：" + (relatedFacts.length ? "<ul>" + relatedFacts.map((f) => "<li>" + esc(f.fact) + "</li>").join("") + "</ul>" : "无直接匹配的事实。")
    + "</div>";
}

function sortedEvents() {
  const evs = DATA.timeline.events.slice();
  return evs.sort((a, b) => {
    if (a.date && !b.date) return -1;
    if (!a.date && b.date) return 1;
    if (a.date && b.date) return a.date < b.date ? -1 : 1;
    return (a.source_date || "") < (b.source_date || "") ? -1 : 1;
  });
}

function renderTimeline() {
  const evs = sortedEvents();
  document.getElementById("timelineList").innerHTML = evs.map((ev, i) => {
    const sid = ev.source_id || "";
    return "<div class='card' data-search='" + esc(ev.description + " " + (ev.title || "") + " " + (ev.date || "") + " " + (ev.source_date || "")) + "'>"
      + "<button class='del' type='button' data-del='event' data-sid='" + esc(sid) + "' data-label='" + esc(ev.description.slice(0, 20)) + "'>删除</button>"
      + "<b>" + esc(ev.date || "未注明日期") + "</b>" + (ev.source_date ? " · 对话日期 " + esc(ev.source_date) : "")
      + "<div>" + esc(ev.description) + "</div>"
      + "<div class='meta'>" + esc(ev.title || "") + " · 来源对话：" + esc(sid) + "</div>"
      + "<div class='delbox-slot'></div></div>";
  }).join("") || "<p class='empty'>暂无事件。</p>";
  bindDeleteButtons(document.getElementById("timelineList"));
}

function renderSummaries(q) {
  document.getElementById("summaryList").innerHTML = DATA.summaries.summaries.map((s) => {
    const text = s.title + " " + s.summary + " " + s.conversation_id + " " + (s.date || "");
    return "<div class='card' data-search='" + esc(text) + "'>"
      + "<button class='del' type='button' data-del='summary' data-sid='" + esc(s.conversation_id) + "' data-label='" + esc(s.title) + "'>删除</button>"
      + "<b>" + highlight(s.title, q) + "</b> · " + esc(s.date || "")
      + "<div>" + highlight(s.summary, q) + "</div>"
      + "<div class='meta'>来源对话：" + esc(s.conversation_id) + "（" + shortId(s.conversation_id) + "）</div>"
      + "<div class='delbox-slot'></div></div>";
  }).join("");
  bindDeleteButtons(document.getElementById("summaryList"));
}

function renderFacts(q) {
  document.getElementById("factList").innerHTML = DATA.facts.facts.map((f, i) => {
    const text = f.fact + " " + f.sources.join(" ");
    return "<div class='card' data-search='" + esc(text) + "'>"
      + "<button class='del' type='button' data-del='fact' data-sid='" + esc(f.sources[0] || "") + "' data-label='事实" + (i + 1) + "'>删除</button>"
      + "<b>事实 " + (i + 1) + "</b><div>" + highlight(f.fact, q) + "</div>"
      + "<div class='meta'>来源对话：" + f.sources.map(esc).join(", ") + "</div>"
      + "<div class='delbox-slot'></div></div>";
  }).join("");
  bindDeleteButtons(document.getElementById("factList"));
}

function renderEvents(q) {
  document.getElementById("eventList").innerHTML = DATA.events.events.map((ev) => {
    const text = ev.description + " " + (ev.title || "") + " " + (ev.source_id || "");
    return "<div class='card' data-search='" + esc(text) + "'>"
      + "<button class='del' type='button' data-del='event' data-sid='" + esc(ev.source_id || "") + "' data-label='" + esc(ev.description.slice(0, 20)) + "'>删除</button>"
      + "<b>" + esc(ev.date || "未注明日期") + "</b><div>" + highlight(ev.description, q) + "</div>"
      + "<div class='meta'>" + esc(ev.title || "") + " · 来源对话：" + esc(ev.source_id || "") + "</div>"
      + "<div class='delbox-slot'></div></div>";
  }).join("");
  bindDeleteButtons(document.getElementById("eventList"));
}

function applySearch() {
  const q = document.getElementById("q").value.trim();
  renderSummaries(q);
  renderFacts(q);
  renderEvents(q);
  let visible = 0, total = 0;
  $$(".card[data-search]").forEach((card) => {
    total++;
    const hay = card.getAttribute("data-search") || "";
    const show = !q || hay.toLowerCase().includes(q.toLowerCase());
    card.classList.toggle("hidden", !show);
    if (show) visible++;
  });
  document.getElementById("searchInfo").textContent = q
    ? ("搜索“" + q + "”：匹配 " + visible + " / " + total + " 条（摘要、事实、事件都查了，图谱节点按点击查看）。")
    : "";
  // Re-render timeline without the search filter on its own cards is handled
  // by the same .card[data-search] pass above; timeline cards also carry it.
}

document.querySelectorAll(".tabs button").forEach((btn) => {
  btn.addEventListener("click", () => {
    $$(".tabs button").forEach((b) => b.classList.remove("active"));
    btn.classList.add("active");
    $$("section[id^='tab-']").forEach((s) => s.classList.remove("active"));
    const tab = btn.getAttribute("data-tab");
    document.getElementById("tab-" + tab).classList.add("active");
    currentTab = tab;
  });
});
document.getElementById("q").addEventListener("input", applySearch);
document.getElementById("clearBtn").addEventListener("click", () => {
  document.getElementById("q").value = "";
  applySearch();
});

(async () => {
  await tryFetchLive();
  renderCounts();
  renderGraph();
  renderTimeline();
  applySearch();
})();
</script>
</body>
</html>
"""

if __name__ == "__main__":
    main()
