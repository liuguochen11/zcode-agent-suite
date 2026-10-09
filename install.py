#!/usr/bin/env python3
"""一键安装 ZCode Agent Suite：
1. 把 skills/ 下的两个 skill 拷贝到 ~/.zcode/skills（已存在则跳过，不覆盖）；
2. 调用 skill-sync 把它们同步（junction/符号链接）到本机所有 agent。

纯标准库，Python 3.8+。安全：只添加不删除，不读任何凭据。
"""
import os
import shutil
import subprocess
import sys

HOME = os.path.expanduser("~")
ROOT = os.path.dirname(os.path.abspath(__file__))
SKILLS = ("skill-sync", "task-monitor")


def main():
    store = os.path.join(HOME, ".zcode", "skills")
    os.makedirs(store, exist_ok=True)
    for name in SKILLS:
        src = os.path.join(ROOT, "skills", name)
        dst = os.path.join(store, name)
        if os.path.exists(dst):
            print(f"已存在，跳过: {dst}")
        else:
            shutil.copytree(src, dst)
            print(f"已安装: {dst}")

    sync = os.path.join(store, "skill-sync", "scripts", "skill_sync.py")
    print("\n同步到所有 agent ...")
    subprocess.run([sys.executable, sync, "link"], check=True)
    print("\n完成。task-monitor 用法:")
    print(f"  python {os.path.join(store, 'task-monitor', 'scripts', 'task_monitor.py')} serve")


if __name__ == "__main__":
    main()
