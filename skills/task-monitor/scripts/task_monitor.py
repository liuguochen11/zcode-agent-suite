#!/usr/bin/env python3
"""task-monitor —— 只读监控本机 ZCode 所有会话/任务的网页仪表盘。

用法:
  python task_monitor.py render [-o out.html] [--no-open]
  python task_monitor.py serve [--port 8765]
  python task_monitor.py list-sources

零依赖, 纯标准库。只读 db.sqlite, 不改任何 ZCode 数据。
"""
import argparse
import html
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

DEFAULT_DB = os.path.join(
    os.environ.get("ZCODE_HOME", os.path.join(os.path.expanduser("~"), ".zcode")),
    "cli", "db", "db.sqlite",
)


def fmt_ts(ms):
    if not ms:
        return "-"
    return time.strftime("%m-%d %H:%M:%S", time.localtime(ms / 1000))


def fmt_dur(ms):
    if not ms:
        return "-"
    s = int(ms / 1000)
    if s < 60:
        return f"{s}s"
    if s < 3600:
        return f"{s // 60}m{s % 60:02d}s"
    return f"{s // 3600}h{(s % 3600) // 60:02d}m"


def fmt_tokens(n):
    if n is None:
        return "-"
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1000:
        return f"{n / 1000:.1f}K"
    return str(n)


def open_db(path):
    """只读打开; 失败则复制到临时目录再读, 绝不影响运行中的 agent."""
    try:
        return sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    except sqlite3.Error:
        tmp = os.path.join(tempfile.gettempdir(), "task-monitor-db-copy.sqlite")
        shutil.copy2(path, tmp)
        return sqlite3.connect(tmp)


