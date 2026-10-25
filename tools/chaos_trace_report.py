"""把卡厄思流程追踪目录（dev_out/chaos_trace/<时间>/trace.jsonl + 截图）生成一页 HTML，供人工审阅。

用法：python tools/chaos_trace_report.py [追踪目录]   不给目录就用 dev_out/chaos_trace 下最新的一个；输出 <目录>/index.html
"""
import html
import json
import os
import sys

KIND_NAME = {"map": "地图", "route": "路线", "event": "事件", "card": "选卡", "page": "页面"}


def load(path):
    steps, cur = [], None
    with open(os.path.join(path, "trace.jsonl"), encoding="utf-8") as f:
        for line in f:
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            if rec.get("kind") == "log":
                if cur is None:
                    cur = {"kind": "start", "title": "启动", "logs": [], "data": {}}
                    steps.append(cur)
                cur["logs"].append(rec)
            else:
                cur = dict(rec, logs=[])
                steps.append(cur)
    return steps


def esc(s):
    return html.escape(str(s))


def render_step(st):
    d = st.get("data") or {}
    kind = st.get("kind")
    parts = [f'<section class="step {esc(kind)}" id="s{st.get("seq", 0)}">',
             f'<h3><span class="tag">{esc(KIND_NAME.get(kind, kind))}</span> {esc(st.get("title", ""))}'
             f'<small> #{st.get("seq", "")} {esc(st.get("t", ""))} · 第{st.get("round", 0) + 1}轮 第{st.get("layer", "?")}层'
             f' 节点{st.get("node", "?")}</small></h3>']
    if kind == "event":
        rows = []
        for i, o in enumerate(d.get("options", [])):
            cls = ' class="chosen"' if i == d.get("chosen") else ""
            rows.append(f"<tr{cls}><td>{'✔' if cls else ''}</td><td>{esc(o['desc'])}</td><td>{o['score']:+g}</td>"
                        f"<td>{esc(' '.join(o.get('why') or []) or '无效果')}</td><td>{esc(o.get('src', ''))}</td></tr>")
        parts.append("<table><tr><th></th><th>选项</th><th>分</th><th>理由</th><th>来源</th></tr>"
                     + "".join(rows) + "</table>")
    elif kind == "route":
        parts.append(f"<p>路线（总分 {esc(d.get('score'))}）：<b>{esc(' → '.join(d.get('path', [])))}</b>"
                     f"　节点 id：{esc(d.get('route'))}</p>")
    elif kind == "map":
        cols = {}
        for n in d.get("nodes", []):
            cols.setdefault(n.get("col"), []).append(f"{n['id']}:{n['type']}{'[商店]' if n.get('special_features') else ''}")
        parts.append("<p>" + " | ".join(f"列{c}: {', '.join(v)}" for c, v in sorted(cols.items(), key=lambda x: x[0]))
                     + f"</p><p>连线：{esc(d.get('adjacency'))}</p>")
    elif kind == "card":
        parts.append(f"<p>点 <b>{esc(d.get('chosen'))}</b>（{esc(d.get('reason'))}）　当前页卡牌：{esc(d.get('cards'))}</p>")
    if st.get("img"):
        parts.append(f'<a href="{esc(st["img"])}" target="_blank"><img loading="lazy" src="{esc(st["img"])}"></a>')
    if st["logs"]:
        parts.append(f"<details><summary>日志 {len(st['logs'])} 行</summary><pre>"
                     + "\n".join(esc(f"{l['t']} {l['msg']}") for l in st["logs"]) + "</pre></details>")
    parts.append("</section>")
    return "\n".join(parts)


def render(path):
    steps = load(path)
    decisions = [s for s in steps if s.get("kind") in ("route", "event", "card")]
    summary = []
    for s in decisions:
        d = s.get("data") or {}
        if s["kind"] == "event":
            o = (d.get("options") or [{}])[d.get("chosen", 0)] if d.get("options") else {}
            what = f"{o.get('desc', '')}（{o.get('score', 0):+g}）"
        elif s["kind"] == "route":
            what = " → ".join(d.get("path", []))
        else:
            what = f"{d.get('chosen')}（{d.get('reason')}）"
        summary.append(f'<tr><td><a href="#s{s["seq"]}">#{s["seq"]}</a></td><td>{s.get("layer")}</td>'
                       f'<td>{esc(KIND_NAME[s["kind"]])}</td><td>{esc(s.get("title", ""))}</td><td>{esc(what)}</td></tr>')
    css = """
:root{--bg:#fff;--fg:#1d1d1f;--mut:#6e6e73;--line:#ddd;--hi:#fff4c2;--tag:#0a5bd8}
@media (prefers-color-scheme:dark){:root{--bg:#18181a;--fg:#ececec;--mut:#9a9aa0;--line:#333;--hi:#4a3f12;--tag:#6ea8ff}}
body{background:var(--bg);color:var(--fg);font:14px/1.5 -apple-system,"PingFang SC",sans-serif;margin:0 auto;max-width:1320px;padding:16px}
h3{margin:8px 0;font-size:15px} small{color:var(--mut);font-weight:normal}
.tag{color:var(--tag)} .step{border-top:1px solid var(--line);padding:8px 0}
img{max-width:100%;border:1px solid var(--line)} table{border-collapse:collapse;width:100%;margin:6px 0}
td,th{border:1px solid var(--line);padding:3px 6px;text-align:left;vertical-align:top} tr.chosen{background:var(--hi)}
pre{white-space:pre-wrap;font-size:12px;color:var(--mut)} .page h3{font-size:13px}
"""
    out = [f"<!doctype html><meta charset='utf-8'><meta name='viewport' content='width=device-width'>"
           f"<title>卡厄思流程 {esc(os.path.basename(path))}</title><style>{css}</style>",
           f"<h1>卡厄思流程追踪 {esc(os.path.basename(path))}</h1>",
           f"<p>{len(steps)} 条记录，{len(decisions)} 个决策。</p>",
           "<h2>决策一览</h2><table><tr><th>#</th><th>层</th><th>类</th><th>标题</th><th>选择</th></tr>"
           + "".join(summary) + "</table><h2>全过程</h2>"]
    out += [render_step(s) for s in steps]
    dst = os.path.join(path, "index.html")
    with open(dst, "w", encoding="utf-8") as f:
        f.write("\n".join(out))
    return dst


if __name__ == "__main__":
    if len(sys.argv) > 1:
        target = sys.argv[1]
    else:
        root = os.path.join("dev_out", "chaos_trace")
        target = os.path.join(root, sorted(os.listdir(root))[-1])
    print(render(target))
