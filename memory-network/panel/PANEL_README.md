# Omi 记忆网络 · 可视化面板（第 2 步）

## 怎么打开

两种办法都可以，数据只存在本机，不联网：

1. 直接双击打开 `panel.html`。页面里内嵌了一份数据快照，所以不用开服务器也能看。
2. 想看最新数据，用本地服务打开（推荐）：
   ```bash
   cd ~/workspace/omi-memory-network
   bash panel/serve.sh
   ```
   然后在浏览器打开 http://localhost:8321/panel/panel.html

## 面板里有什么

- 图谱：22 个节点、14 条边，点一个节点可以看到它的类型、来源对话、相连关系和相关事实。
- 时间线：4 个事件按日期排，没有明确日期的排在最后（现在 4 个都没有明确日期）。
- 摘要：2 条，事实：11 条，事件：4 条，每条都标了来源对话 id。
- 搜索：顶上的搜索框同时查摘要、事实、事件，命中的字会标黄。

## 刷新（新数据到了以后）

Omi 里有了新对话，先跑一次完整更新，再重新生成面板，最后刷新页面：

```bash
cd ~/workspace/omi-memory-network
bash run_all.sh
python3 panel/build_panel.py
```

用本地服务打开时，刷新页面就会读到最新的 JSON 文件；直接双击打开时，必须先跑 `python3 panel/build_panel.py` 更新内嵌快照，再刷新页面。

## 删除一段记忆

面板本身不直接删文件。点每条旁边的“删除”，页面会告诉你具体删哪两个文件：

- `data/raw/conversations/<对话id>.json`
- `data/processed/<对话id>.json`

删完再跑：

```bash
cd ~/workspace/omi-memory-network
python3 process.py
python3 build_derived.py
python3 panel/build_panel.py
```

也可以用助手脚本（它会先打印要删的文件，加 `--yes` 才真的删）：

```bash
python3 panel/delete_memory.py <对话id> --yes
```

## 隐私

- 面板是纯 HTML/CSS/JS，没有外部网络请求，没有 CDN，没有统计。
- 面板不调用 DeepSeek，不调用 Omi，只读本地 `data/` 里的 JSON 文件。
- 不存任何 key、token、密码。
