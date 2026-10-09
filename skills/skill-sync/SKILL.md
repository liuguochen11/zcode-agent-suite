---
name: skill-sync
description: 把一个 skill 源目录（默认 ~/.zcode/skills）一键共享/同步到本机所有 AI agent 的 skills 目录（ZCode、Codex、Claude Code、Cursor、Copilot、Gemini、Windsurf、WorkBuddy、Trae CN、CodeBuddy）。Windows 用目录联接（junction）实现单份存储、全 agent 实时共用，改一处全部生效。当用户想让某个 skill 被电脑上所有 agent 共同使用、集中管理 skills、问"怎么让多个 agent 共用同一个 skill"或"配置一次所有 agent 都能用"时使用。
---

# skill-sync

让一个 skill 只配置一次，本机所有 AI agent 自动共同使用。

## 原理

各 agent 的 skill 目录是固定的（如 `~/.zcode/skills`、`~/.codex/skills`、`~/.claude/skills`）。本 skill 把**源目录**里每个 skill 以目录联接（Windows `mklink /J`，无需管理员权限；其他平台用符号链接）挂到各 agent 的 skills 目录下：

- 单份存储：所有 agent 读的是同一份文件，改源目录立刻全生效，无复制无漂移；
- 逐 skill 合并：只添加、不覆盖，agent 自带的同名/内置 skill 原样保留（绝不整目录替换）；
- 不支持联接的盘（如网络盘）自动降级为复制。

源目录默认 `~/.zcode/skills`（ZCode 本机的 skill 仓库），可用 `--store` 换任意目录。

## 使用流程

1. **查看现状**：`python scripts/skill_sync.py list` —— 列出源目录的 skill 和本机检测到的 agent 及其 skill 目录是否存在。
2. **预演**：`python scripts/skill_sync.py link --dry-run` —— 先看将执行哪些联接，确认无误。
3. **执行共享**：`python scripts/skill_sync.py link` —— 默认只对**已安装**的 agent 生效（agent 目录已存在的才同步）；加 `--all` 会连未安装 agent 的目录也一并创建。
4. **验证**：进各 agent 目录确认出现了指向源目录的联接；在该 agent 里直接问"你有哪些 skills"或试跑一个 skill。

## 命令速查

| 命令 | 作用 |
|---|---|
| `list` | 列出源 skill、检测到的 agent、当前共享状态 |
| `link` | 目录联接/符号链接共享（Windows 首选，实时共用） |
| `copy` | 复制镜像到各 agent（适合备份、跨盘、发给别人） |
| `watch` | 常驻轮询（默认 5s 间隔），源目录出现新 skill 或改动时自动重新同步 |

参数：`--store DIR`（源目录）、`--only zcode,codex`（只同步指定 agent）、`--all`（含未安装 agent）、`--dry-run`（只打印不执行）、`--interval SEC`（watch 间隔）、`--home DIR`（测试时覆盖 HOME）。

## 安全约定（必须遵守）

- **永不删除**：脚本只有添加/更新，绝不删除任何 agent 目录里已有的 skill；
- **同名跳过**：目标位置已存在同名 skill（无论真目录还是联接）一律跳过并报告，由用户决定是否手动迁移后重跑；
- **先 dry-run 后执行**：对外部 agent 目录（codex/claude/cursor 等）操作前先 `--dry-run` 给用户看结果；
- 删除联接不会删除源文件（`rmdir` 联接目录是安全的），但**不要**在 agent 目录里删"穿过联接"的文件——会删到源。

## 常见情况

- **目标已存在同名 skill**：list 会标出冲突。确认内容一致可跳过；不一致时先备份目标目录里的同名项，再重跑。
- **只想共享部分 skill**：把要共享的 skill 复制到一个独立目录，用 `--store` 指向它（例如桌面 `ai.skills/user`），或用 `--only` 限定 agent。
- **把某个 agent 自己的 skill 并入共享池**：直接复制到源目录再跑 `link`，该 skill 就会同步给所有 agent（目标已存在同名项时跳过，内容一致无影响）。
- **想让新 skill 自动传播**：`link` 模式下新加的 skill 不会自动出现，需重跑一次 link；或开 `watch` 常驻后台自动同步。
- **换电脑/备份**：用 `copy` 模式把源目录镜像出去即可。
