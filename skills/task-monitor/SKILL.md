---
name: task-monitor
description: 实时监控本机 ZCode 所有会话/任务的网页仪表盘。只读 db.sqlite 与会话目录，展示每个会话的状态（运行中/完成/出错）、任务树、动态工作流 actor 进度、token 消耗与工具报错，自动刷新。当用户想看"我 agent 现在在跑什么"、监控多个并行任务/多个窗口会话、要一个任务监控页/仪表盘时使用。零依赖纯标准库。
---

# task-monitor

一张自动刷新的网页，监控本机 ZCode 的所有会话与任务（多个窗口/后台任务/工作流 actor 全部汇总）。

## 用法

```bash
# 方式一：静态页（最简单，5 秒自动刷新，改 HTML 即改页面）
python scripts/task_monitor.py render [-o 输出路径.html]   # 默认 ~/Desktop/task-monitor.html 并自动用浏览器打开

# 方式二：本地服务（3 秒轮询，无需整页刷新）
python scripts/task_monitor.py serve [--port 8765]         # 打开 http://127.0.0.1:8765
```

参数：`--db PATH`（默认 `~/.zcode/cli/db/db.sqlite`，自动跟随 `ZCODE_HOME`）、`--port`（serve 模式端口）、`-o`（render 输出路径）、`--no-open`（不自动开浏览器）。

## 数据来源（全部只读）

- `~/.zcode/cli/db/db.sqlite`：`session`（会话）、`turn_usage`（每轮状态/token）、`tool_usage`（工具调用，`status='running'` 即会话正在干活）、`session_task_link`（任务树）、`dwf_run`/`dwf_actor`/`dwf_node`（动态工作流运行与 actor 进度）。
- 以 `mode=ro` 只读打开（WAL 安全），打不开时自动复制临时副本再读，绝不影响正在运行的 agent。

## 页面内容

- 汇总卡片：活跃会话数、今日 turns/tokens、错误数、运行中任务数；
- 运行中任务：正在执行工具调用的会话 + 工作流 actor 任务树（状态/阶段/模型）；
- 工作流面板：最近 dwf 运行（名称、actor 完成/失败数、耗时、token）；
- 会话面板：最近 30 个会话（标题、类型：交互/子代理/工作流子任务、最近活动、turns、token、错误），运行中的高亮；
- 工具日志：最近 20 条工具调用，报错标红（含 error_type/error_message）。

## 约定

- 只读监控，不改任何 ZCode 数据；不写 db，不杀进程。
- 时间戳为毫秒 epoch，展示转本地时间。
- 跨窗口可用：页面无状态，任何窗口的 agent 或用户本人都能打开同一个 URL/文件看到全局。
- 若 db 路径不对（非默认安装），先跑 `list-sources` 探测可用的会话目录，再 `--db` 指定。
