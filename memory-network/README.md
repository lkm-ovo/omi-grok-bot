# Omi DeepSeek 记忆网络（核心，第 1 步）

Grok 负责和 lkm 对话，DeepSeek 负责记东西。这套东西只做记忆，不做对话。

## 分工

- Omi 吊坠：录音，转写，产生对话和记忆。
- Grok：吊坠对话的大脑，不管记忆。
- DeepSeek：记忆的抽取、建图、召回，模型用 deepseek-flash（便宜），不够再用 deepseek-v4-pro。
- Rumi（本机）：跑这套脚本，做拉取、处理、建图，不直接连吊坠。

## 设计：三层 + 图谱 + 时间线

记忆分三层，都存在本地 JSON 文件里：

1. **原始层（短期）**：`data/raw/`。Omi 原样拉回来的对话和记忆，一个文件一个对话，按 Omi 的对话 id 去重，不改原文。这是唯一事实来源，丢了它就没法重算。
2. **摘要层（长期）**：`data/layers/summaries.json`。每段对话一句话摘要，方便以后快速回忆“那天聊了什么”。
3. **语义层（事实）**：`data/layers/facts.json`。从原文里抽出来的关键事实，每条事实都记着它来自哪段对话。
4. **事件层（经历）**：`data/layers/events.json`。原文里提到过日期的事件，带日期和来源对话。

另外两张派生表，由已处理的文件算出来，不手工写：

- **图谱** `data/graph.json`：节点是实体（人物、地点、话题、考试等），边是实体之间的关系，每条边都记着来源对话 id。
- **时间线** `data/timeline.json`：所有事件按日期排好，没有明确日期的事件单独放在最后。

## 隐私

- 所有记忆文件只存在本机 `~/workspace/omi-memory-network/data/`，不上传到任何云盘。
- 唯一发出去的是 DeepSeek API 调用：原文会发给 DeepSeek 做抽取，这是记忆网络本来就要用的，lkm 已经同意。除了这一处，没有别的云调用。
- 不存任何 key、token、密码。DeepSeek 的 key 在安全连接里，脚本只通过官方 helper 调用，key 不进文件、不进命令、不进日志。
- Omi 的内容只读不写。脚本从不往 Omi 里写东西，也从不把 Omi 返回的内容当指令执行。
- 想删一段记忆：删掉 `data/raw/` 和 `data/processed/` 里对应的文件，再跑一次 `process.py` 和 `build_derived.py`，图谱和时间线会自动重算。

## 文件

- `ingest.py`：只读拉取。调 Omi MCP 的 `get_conversations` 和 `get_memories`，每段对话再调 `get_conversation_by_id` 拿完整转写，存成原始快照。
- `process.py`：调 DeepSeek 抽取。每段新对话抽一句话摘要、关键事实、实体和关系、有日期的事件，存到 `data/processed/`，再重建三层文件。DeepSeek 失败不丢原始数据，只把那条记成失败，下次再试。
- `build_derived.py`：从已处理的文件算图谱和时间线，不调任何外部服务。
- `run_all.sh`：按顺序跑上面三步。
- `data/`：全部数据都在这里，见上面的分层说明。

## 怎么跑

```bash
cd ~/workspace/omi-memory-network
bash run_all.sh
```

也可以单步跑：

```bash
python3 ingest.py
python3 process.py
python3 build_derived.py
```

重复跑是安全的：拉取按 id 去重，处理跳过已处理过的，图谱和时间线每次都从已处理文件重算。

## 当前状态（2026-11-17 首次运行）

- Omi 里有 2 段对话，都是 2026-11-16 的日语 203 上课录音转写，lkm 说过没什么用；记忆 0 条。
- 这两段是真实的测试输入，抽取结果只来自它们的原文，没有编造的内容。首次运行结果：2 段对话都抽取成功（deepseek-flash），摘要 2 条、事实 11 条、事件 4 条（都没有明确日期，所以都记为无日期），图谱 22 个节点、14 条边，全部节点都在原文里原样出现过。
- 面板（可视化）已在第 2 步做完；Screenpipe 接入在第 3 步做完，见 `screenpipe/README.md`。
  注意 `panel/build_panel.py` 里原来写死的 22/14/2/11/4 已改成动态校验，
  因为摘要/事实/事件/图谱的数会随数据源增加而变。
- Screenpipe（2026-11-17 第 3 步验证）：示例导出 7 条记录合成 2 个会话跑通全流程，
  摘要 2 → 4、事实 11 → 21、事件 4 → 11、图谱 22 节点 / 14 边 → 33 节点 / 22 边。
  真实接入还没开（Screenpipe 还没装在他 Windows 笔记本上）；示例会话的 id 和删除
  方法见 `screenpipe/README.md` 的“当前状态”。