def load(db_path, hours=24):
    c = open_db(db_path)
    c.row_factory = sqlite3.Row
    now = time.time() * 1000
    window = now - hours * 3600 * 1000

    def q(sql, *args):
        try:
            return [dict(r) for r in c.execute(sql, args).fetchall()]
        except sqlite3.Error as e:
            return [{"_err": str(e)}]

    # 会话 + 最近活动/统计
    sessions = q(
        """SELECT s.id, s.title, s.task_type, s.directory, s.time_created, s.time_updated,
              (SELECT MAX(started_at) FROM turn_usage u WHERE u.session_id = s.id) AS last_turn,
              (SELECT COUNT(*) FROM turn_usage u WHERE u.session_id = s.id) AS turns,
              (SELECT SUM(computed_total_tokens) FROM turn_usage u WHERE u.session_id = s.id) AS tokens,
              (SELECT COUNT(*) FROM tool_usage t WHERE t.session_id = s.id AND t.status = 'running') AS running_tools,
              (SELECT COUNT(*) FROM tool_usage t WHERE t.session_id = s.id AND (t.error_type IS NOT NULL OR t.status = 'error')) AS tool_errors
        FROM session s
        ORDER BY COALESCE((SELECT MAX(started_at) FROM turn_usage u WHERE u.session_id = s.id), s.time_updated) DESC
        LIMIT 30"""
    )
    for s in sessions:
        if not s.get("_err"):
            s["active"] = bool(s["running_tools"]) or (
                s.get("last_turn") and s["last_turn"] >= now - 10 * 60 * 1000
            )

    # 运行中的任务树
    tasks = q(
        """SELECT id, root_workflow_run_id, parent_session_id, child_session_id, role, depth,
              path, phase, label, agent_type, model, status, time_created, time_updated
        FROM session_task_link WHERE status = 'running' ORDER BY time_updated DESC LIMIT 30"""
    )

    # 动态工作流
    runs = q(
        """SELECT r.id, r.parent_session_id, r.name, r.status, r.spent_tokens,
              r.time_created, r.time_updated,
              (SELECT COUNT(*) FROM dwf_node n WHERE n.run_id = r.id) AS nodes,
              (SELECT COUNT(*) FROM dwf_node n WHERE n.run_id = r.id AND n.status = 'failed') AS failed,
              (SELECT COUNT(*) FROM dwf_node n WHERE n.run_id = r.id AND n.status = 'completed') AS done
        FROM dwf_run r ORDER BY r.time_created DESC LIMIT 8"""
    )
    for r in runs:
        if r.get("_err"):
            continue
        actors = q(
            """SELECT a.name, a.resolved_model, a.session_id, a.time_created,
               (SELECT n.status FROM dwf_node n WHERE n.run_id = a.run_id
                 AND n.actor_site_id = a.site_id AND n.actor_ordinal = a.ordinal
                 ORDER BY n.time_created DESC LIMIT 1) AS node_status
            FROM dwf_actor a WHERE a.run_id = ? ORDER BY a.ordinal""",
            r["id"],
        )
        r["actors"] = actors

    # 工具日志
    tools = q(
        """SELECT session_id, tool_name, status, error_type, error_message, duration_ms,
              started_at, completed_at
        FROM tool_usage ORDER BY started_at DESC LIMIT 20"""
    )

    # 汇总
    today_start = (now // 86400000) * 86400000 - time.timezone * 1000
    sums = q(
        """SELECT
           (SELECT COUNT(*) FROM turn_usage WHERE started_at >= ?) AS turns_today,
           (SELECT SUM(computed_total_tokens) FROM turn_usage WHERE started_at >= ?) AS tokens_today,
           (SELECT COUNT(*) FROM tool_usage WHERE started_at >= ? AND (error_type IS NOT NULL OR status = 'error')) AS errors_today,
           (SELECT COUNT(*) FROM session) AS sessions_total,
           (SELECT COUNT(*) FROM tool_usage WHERE status = 'running') AS running_tools_now""",
        today_start, today_start, today_start,
    )
    c.close()
    return {
        "generated": now,
        "sessions": sessions,
        "tasks": tasks,
        "runs": runs,
        "tools": tools,
        "sums": sums[0] if sums else {},
    }


# ---------- 页面 ----------

CSS = """
body{margin:0;font:14px/1.5 "Segoe UI","Microsoft YaHei",sans-serif;background:#0f1419;color:#d7dee6}
h1{font-size:18px;margin:0 0 4px} .sub{color:#6b7a88;font-size:12px}
.wrap{max-width:1200px;margin:0 auto;padding:16px}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin:12px 0}
.card{background:#171e26;border:1px solid #26313c;border-radius:8px;padding:10px 14px}
.card b{font-size:20px;display:block} .card span{color:#6b7a88;font-size:12px}
table{width:100%;border-collapse:collapse;background:#171e26;border:1px solid #26313c;border-radius:8px;overflow:hidden;margin-bottom:14px}
th,td{padding:6px 10px;text-align:left;border-bottom:1px solid #222c36;font-size:13px;white-space:nowrap}
th{background:#1d2731;color:#8fa0ae;font-weight:600}
tr:hover td{background:#1b2530}
.pill{display:inline-block;padding:1px 8px;border-radius:10px;font-size:11px}
.running{background:#123b24;color:#4ade80} .done{background:#203040;color:#7dd3fc}
.error{background:#3b1218;color:#f87171} .idle{background:#2a2f36;color:#8fa0ae}
.mono{font-family:Consolas,monospace;font-size:12px} .err-msg{color:#f87171;font-size:12px;max-width:320px;overflow:hidden;text-overflow:ellipsis}
h2{font-size:15px;color:#9fb3c8;margin:18px 0 8px}
"""


def pill(status):
    m = {"running": ("running", "运行中"), "completed": ("done", "完成"),
         "failed": ("error", "失败"), "cancelled": ("idle", "已取消"), "error": ("error", "出错")}
    cls, txt = m.get(status, ("idle", status or "-"))
    return f'<span class="pill {cls}">{txt}</span>'


def render_html(data, live=True):
    d = data
    rows = []
    for s in d["sessions"]:
        if s.get("_err"):
            continue
        status = "running" if s.get("active") else "completed"
        ttype = {"interactive": "交互", "subagent_child": "子代理", "workflow_child": "工作流子任务"}.get(
            s.get("task_type"), s.get("task_type") or "-")
        title = html.escape((s.get("title") or s.get("id") or "")[:40])
        rows.append(
            f'<tr><td>{pill(status)}</td><td>{title}</td><td>{ttype}</td>'
            f'<td class="mono">{fmt_ts(s.get("last_turn"))}</td><td>{s.get("turns") or 0}</td>'
            f'<td>{fmt_tokens(s.get("tokens"))}</td><td>{s.get("tool_errors") or 0}</td></tr>'
        )
    sess_html = "".join(rows) or "<tr><td colspan=7>暂无会话</td></tr>"

    trows = []
    for t in d["tasks"]:
        trows.append(
            f'<tr><td>{pill("running")}</td><td>{html.escape(str(t.get("label") or t.get("phase") or "-"))}</td>'
            f'<td class="mono">{(t.get("parent_session_id") or "")[:20]}</td>'
            f'<td>{html.escape(str(t.get("model") or "-"))}</td><td>{fmt_ts(t.get("time_updated"))}</td></tr>'
        )
    tasks_html = "".join(trows) or "<tr><td colspan=5>无运行中任务</td></tr>"

    rrows = []
    for r in d["runs"]:
        if r.get("_err"):
            continue
        rrows.append(
            f'<tr><td>{pill(r.get("status"))}</td><td>{html.escape((r.get("name") or "")[:46])}</td>'
            f'<td>{r.get("done") or 0}/{r.get("nodes") or 0} 节点</td><td>{r.get("failed") or 0} 失败</td>'
            f'<td>{fmt_tokens(r.get("spent_tokens"))}</td>'
            f'<td>{fmt_dur((r.get("time_updated") or 0) - (r.get("time_created") or 0))}</td>'
            f'<td>{fmt_ts(r.get("time_created"))}</td></tr>'
        )
        for a in r.get("actors", []):
            if not a.get("name"):
                continue
            rrows.append(
                f'<tr><td></td><td style="padding-left:24px;color:#8fa0ae">└ {html.escape(str(a.get("name")))}'
                f' <span class="mono">{(a.get("resolved_model") or "")[:30]}</span></td>'
                f'<td>{pill(a.get("node_status"))}</td><td colspan=4></td></tr>'
            )
    runs_html = "".join(rrows) or "<tr><td colspan=7>无工作流运行</td></tr>"

    xrows = []
    for t in d["tools"]:
        if t.get("_err"):
            continue
        err = t.get("error_type") or t.get("error_message")
        xrows.append(
            f'<tr><td>{pill(t.get("status"))}</td><td class="mono">{html.escape(str(t.get("tool_name")))}</td>'
            f'<td class="mono">{(t.get("session_id") or "")[:20]}</td>'
            f'<td>{fmt_dur(t.get("duration_ms"))}</td>'
            f'<td class="err-msg" title="{html.escape(str(err or ""))}">{html.escape(str(err or ""))}</td></tr>'
        )
    tools_html = "".join(xrows) or "<tr><td colspan=5>无工具调用</td></tr>"

    s = d["sums"]
    cards = (
        f'<div class="card"><b>{sum(1 for x in d["sessions"] if x.get("active"))}</b><span>活跃会话</span></div>'
        f'<div class="card"><b>{s.get("running_tools_now") or 0}</b><span>运行中工具调用</span></div>'
        f'<div class="card"><b>{len(d["tasks"])}</b><span>运行中任务</span></div>'
        f'<div class="card"><b>{s.get("turns_today") or 0}</b><span>今日 turns</span></div>'
        f'<div class="card"><b>{fmt_tokens(s.get("tokens_today"))}</b><span>今日 tokens</span></div>'
        f'<div class="card"><b>{s.get("errors_today") or 0}</b><span>今日错误</span></div>'
        f'<div class="card"><b>{s.get("sessions_total") or 0}</b><span>会话总数</span></div>'
    )

    body = f"""
    <div class="wrap">
      <h1>ZCode 任务监控</h1>
      <div class="sub">本机所有窗口/会话/工作流汇总 · 更新于 {fmt_ts(d["generated"])} · <span id="fresh"></span></div>
      <div class="cards">{cards}</div>
      <h2>会话（最近 30 个）</h2>
      <table><tr><th>状态</th><th>标题</th><th>类型</th><th>最近活动</th><th>turns</th><th>tokens</th><th>错误</th></tr>{sess_html}</table>
      <h2>运行中任务（任务树）</h2>
      <table><tr><th>状态</th><th>任务</th><th>父会话</th><th>模型</th><th>更新时间</th></tr>{tasks_html}</table>
      <h2>动态工作流</h2>
      <table><tr><th>状态</th><th>名称</th><th>节点</th><th>失败</th><th>tokens</th><th>耗时</th><th>创建</th></tr>{runs_html}</table>
      <h2>最近工具调用（含报错）</h2>
      <table><tr><th>状态</th><th>工具</th><th>会话</th><th>耗时</th><th>错误</th></tr>{tools_html}</table>
    </div>"""

    if live:
        return (
            f"<!doctype html><html><head><meta charset='utf-8'>"
            f"<meta http-equiv='refresh' content='3'><style>{CSS}</style>"
            f"<title>ZCode 任务监控</title></head><body>{body}</body></html>"
        )
    return (
        f"<!doctype html><html><head><meta charset='utf-8'>"
        f"<meta http-equiv='refresh' content='5'><style>{CSS}</style>"
        f"<title>ZCode 任务监控</title></head><body>{body}</body></html>"
    )


# ---------- 命令 ----------

def cmd_list_sources(args):
    home = os.path.expanduser("~")
    candidates = [
        DEFAULT_DB,
        os.path.join(home, ".zcode", "cli", "db", "db.sqlite"),
        os.path.join(home, ".zcode", "db.sqlite"),
    ]
    for p in candidates:
        print(("存在" if os.path.exists(p) else "缺失"), p)


def cmd_render(args):
    out = args.o or os.path.join(os.path.expanduser("~"), "Desktop", "task-monitor.html")
    data = load(args.db)
    html = render_html(data, live=False)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"已生成 {out}")
    if not args.no_open:
        subprocess.Popen(["cmd", "/c", "start", "", out])
    print("页面每 5 秒自动刷新。")


class Handler(BaseHTTPRequestHandler):
    db = DEFAULT_DB

    def do_GET(self):
        if self.path == "/api/data":
            body = json.dumps(load(self.db), ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
        else:
            body = render_html(load(self.db), live=True).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        pass


def cmd_serve(args):
    Handler.db = args.db
    srv = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"监控页: http://127.0.0.1:{args.port}  (Ctrl+C 退出)")
    if not args.no_open:
        subprocess.Popen(["cmd", "/c", "start", "", f"http://127.0.0.1:{args.port}"])
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("已退出")


def main():
    ap = argparse.ArgumentParser(description="ZCode 任务监控页")
    ap.add_argument("command", choices=["render", "serve", "list-sources"])
    ap.add_argument("--db", default=DEFAULT_DB)
    ap.add_argument("-o", default=None)
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--no-open", action="store_true")
    args = ap.parse_args()
    if not os.path.exists(args.db):
        print(f"db 不存在: {args.db}\n先用 list-sources 找位置, 或 --db 指定。")
        sys.exit(1)
    {"render": cmd_render, "serve": cmd_serve, "list-sources": cmd_list_sources}[args.command](args)


if __name__ == "__main__":
    main()
