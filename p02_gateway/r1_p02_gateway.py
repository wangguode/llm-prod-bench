#!/usr/bin/env python3
"""第02期 第一轮实测（百炼侧，最省口径）：
T1 流式 TTFT：qwen3.8-max / qwen3.8-flash 各 N=20（思考关闭）
T2 tools / T3 json_object：每模型各 5 次（非流式）
T4 限流：仅 qwen3.8-flash 短请求，10→20→50→100 路逐级突发；首次出现 429 即停止加压；100 路仍无 429 也停止。429 不重试。"""
import sys, time, concurrent.futures as cf
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "_common_r1"))
from benchlib_r1 import setup, parse_json_strict

r = setup("p02_r1")
MODELS = [("qwen3.8-max", {"enable_thinking": False}), ("qwen3.8-flash", {"enable_thinking": False})]
TOOL = [{"type": "function", "function": {"name": "query_order", "description": "查询订单状态",
         "parameters": {"type": "object", "properties": {"order_id": {"type": "string"}}, "required": ["order_id"]}}}]
for model, extra in MODELS:
    for i in range(20):
        r.call_r(f"T1_stream_ttft_{i:02d}", "dashscope", model, {"messages": [{"role": "user", "content": f"用一句话说明什么是幂等键。#{i}"}], "max_tokens": 64, **extra}, stream=True, max_out=64)
    for i in range(5):
        rec = r.call_r(f"T2_tools_{i}", "dashscope", model, {"messages": [{"role": "user", "content": f"帮我查订单 ORD-77 的状态（第{i}次）"}], "tools": TOOL, "max_tokens": 128, **extra}, stream=False, max_out=128)
        tc = rec.get("tool_calls") or []
        rec["check"] = {"passed": bool(tc) and tc[0].get("name") == "query_order" and "ORD-77" in (tc[0].get("arguments") or "")}
        r.log(f"  check={rec['check']}")
    for i in range(5):
        rec = r.call_r(f"T3_json_{i}", "dashscope", model, {"messages": [{"role": "system", "content": "只输出 JSON"}, {"role": "user", "content": f"把“张三，订单金额 199.5 元”转成 JSON，字段 name, amount_cents(整数)。（第{i}次）"}],
                       "response_format": {"type": "json_object"}, "max_tokens": 128, **extra}, stream=False, max_out=128)
        o, why = parse_json_strict(rec.get("text"))
        rec["check"] = {"parse": why, "passed": bool(o) and o.get("amount_cents") == 19950}
        r.log(f"  check={rec['check']}")
for n in (10, 20, 50, 100):
    t0 = time.perf_counter()
    with cf.ThreadPoolExecutor(max_workers=n) as ex:
        futs = [ex.submit(r.call, f"T4_burst{n}_{i:03d}", "dashscope", "qwen3.8-flash",
                          {"messages": [{"role": "user", "content": f"回复“OK{i}”"}], "max_tokens": 16, "enable_thinking": False}, True, 120, 16) for i in range(n)]
        res = [f.result() for f in futs]
    wall = round(time.perf_counter() - t0, 3)
    sts = [x.get("status") for x in res]
    n429 = sum(1 for s in sts if s == 429)
    r.records.append({"case": f"T4_burst{n}_summary", "model": "qwen3.8-flash", "n": n, "wall_sec": wall, "statuses": sts, "n_429": n429,
                      "errors_sample": [x.get("error") for x in res if x.get("error")][:3]})
    r.log(f"T4 burst{n} wall={wall}s 200={sts.count(200)} 429={n429} other={[s for s in sts if s not in (200, 429)]}")
    if n429 or any(x.get("sent") is False for x in res):
        r.log(f"T4 stop at burst{n}"); break
r.save({"design": __doc__})
