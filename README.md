# ZCode Agent Suite

一套让本机所有 AI Agent 协同工作的基础设施：**skill-sync**（一个 skill 配置一次、所有 agent 实时共用）+ **task-monitor**（一张实时网页监控所有会话/任务）。

> English: Two zero-dependency tools that make every AI agent on your machine share one skill pool and show all running sessions/tasks on a single live dashboard.

## 组件

### 1. skill-sync —— 跨 Agent 技能共享

在 `~/.zcode/skills` 里配置一次 skill，自动以**目录联接（Windows junction，免管理员）**挂载到本机所有 agent 的 skills 目录：

| Agent | 目录 |
|---|---|
| ZCode | `~/.zcode/skills` |
| Codex | `~/.codex/skills` |
| Claude Code | `~/.claude/skills` |
| Cursor / Copilot / Gemini / Windsurf | `~/.cursor/skills` 等 |
| WorkBuddy | `~/.workbuddy-ai/skills` |
| Trae CN | `~/.trae-cn/skills` |
| CodeBuddy | `~/.codebuddy/skills` |

- 单份存储：所有 agent 读同一份文件，改一处全部生效，零复制零漂移；
- 安全：只添加不删除、同名跳过、`--dry-run` 先预演；
- 自动降级：不支持的盘符（如网络盘）自动改为复制；非 Windows 平台用符号链接；
- 反向合并：某 agent 自带的 skill 复制进源目录即可进共享池。

```bash
python skills/skill-sync/scripts/skill_sync.py list        # 看现状
python skills/skill-sync/scripts/skill_sync.py link --dry-run
python skills/skill-sync/scripts/skill_sync.py link        # 执行共享
python skills/skill-sync/scripts/skill_sync.py watch       # 常驻自动同步
```

### 2. task-monitor —— 实时任务监控页

只读 `~/.zcode/cli/db/db.sqlite`，一张自动刷新的网页看全局：

- 汇总卡片：活跃会话、运行中工具调用、运行中任务、今日 turns/tokens/错误；
- 会话面板：最近 30 个会话（状态/类型/最近活动/token/错误），运行中高亮；
- 任务树：`session_task_link` 里所有运行中任务（阶段/模型）；
- 动态工作流：dwf 运行 + 每个 actor（如"质检员"）的节点状态、耗时、token；
- 工具日志：最近 20 条工具调用，报错标红带原因。

```bash
python skills/task-monitor/scripts/task_monitor.py serve --port 8765  # 实时页 http://127.0.0.1:8765
python skills/task-monitor/scripts/task_monitor.py render             # 静态页(桌面, 5s 自刷)
```

## 安装

要求：Python 3.8+（纯标准库，零 pip 依赖），Windows 10/11（junction）；macOS/Linux 自动用符号链接。

```bash
# 方式一：一键安装（拷贝两个 skill 到 ~/.zcode/skills 并同步全 agent）
python install.py

# 方式二：手动
cp -r skills/skill-sync skills/task-monitor ~/.zcode/skills/
python ~/.zcode/skills/skill-sync/scripts/skill_sync.py link
```

## 架构

```
~/.zcode/skills/  (唯一源)
   ├── skill-a/
   ├── skill-b/
   └── skill-sync/ ──────────┐   python skill_sync.py link
                              │   (mklink /J, 免管理员)
   ~/.codex/skills/ ──────────┼── skill-a ──▶ junction ──┐
   ~/.claude/skills/ ─────────┼── skill-b ──▶ junction ──┤ 全部指向同一份文件
   ~/.workbuddy-ai/skills/ ───┴── ...                   ◀─┘

~/.zcode/cli/db/db.sqlite ──(只读 mode=ro)──▶ task-monitor ──▶ http://127.0.0.1:8765
```

详见 [docs/architecture.md](docs/architecture.md)。

## FAQ

- **会覆盖 agent 自带的 skill 吗？** 不会。只添加，同名一律跳过，agent 内置技能原样保留。
- **为什么是 junction 而不是复制？** 单份存储实时生效、零磁盘占用；junction 无需管理员权限（符号链接在 Windows 上需要开发者模式）。
- **task-monitor 会拖慢 agent 吗？** 不会。只读连接 + WAL 兼容，打不开时自动复制临时副本再读。
- **数据安全？** task-monitor 只在本机 127.0.0.1 监听，不联网不上传；skill-sync 不读任何凭据文件。

## License

MIT
