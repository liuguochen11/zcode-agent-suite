#!/usr/bin/env python3
"""skill-sync —— 把一个 skill 源目录共享/同步到本机所有 AI agent 的 skills 目录。

用法:
  python skill_sync.py list   [选项]
  python skill_sync.py link   [选项]   # 目录联接/符号链接, 单份存储实时共享(Windows 首选)
  python skill_sync.py copy   [选项]   # 复制镜像(备份/跨盘/分发)
  python skill_sync.py watch  [选项]   # 常驻轮询, 源变化自动重新同步

选项:
  --store DIR      源目录, 默认 ~/.zcode/skills
  --home DIR       覆盖 HOME(测试用)
  --only a,b       只同步到指定 agent(逗号分隔)
  --all            连未安装 agent 也创建其 skills 目录
  --dry-run        只打印将要执行的操作, 不实际执行
  --interval SEC   watch 轮询间隔, 默认 5

安全: 永不删除目标已存在的 skill; 同名一律跳过; 先 dry-run 后执行。
仅用 Python 标准库。
"""
import argparse
import os
import shutil
import subprocess
import sys
import time

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

AGENTS = [
    ("zcode",     ".zcode",       "skills"),
    ("codex",     ".codex",       "skills"),
    ("claude",    ".claude",      "skills"),
    ("cursor",    ".cursor",      "skills"),
    ("copilot",   ".copilot",     "skills"),
    ("gemini",    ".gemini",      "skills"),
    ("windsurf",  ".windsurf",    "skills"),
    ("workbuddy", ".workbuddy-ai", "skills"),
    ("trae-cn",   ".trae-cn",     "skills"),
    ("codebuddy", ".codebuddy",   "skills"),
]


def is_skill(d):
    return os.path.isdir(d) and os.path.isfile(os.path.join(d, "SKILL.md"))


def store_skills(store):
    if not os.path.isdir(store):
        return []
    return sorted(
        d for d in os.listdir(store) if is_skill(os.path.join(store, d))
    )


def resolve_agents(home, only, include_all):
    agents = []
    for name, dot, sub in AGENTS:
        if only and name not in only:
            continue
        path = os.path.join(home, dot, sub)
        agents.append((name, path, os.path.isdir(os.path.join(home, dot))))
    return agents


def make_link(source, target):
    """返回 None=成功, 字符串=跳过的原因."""
    source = os.path.abspath(source)
    target = os.path.abspath(target)
    if os.path.lexists(target):
        return "已存在, 跳过"
    os.makedirs(os.path.dirname(target), exist_ok=True)
    if os.name == "nt":
        r = subprocess.run(
            ["cmd", "/c", "mklink", "/J", target, source],
            capture_output=True,
        )
        if r.returncode == 0:
            return None
        shutil.copytree(source, target)
        return "联接失败, 已改为复制"
    try:
        os.symlink(source, target, target_is_directory=True)
        return None
    except OSError:
        shutil.copytree(source, target)
        return "符号链接失败, 已改为复制"


def do_link(store, agents, dry_run):
    skills = store_skills(store)
    for name, path, installed in agents:
        if not installed:
            print(f"[{name}] 未安装, 跳过: {path}")
            continue
        for s in skills:
            src = os.path.join(store, s)
            dst = os.path.join(path, s)
            if os.path.lexists(dst):
                print(f"[{name}] {s}: 已存在, 跳过")
                continue
            print(f"[{name}] {s}: {'(dry-run) ' if dry_run else ''}联接 -> {dst}")
            if not dry_run:
                r = make_link(src, dst)
                if r:
                    print(f"          {r}")


def do_copy(store, agents, dry_run):
    skills = store_skills(store)
    for name, path, installed in agents:
        if not installed:
            print(f"[{name}] 未安装, 跳过: {path}")
            continue
        for s in skills:
            src = os.path.join(store, s)
            dst = os.path.join(path, s)
            print(f"[{name}] {s}: {'(dry-run) ' if dry_run else ''}复制 -> {dst}")
            if not dry_run:
                shutil.copytree(src, dst, dirs_exist_ok=True)


def do_list(store, agents):
    print(f"源目录: {store}")
    skills = store_skills(store)
    print(f"源 skill ({len(skills)}): " + ", ".join(skills) if skills else "源 skill: 无")
    print()
    print("检测到的 agent:")
    for name, path, installed in agents:
        mark = "已安装" if installed else "未安装"
        if os.path.isdir(path):
            have = [d for d in os.listdir(path) if is_skill(os.path.join(path, d))]
            link = [d for d in os.listdir(path) if os.path.islink(os.path.join(path, d))]
            detail = f"目录存在, 已有 {len(have)} 个 skill" + (f", {len(link)} 个为链接" if link else "")
        else:
            detail = "skills 目录不存在"
        print(f"  {name:10s} [{mark}] {path}")
        print(f"              {detail}")


def fingerprint(store):
    out = {}
    for s in store_skills(store):
        p = os.path.join(store, s, "SKILL.md")
        try:
            st = os.stat(p)
            out[s] = (st.st_mtime, st.st_size)
        except OSError:
            out[s] = None
    return out


def main():
    ap = argparse.ArgumentParser(description="共享 skill 到本机所有 AI agent")
    ap.add_argument("command", choices=["list", "link", "copy", "watch"])
    ap.add_argument("--store", default=None)
    ap.add_argument("--home", default=os.path.expanduser("~"))
    ap.add_argument("--only", default=None)
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--interval", type=float, default=5.0)
    args = ap.parse_args()

    store = args.store or os.path.join(args.home, ".zcode", "skills")
    only = set(args.only.split(",")) if args.only else None
    agents = resolve_agents(args.home, only, args.all)
    agents = [(n, p, i or args.all) for n, p, i in agents]

    if args.command == "list":
        do_list(store, agents)
        return

    if args.command == "watch":
        print(f"watch 模式: 源目录 {store}, 间隔 {args.interval}s, Ctrl+C 退出")
        last = fingerprint(store)
        while True:
            time.sleep(args.interval)
            now = fingerprint(store)
            if now != last:
                print(f"[{time.strftime('%H:%M:%S')}] 检测到变化, 重新同步(link)")
                do_link(store, agents, False)
                last = now
        return

    if args.command == "link":
        do_link(store, agents, args.dry_run)
    elif args.command == "copy":
        do_copy(store, agents, args.dry_run)


if __name__ == "__main__":
    main()
