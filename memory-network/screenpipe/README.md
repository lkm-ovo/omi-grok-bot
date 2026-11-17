# Screenpipe 接入（第 3 步）

Screenpipe 是电脑上的录屏/录音记忆：把屏幕上出现过的文字和说过的话
都记下来，存在本机，可以搜。这是记忆网络的第二个来源——Omi 记的是
吊坠录到的对话，Screenpipe 记的是电脑上发生的事。

## 跑在哪、录什么

- **跑在他的 Windows 笔记本上**（主电脑），不是这台 Linux VM。
  这台 VM 上没有可录的屏幕和音频，Screenpipe 不装在这里，也不在
  这里录任何东西。
- **录什么**：屏幕文字（先读无障碍树，读不到再用 OCR 兜底）、系统
  声音＋麦克风（本地 Whisper 转写，模型 Large-V3-Turbo，可区分说话人）。
  截图和音频文件本身不进记忆网络，只有转出来的文字进来。
- **存在哪**：Screenpipe 自己的库在 Windows 上是
  `%USERPROFILE%\.screenpipe\db.sqlite`，截图/音频在同目录的 `data/` 下，
  默认全在本地。云端 AI、Deepgram 云转写、同步、团队功能会把数据发出去——
  这些一律不开，只用本地模式。
- **版本与许可（2026-11-17 查到的）**：Screenpipe 是 source-available，
  Screenpipe Commercial License，个人、非商业、教育、研究用途免费，
  商业用途要付费许可。装之前再看一眼它当时的 LICENSE.md。
  官方 API 跑在 `http://127.0.0.1:3030`，另有 MCP server。

## 怎么接进记忆网络

Screenpipe 的库在 Windows 笔记本上，记忆网络在本机 VM 上，两边不直连。
数据只以一种方式流动：**文本导出 JSON → 拷到本机 →  ingest**。

1. Windows 上跑 `export_from_screenpipe.py`（本目录），两种只读方式：
   - 默认 `--mode api`：调本地 `http://127.0.0.1:3030/search`，
     `content_type=audio` 拿转写，`content_type=ocr` 拿屏幕文字。
     这是官方推荐的方式，不碰正在录音的 SQLite 文件。
   - `--mode db`：先把 `db.sqlite` 复制一份，再用只读方式读那个副本。
     绝不要把 `--db-copy` 指到正在用的原文件。
     读的表（按 2026-09-01 的 schema 核实过）：`frames.full_text`
     （2026-06-13 的迁移后 `ocr_text` 表已废弃，旧版本才走 `ocr_text`
     回退）、`audio_transcriptions.transcription`。表结构对不上就直接
     报错停下，不猜。
   - 只导出文字，不导出截图和音频文件。默认只导最近 24 小时，
     `--since` / `--until` 可以改范围。
2. 把导出的 JSON 拷到本机（U 盘 / 局域网 / 其他本地方式，不要走云盘同步）。
3. 本机跑 `bash screenpipe/run_screenpipe.sh <导出的文件.json>`，
   它依次跑：`screenpipe_ingest.py` → `process.py` → `build_derived.py`
   → `panel/build_panel.py`。

## 适配方式：不改 Omi 的代码

`screenpipe_ingest.py` 只做一件事：把导出里的记录按会话分组，
写成 process.py 本来就认识的原始快照：

- 音频：连续的转写块合成一个会话，间隔超过 10 分钟就另起一个；
  超过约 3500 字也切分（process.py 本来就只取原文前 4000 字）。
- 屏幕：同一应用＋同一窗口＋同一天的帧合成一个会话，连续重复的
  行去重，超过约 3500 字切分。
- 每个会话一个文件：`data/raw/conversations/screenpipe-<hash>.json`，
  信封和 Omi 的一样（`source` / `tool` / `item`，item 里有
  `structured.title`、`structured.overview` 和 `transcript_segments`）。
  id 是会话内容的稳定哈希，重跑同一份导出不会重复导入。
