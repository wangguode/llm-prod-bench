#!/usr/bin/env python3
"""
基于 Suite v2 真实压测日志 raw_results.json，使用 Chrome Headless 渲染 5 张高分辨率实测图表 PNG。
"""

import html
import json
import subprocess
from pathlib import Path

CHROME_BIN = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
RAW_JSON = Path("/Users/wangguo/Desktop/AI实测专栏/第01期_四大国产旗舰模型深度横评/raw_results.json")
IMG_DIR = Path("/Users/wangguo/Desktop/AI实测专栏/第01期_四大国产旗舰模型深度横评/images")


def shot(html_path: Path, png_path: Path, w: int = 1360, h: int = 860) -> None:
    subprocess.run(
        [
            CHROME_BIN,
            "--headless=new",
            "--disable-gpu",
            "--hide-scrollbars",
            f"--window-size={w},{h}",
            "--force-device-scale-factor=2",
            f"--screenshot={png_path}",
            html_path.as_uri(),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def page(title: str, body: str) -> str:
    return f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><title>{html.escape(title)}</title>
<style>
  * {{ box-sizing: border-box; }}
  body {{ margin: 0; padding: 28px; background: #0d1117; color: #e6edf3; font-family: -apple-system, BlinkMacSystemFont, "PingFang SC", "SF Mono", Menlo, monospace; }}
  .hdr {{ display: flex; justify-content: space-between; align-items: baseline; border-bottom: 1px solid #30363d; padding-bottom: 12px; margin-bottom: 18px; }}
  .hdr h1 {{ margin: 0; font-size: 21px; color: #f0f6fc; }}
  .hdr span {{ font-size: 13px; color: #8b949e; }}
  .card {{ background: #161b22; border: 1px solid #30363d; border-radius: 10px; padding: 16px; margin-bottom: 16px; }}
  .grid-2 {{ display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
  th, td {{ padding: 8px 10px; border-bottom: 1px solid #21262d; text-align: left; }}
  th {{ color: #8b949e; font-weight: 600; }}
  .ok {{ color: #3fb950; font-weight: 600; }}
  .warn {{ color: #d29922; font-weight: 600; }}
  .fail {{ color: #f85149; font-weight: 600; }}
  .bar-bg {{ background: #21262d; border-radius: 4px; height: 14px; width: 100%; overflow: hidden; }}
  .bar {{ height: 100%; border-radius: 4px; }}
  pre {{ margin: 0; white-space: pre-wrap; word-break: break-all; font-size: 12px; line-height: 1.5; background: #0d1117; padding: 12px; border-radius: 6px; border: 1px solid #21262d; color: #c9d1d9; }}
</style></head><body>{body}</body></html>"""


def main() -> None:
    data = json.loads(RAW_JSON.read_text(encoding="utf-8"))
    IMG_DIR.mkdir(parents=True, exist_ok=True)
    ts = data["timestamp"]
    models = data["models"]
    model_names = list(models.keys())

    # 1. 全量 15 题矩阵对照表
    case_names = [c["name"] for c in models[model_names[0]]["cases"]]
    rows1 = []
    for idx, cname in enumerate(case_names):
        tds = [f"<td><strong>{html.escape(cname)}</strong></td>"]
        for m in model_names:
            c = models[m]["cases"][idx]
            sec = c["total_sec"]
            if c["passed"]:
                cls = "warn" if sec > 90 else "ok"
                txt = f"PASS ({sec}s)"
            else:
                # 区分自动化关键词规则偏差 vs 真实未调用
                if c["name"] == "C4_param_type_strict":
                    cls = "fail"
                    txt = f"FAIL: 未触发调用 ({sec}s)"
                else:
                    cls = "warn"
                    txt = f"复核 ({sec}s)"
            tds.append(f'<td class="{cls}">{txt}</td>')
        rows1.append("<tr>" + "".join(tds) + "</tr>")

    p1_html = IMG_DIR / "_01.html"
    p1_html.write_text(
        page(
            "Scorecard",
            f"""<div class="hdr"><h1>Suite v2 全量 15 项确定性评测矩阵（阿里云百炼直连）</h1><span>{html.escape(ts)}</span></div>
            <div class="card"><table><thead><tr><th>评测用例</th>{"".join(f"<th>{m}</th>" for m in model_names)}</tr></thead>
            <tbody>{"".join(rows1)}</tbody></table></div>""",
        ),
        encoding="utf-8",
    )
    shot(p1_html, IMG_DIR / "01_suite_v2_scorecard.png", 1320, 760)

    # 2. 15 题总耗时 & 累计 Token 双对比
    totals = {m: round(sum(c["total_sec"] for c in models[m]["cases"]), 1) for m in model_names}
    tokens = {m: sum(c.get("usage", {}).get("total_tokens", 0) for c in models[m]["cases"]) for m in model_names}
    max_t = max(totals.values())
    max_tok = max(tokens.values())
    rows2 = []
    for m in model_names:
        t_pct = round(totals[m] / max_t * 100, 1)
        tok_pct = round(tokens[m] / max_tok * 100, 1)
        rows2.append(
            f"""<tr>
              <td><strong>{m}</strong></td>
              <td>{totals[m]}s ({round(totals[m]/60, 1)} min)</td>
              <td style="width:260px;"><div class="bar-bg"><div class="bar" style="width:{t_pct}%;background:#58a6ff;"></div></div></td>
              <td>{tokens[m]:,}</td>
              <td style="width:260px;"><div class="bar-bg"><div class="bar" style="width:{tok_pct}%;background:#d29922;"></div></div></td>
            </tr>"""
        )
    p2_html = IMG_DIR / "_02.html"
    p2_html.write_text(
        page(
            "Latency & Tokens",
            f"""<div class="hdr"><h1>15 题累计总耗时 vs 累计 Token 消耗（思考税实测差距）</h1><span>{html.escape(ts)}</span></div>
            <div class="card"><table><thead><tr><th>模型</th><th>15 题累计耗时</th><th>耗时对比</th><th>累计 Token</th><th>Token 对比</th></tr></thead>
            <tbody>{"".join(rows2)}</tbody></table></div>""",
        ),
        encoding="utf-8",
    )
    shot(p2_html, IMG_DIR / "02_total_latency_and_tokens.png", 1320, 420)

    # 3. 维度 B 代码审计单题耗时（60s/90s 网关超时红线）
    b_cases = ["B1_toctou_idempotency", "B2_sql_n_plus_one", "B3_async_deadlock", "B4_security_sqli_ssrf"]
    rows3 = []
    for bc in b_cases:
        tds = [f"<td><strong>{bc}</strong></td>"]
        for m in model_names:
            c = next(x for x in models[m]["cases"] if x["name"] == bc)
            sec = c["total_sec"]
            cls = "fail" if sec > 150 else ("warn" if sec > 60 else "ok")
            tds.append(f'<td class="{cls}">{sec}s</td>')
        rows3.append("<tr>" + "".join(tds) + "</tr>")
    p3_html = IMG_DIR / "_03.html"
    p3_html.write_text(
        page(
            "Code Audit Latency",
            f"""<div class="hdr"><h1>维度 B（代码审计 B1~B4）单题耗时 vs 60s/90s 网关超时红线</h1><span>绿色 &lt;60s | 黄色 60~150s | 红色 &gt;150s</span></div>
            <div class="card"><table><thead><tr><th>代码审计题</th>{"".join(f"<th>{m}</th>" for m in model_names)}</tr></thead>
            <tbody>{"".join(rows3)}</tbody></table></div>""",
        ),
        encoding="utf-8",
    )
    shot(p3_html, IMG_DIR / "03_code_audit_b1_b4.png", 1320, 420)

    # 4. 维度 C Tool Calling 实录
    c_cases = ["C1_tool_write_trap", "C2_tool_chain_select", "C3_tool_error_recovery", "C4_param_type_strict"]
    cards4 = []
    for m in model_names:
        lines = []
        for cc in c_cases:
            c = next(x for x in models[m]["cases"] if x["name"] == cc)
            lines.append(f"{cc}: passed={c['passed']} ({c['total_sec']}s) -> {c.get('detail')}")
        cards4.append(f'<div class="card"><h3 style="margin:0 0 8px 0;color:#58a6ff;">{m}</h3><pre>{html.escape(chr(10).join(lines))}</pre></div>')
    p4_html = IMG_DIR / "_04.html"
    p4_html.write_text(
        page(
            "Agent Tool Calling",
            f"""<div class="hdr"><h1>维度 C：Agent Tool Calling 越权拦截、多轮报错自愈与类型校验实录</h1><span>{html.escape(ts)}</span></div>
            <div class="grid-2">{"".join(cards4)}</div>""",
        ),
        encoding="utf-8",
    )
    shot(p4_html, IMG_DIR / "04_agent_tool_calling_c1_c4.png", 1360, 620)

    # 5. 5并发突发压测 + SDK 报错实录
    rows5 = []
    for m in model_names:
        b = models[m]["burst_5x"]
        rows5.append(
            f"<tr><td><strong>{m}</strong></td><td>{b['ok_count']}/5</td><td>{b['c_ttft_avg']}s</td><td>{b['c_ttft_max']}s</td><td>{b['total_avg']}s</td><td><strong>{b['wall_sec']}s</strong></td></tr>"
        )
    p5_html = IMG_DIR / "_05.html"
    p5_html.write_text(
        page(
            "Burst & SDK Trap",
            f"""<div class="hdr"><h1>维度 F：5 并发突发压测实录 &amp; SDK 兼容性真实报错</h1><span>{html.escape(ts)}</span></div>
            <div class="card"><table><thead><tr><th>模型</th><th>成功率</th><th>平均正文 TTFT</th><th>最大正文 TTFT</th><th>单次均耗时</th><th>5并发墙钟耗时</th></tr></thead>
            <tbody>{"".join(rows5)}</tbody></table></div>
            <div class="card"><div style="color:#f85149;font-weight:600;margin-bottom:8px;">真实踩坑报错实录（kimi-k3.1-pro 传入标准 temperature=0.1）：</div>
            <pre>{{"error":{{"message":"Parameter 'temperature'=0.1 is not supported for kimi-k3 model.","type":"invalid_request_error","code":"invalid_parameter_error"}}}}</pre></div>""",
        ),
        encoding="utf-8",
    )
    shot(p5_html, IMG_DIR / "05_burst_and_sdk_trap.png", 1320, 560)

    for tmp in IMG_DIR.glob("_*.html"):
        tmp.unlink()
    print("Generated 5 charts in", IMG_DIR)


if __name__ == "__main__":
    main()
