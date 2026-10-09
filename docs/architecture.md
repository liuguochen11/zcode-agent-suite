# 架构说明

## skill-sync 原理

```
        源目录 ~/.zcode/skills/（单份存储）
        ├── skill-a/
        │     └── SKILL.md
        └── skill-sync/scripts/skill_sync.py

python skill_sync.py link
        │
        ├─ Windows:  mklink /J <agent目录>/<skill> <源>/<skill>   （目录联接，免管理员）
        │           失败（网络盘等）→ 自动降级 copytree
        │
        └─ POSIX:    os.symlink(...)                              （符号链接）
                     失败 → 自动降级 copytree

结果：所有 agent 读同一份文件，改源即生效；agent 自身技能不受影响（逐 skill 合并，只添加）。
```

关键不变量：

- 永不删除目标已存在的 skill；同名跳过（防覆盖 agent 内置技能）；
- `os.path.abspath` 归一化路径后再调 mklink（mklink 不接受正斜杠）；
- 已安装判定 = agent 家目录存在（`~/.codex` 等），未安装默认跳过，`--all` 强制创建。

## task-monitor 数据流

```
~/.zcode/cli/db/db.sqlite        （ZCode 本地库，WAL 模式）
   ├── session                  会话表（标题/类型/时间）
   ├── turn_usage               每轮状态与 token（completed/cancelled/error）
   ├── tool_usage               工具调用（status='running' ⇒ 会话正在干活）
   ├── session_task_link        任务树（status/phase/model/父会话）
   ├── dwf_run / dwf_actor / dwf_node   动态工作流运行与 actor 节点
   └── (model_usage 等，暂未使用)

task_monitor.py
   ├── open_db(): sqlite3 'file:...?mode=ro' 只读；失败则 copy 临时副本再读
   ├── load():  聚合 会话+统计 / 任务树 / 工作流 / 工具日志 / 今日汇总
   ├── render:  生成静态 HTML（meta refresh 5s）→ 桌面 task-monitor.html
   └── serve:   ThreadingHTTPServer 只监听 127.0.0.1:8765
                /          → HTML（meta refresh 3s）
                /api/data  → JSON（程序化消费）
```

时间戳均为毫秒 epoch，展示时转本地时间。

## 安全边界

- task-monitor 不监听外网（127.0.0.1）、不写库、不杀进程；
- skill-sync 不读取任何凭据/配置文件，只处理 skill 目录结构；
- 两者均零第三方依赖（纯 Python 标准库），可直接审计全部源码。