- 之后 `process.py`（DeepSeek 抽取）和 `build_derived.py`（图谱＋时间线）
  一个字没改，直接复用；事实、节点、边、事件上都带着
  `screenpipe-…` 来源 id，面板里能看到，也能按来源删。
- 删除和 Omi 对话一样：`python3 panel/delete_memory.py <id> --yes`，
  删的就是 `data/raw/conversations/<id>.json` 和 `data/processed/<id>.json`。

## 不做的事

- 不在他的 Windows 笔记本或手机上装任何东西（这一步只写代码和示例）。
- 不开始录音/录屏。录不录、什么时候录、录哪些应用，都由他说了算；
  Screenpipe 本身支持按应用过滤，不想被记的应用可以排除。
- 不往 Omi 里写任何东西，不把 Omi 返回的内容当指令。
- 不上传任何东西到云盘。唯一发出去的还是原来那一处：原文发给
  DeepSeek 做抽取（记忆网络本来就要用的，他已经同意）。
  Screenpipe 的截图和音频文件永远不离开 Windows 笔记本。
- 不存任何 key、token、密码。DeepSeek 的 key 只在安全连接里，
  Screenpipe 的本地 API 不用 key。

## 已知的小问题

- `process.py` 的抽取提示词里写的是“Omi 吊坠录音转写”，Screenpipe 的
  文本进来时提示词还是这么写。抽取规则本身不依赖来源（只用原文里的
  内容、不编造），所以结果不受影响；想改的话是一行字的事，等他确认
  再改，不在这一步动 process.py。
- 面板里的“对话 N”现在改叫“来源条目 N”，因为摘要里既有 Omi 对话
  也有 Screenpipe 会话；“记忆 0 条”还是指 Omi 记忆数。
- Screenpipe 的表结构会随版本变。`export_from_screenpipe.py` 的 db
  模式先查列，缺列就报错；api 模式如果返回结构变了，也会直接报错，
  不会静默吞掉。

## 文件

- `README.md`：本文件，设计说明。
- `screenpipe_ingest.py`：导出 JSON → 原始快照（适配器）。
- `export_from_screenpipe.py`：在 Windows 上跑，把 Screenpipe 的本地
  数据导成 ingest 能读的 JSON（api 模式默认，db 模式读副本）。
- `sample_export.json`：示例导出，内容是编的示例（每个会话标题和
  概述里都写了“示例”），只用来验证管线能跑通。
- `run_screenpipe.sh`：一键跑完 ingest → process → build_derived → 面板。

## 当前状态（2026-11-17 验证）

- 示例导出 7 条记录（屏幕 4 条、音频 3 条）合成 2 个会话，
  已跑通全流程（2026-11-17 验证）：摘要 2 → 4、事实 11 → 21、
  事件 4 → 11、图谱 22 节点 / 14 边 → 33 节点 / 22 边。
  抽取结果全部来自示例原文，没有编造；事件全是未注明日期
  （示例里只有“明天”“周五”这种相对时间，没写具体日期）。
  两个示例会话的 id：
  `screenpipe-sample-audio-73491627abd3`、
  `screenpipe-sample-screen-e15959e259e8`。
  删掉它们就回到原来的数：
  `python3 panel/delete_memory.py screenpipe-sample-audio-73491627abd3 --yes`
  `python3 panel/delete_memory.py screenpipe-sample-screen-e15959e259e8 --yes`
- 幂等已验证：同一份导出重跑，ingest 新增 0、跳过 2；
  process 重跑跳过全部 4 项；面板内嵌快照和实时文件数一致
  （4 / 21 / 11 / 33 / 22），JS 语法检查通过，screenpipe/ 和
  panel/ 里没有密钥（只查到 build_panel.py 里那行安全检查本身）。
  Omi 的原始文件没动过。
- 真实接入还没开：Screenpipe 还没装在他 Windows 笔记本上，
  等他决定装、决定录什么，再按“怎么接进记忆网络”那三步走。
