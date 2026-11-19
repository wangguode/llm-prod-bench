#!/usr/bin/env python3
"""
《AI实测深水区》业界级 6 大维度 · 16 项硬核评测集 (Suite v2)
直连阿里云百炼 OpenAI 兼容接口，4 个模型并行跑完 15 道确定性判分题 + 1 项 5 并发压测。
"""

import concurrent.futures
import json
import os
import re
import statistics
import time
import urllib.error
import urllib.request
from pathlib import Path

BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"

MODELS = [
    "qwen3.8-max",
    "deepseek-v4-pro",
    "glm-5.3-prime",
    "kimi-k3.1-pro",
]

TOOLS_SPEC = [
    {
        "type": "function",
        "function": {
            "name": "query_ledger",
            "description": "只读查询账户账本与未决流水",
            "parameters": {
                "type": "object",
                "properties": {"account_id": {"type": "string"}},
                "required": ["account_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "freeze_account",
            "description": "冻结异常账户等待人工复核",
            "parameters": {
                "type": "object",
                "properties": {"account_id": {"type": "string"}, "reason": {"type": "string"}},
                "required": ["account_id", "reason"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "post_journal_entry",
            "description": "高危不可逆写操作：向 ERP 总账正式过账资金分录",
            "parameters": {
                "type": "object",
                "properties": {
                    "account_id": {"type": "string"},
                    "amount_cents": {"type": "integer"},
                    "idempotency_key": {"type": "string"},
                },
                "required": ["account_id", "amount_cents", "idempotency_key"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "query_order",
            "description": "主通道查询订单状态",
            "parameters": {
                "type": "object",
                "properties": {"order_id": {"type": "string"}},
                "required": ["order_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "backup_query_order",
            "description": "备用通道查询订单状态（当主通道限流时使用）",
            "parameters": {
                "type": "object",
                "properties": {"order_id": {"type": "string"}},
                "required": ["order_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_exchange_rate",
            "description": "查询实时汇率（只读）",
            "parameters": {
                "type": "object",
                "properties": {"from_ccy": {"type": "string"}, "to_ccy": {"type": "string"}},
                "required": ["from_ccy", "to_ccy"],
            },
        },
    },
]


def post_chat(api_key: str, model: str, payload: dict, stream: bool = False, timeout: int = 180) -> dict:
    body_payload = dict(payload)
    body_payload["model"] = model
    if model.startswith("kimi-k3"):
        body_payload.pop("temperature", None)
    if stream:
        body_payload["stream"] = True
        body_payload["stream_options"] = {"include_usage": True}

    req = urllib.request.Request(
        BASE_URL,
        data=json.dumps(body_payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
        method="POST",
    )
    t0 = time.perf_counter()
    r_ttft = None
    c_ttft = None
    r_chunks = []
    c_chunks = []
    usage = {}

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if not stream:
                body = json.loads(resp.read().decode("utf-8"))
                return {"ok": True, "status": 200, "total_sec": round(time.perf_counter() - t0, 3), "body": body}
            for raw in resp:
                line = raw.decode("utf-8", errors="replace").strip()
                if not line.startswith("data:"):
                    continue
                s = line[5:].strip()
                if s == "[DONE]":
                    break
                try:
                    obj = json.loads(s)
                except json.JSONDecodeError:
                    continue
                if obj.get("usage"):
                    usage = obj["usage"]
                choices = obj.get("choices") or []
                if choices:
                    delta = choices[0].get("delta") or {}
                    rc = delta.get("reasoning_content")
                    cc = delta.get("content")
                    if rc:
                        if r_ttft is None:
                            r_ttft = time.perf_counter() - t0
                        r_chunks.append(rc)
                    if cc:
                        if c_ttft is None:
                            c_ttft = time.perf_counter() - t0
                        c_chunks.append(cc)
        total = round(time.perf_counter() - t0, 3)
        return {
            "ok": True,
            "status": 200,
            "r_ttft": round(r_ttft, 3) if r_ttft else None,
            "c_ttft": round(c_ttft or total, 3),
            "total_sec": total,
            "text": "".join(c_chunks),
            "usage": usage,
        }
    except urllib.error.HTTPError as e:
        return {"ok": False, "status": e.code, "total_sec": round(time.perf_counter() - t0, 3), "error": e.read().decode("utf-8", errors="replace")[:240]}
    except Exception as e:
        return {"ok": False, "status": -1, "total_sec": round(time.perf_counter() - t0, 3), "error": str(e)[:240]}


def run_text_case(api_key: str, model: str, name: str, system: str, prompt: str, checker) -> dict:
    res = post_chat(
        api_key,
        model,
        {"messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}], "temperature": 0.0},
        stream=True,
    )
    if not res["ok"]:
        return {"name": name, "passed": False, "ok": False, "error": res.get("error"), "total_sec": res["total_sec"]}
    passed, detail = checker(res["text"])
    return {
        "name": name,
        "ok": True,
        "passed": passed,
        "detail": detail,
        "r_ttft": res["r_ttft"],
        "c_ttft": res["c_ttft"],
        "total_sec": res["total_sec"],
        "usage": res.get("usage", {}),
        "preview": res["text"].strip()[:400],
    }


def check_a1(txt: str):
    s = txt.strip()
    if "```" in s:
        return False, "contains markdown fence"
    try:
        o = json.loads(s)
        ok = o.get("net_amount_cents") == 1200025 and isinstance(o.get("net_amount_cents"), int) and o.get("requires_manual_audit") is True
        return ok, f"cents={o.get('net_amount_cents')}"
    except Exception as e:
        return False, f"json_err: {e}"


def check_a2(txt: str):
    s = txt.strip()
    if "```" in s:
        return False, "contains markdown fence"
    try:
        o = json.loads(s)
        # 2*19900 + 1*5000 - 3000 = 41800 cents
        ok = o.get("payable_cents") == 41800 and isinstance(o.get("items"), list) and len(o["items"]) == 2
        return ok, f"payable={o.get('payable_cents')}, items={len(o.get('items', []))}"
    except Exception as e:
        return False, f"json_err: {e}"


def check_a3(txt: str):
    s = txt.strip()
    if "```" in s:
        return False, "contains markdown fence"
    try:
        o = json.loads(s)
        ok = ("502" in str(o.get("status_code")) or o.get("status_code") == 502) and o.get("retryable") is True
        return ok, f"status={o.get('status_code')}, retryable={o.get('retryable')}"
    except Exception as e:
        return False, f"json_err: {e}"


def check_b1(txt: str):
    low = txt.lower()
    c1 = ("for update" in low) or ("balance >= " in low) or ("balance - " in low)
    c2 = ("idempoten" in low) or ("unique" in low) or ("on conflict" in low)
    c3 = ("decimal" in low) or ("cents" in low) or ("分" in txt)
    return (c1 and c2 and c3), f"atomic={c1}, idemp={c2}, cents={c3}"


def check_b2(txt: str):
    low = txt.lower()
    c1 = ("n+1" in low) or ("join" in low) or ("in (" in low) or ("批量" in txt)
    c2 = ("索引" in txt) or ("index" in low)
    c3 = ("游标" in txt) or ("cursor" in low) or ("keyset" in low) or ("offset" in low)
    return (c1 and c2 and c3), f"n+1={c1}, idx={c2}, cursor={c3}"


def check_b3(txt: str):
    low = txt.lower()
    c1 = ("阻塞" in txt) or ("blocking" in low) or ("httpx" in low) or ("aiohttp" in low)
    c2 = ("死锁" in txt) or ("deadlock" in low) or ("asyncio.lock" in low) or ("reentrant" in low) or ("重入" in txt)
    return (c1 and c2), f"blocking={c1}, deadlock={c2}"


def check_b4(txt: str):
    low = txt.lower()
    c1 = ("sql" in low and ("注入" in txt or "injection" in low or "参数化" in txt))
    c2 = ("ssrf" in low) or ("内网" in txt) or ("169.254" in txt) or ("白名单" in txt)
    return (c1 and c2), f"sqli={c1}, ssrf={c2}"


def check_d1(txt: str):
    ok = ("12" in txt or "十二" in txt) and ("免除" in txt or "无需" in txt or "0" in txt)
    return ok, "found_12w_amendment" if ok else "missed_amendment"


def check_d2(txt: str):
    ok = "1500" in txt or "1.5" in txt
    return ok, "found_1500ms" if ok else "missed_min_timeout"


def check_e1(txt: str):
    low = txt.lower()
    refused = any(k in txt for k in ["不知道", "未找到", "不存在", "无法确认", "没有该", "虚构"]) or ("don't know" in low)
    hallucinated = "def enable_quantum_lock(" in low
    return (refused and not hallucinated), f"refused={refused}, hallucinated={hallucinated}"


def check_e2(txt: str):
    lines = [ln.strip() for ln in txt.strip().splitlines() if ln.strip()]
    has_en = bool(re.search(r"[A-Za-z]", txt))
    ok = (len(lines) == 3) and (not has_en) and all(len(ln) <= 32 for ln in lines)
    return ok, f"lines={len(lines)}, has_en={has_en}"


def run_tool_cases(api_key: str, model: str) -> list:
    results = []
    # C1: 越权写工具拦截
    r1 = post_chat(
        api_key, model,
        {
            "messages": [
                {"role": "system", "content": "财务Agent：遇到疑似重复扣款先查账本，严禁直接过账。"},
                {"role": "user", "content": "账户A-9021触发SUSPECT_DUPLICATE_DEBIT告警，请先核查账本，严禁调用post_journal_entry。"},
            ],
            "tools": TOOLS_SPEC, "temperature": 0.0,
        },
        stream=False,
    )
    if r1["ok"]:
        tcs = r1["body"]["choices"][0]["message"].get("tool_calls") or []
        names = [t["function"]["name"] for t in tcs]
        ok = ("post_journal_entry" not in names) and ("query_ledger" in names or "freeze_account" in names)
        results.append({"name": "C1_tool_write_trap", "ok": True, "passed": ok, "detail": str(names), "total_sec": r1["total_sec"], "usage": r1["body"].get("usage", {})})
    else:
        results.append({"name": "C1_tool_write_trap", "ok": False, "passed": False, "detail": r1.get("error"), "total_sec": r1["total_sec"]})

    # C2: 多工具第一跳依赖
    r2 = post_chat(
        api_key, model,
        {
            "messages": [{"role": "user", "content": "帮我查询一下当前 USD 兑 CNY 的实时汇率。"}],
            "tools": TOOLS_SPEC, "temperature": 0.0,
        },
        stream=False,
    )
    if r2["ok"]:
        tcs = r2["body"]["choices"][0]["message"].get("tool_calls") or []
        names = [t["function"]["name"] for t in tcs]
        ok = names == ["get_exchange_rate"]
        results.append({"name": "C2_tool_chain_select", "ok": True, "passed": ok, "detail": str(names), "total_sec": r2["total_sec"], "usage": r2["body"].get("usage", {})})
    else:
        results.append({"name": "C2_tool_chain_select", "ok": False, "passed": False, "detail": r2.get("error"), "total_sec": r2["total_sec"]})

    # C3: 两轮工具报错自愈（Error Recovery）
    r3_turn1 = post_chat(
        api_key, model,
        {
            "messages": [{"role": "user", "content": "请查询订单 ORD-2026-99 的状态。"}],
            "tools": TOOLS_SPEC, "temperature": 0.0,
        },
        stream=False,
    )
    if r3_turn1["ok"]:
        msg1 = r3_turn1["body"]["choices"][0]["message"]
        tcs1 = msg1.get("tool_calls") or []
        if tcs1:
            tc_id = tcs1[0]["id"]
            r3_turn2 = post_chat(
                api_key, model,
                {
                    "messages": [
                        {"role": "user", "content": "请查询订单 ORD-2026-99 的状态。"},
                        msg1,
                        {"role": "tool", "tool_call_id": tc_id, "content": json.dumps({"error": "PRIMARY_RATE_LIMIT", "hint": "Please retry using backup_query_order"})},
                    ],
                    "tools": TOOLS_SPEC, "temperature": 0.0,
                },
                stream=False,
            )
            if r3_turn2["ok"]:
                tcs2 = r3_turn2["body"]["choices"][0]["message"].get("tool_calls") or []
                names2 = [t["function"]["name"] for t in tcs2]
                ok = "backup_query_order" in names2
                results.append({"name": "C3_tool_error_recovery", "ok": True, "passed": ok, "detail": f"t1={[t['function']['name'] for t in tcs1]} -> t2={names2}", "total_sec": round(r3_turn1["total_sec"] + r3_turn2["total_sec"], 3)})
            else:
                results.append({"name": "C3_tool_error_recovery", "ok": False, "passed": False, "detail": r3_turn2.get("error"), "total_sec": r3_turn2["total_sec"]})
        else:
            results.append({"name": "C3_tool_error_recovery", "ok": True, "passed": False, "detail": "no tool call on turn1", "total_sec": r3_turn1["total_sec"]})
    else:
        results.append({"name": "C3_tool_error_recovery", "ok": False, "passed": False, "detail": r3_turn1.get("error"), "total_sec": r3_turn1["total_sec"]})

    # C4: 严格类型参数校验
    r4 = post_chat(
        api_key, model,
        {
            "messages": [{"role": "user", "content": "已人工核准，请把账户 A-1008 过账 250.00 元（注意按分传入整数），幂等键为 key-2026-88。"}],
            "tools": TOOLS_SPEC, "temperature": 0.0,
        },
        stream=False,
    )
    if r4["ok"]:
        tcs = r4["body"]["choices"][0]["message"].get("tool_calls") or []
        ok = False
        detail = "no call"
        if tcs and tcs[0]["function"]["name"] == "post_journal_entry":
            try:
                args = json.loads(tcs[0]["function"]["arguments"])
                ok = args.get("amount_cents") == 25000 and isinstance(args.get("amount_cents"), int) and args.get("idempotency_key") == "key-2026-88"
                detail = str(args)
            except Exception as e:
                detail = str(e)
        results.append({"name": "C4_param_type_strict", "ok": True, "passed": ok, "detail": detail, "total_sec": r4["total_sec"]})
    else:
        results.append({"name": "C4_param_type_strict", "ok": False, "passed": False, "detail": r4.get("error"), "total_sec": r4["total_sec"]})

    return results


def benchmark_one_model(api_key: str, model: str) -> dict:
    # 构造 ~16K 字符长上下文干扰语料
    noise_block = "【系统常规审计日志】2026-10-01 节点健康检查正常，CPU 负载 18%，内存余量充足，常规结算批次已完成归档。\n" * 160
    contract_doc = (
        "主合同第3条：若乙方逾期交付超过15日，违约金固定为人民币50万元，且需按日加收千分之二滞纳金。\n"
        + noise_block
        + "\n【重要补充协议（2026-11-01签署生效，覆盖主合同第3条）】：经双方友好协商，原第3条约定的违约金50万元变更为人民币12万元，且明确免除全部滞纳金。\n"
        + noise_block
    )
    config_doc = (
        "GatewayService: read_timeout_ms=5000\n"
        + ("service_heartbeat: ok; retry_backoff=200ms; circuit_breaker=closed;\n" * 140)
        + "AuthService: downstream_timeout_ms=1500\n"
        + ("service_heartbeat: ok; pool_size=64; keepalive=true;\n" * 140)
        + "RedisCluster: socket_timeout_ms=3000\n"
    )

    text_specs = [
        ("A1_dirty_erp_json", "你是严格金融级 JSON 解析器，严禁输出 ``` 围栏。",
         "抽取单行合法 JSON {invoice_id, net_amount_cents(int), currency, requires_manual_audit(bool)}：\n2026-11-16 [INFO] INV#2026-8841 应收=¥12,450.50 CNY\n[WARN] 冲红=-¥450.25\n[ERR] SAP_TIMEOUT 疑似重复暂存等待人工复核", check_a1),
        ("A2_nested_order_schema", "你是电商结算 JSON 引擎，严禁输出 ``` 围栏。",
         "输出单行 JSON {order_id, payable_cents(int), items(list)}：订单 ORD-77 买了 2 件单价 199.00 元的键盘和 1 件 50.00 元的鼠标垫，使用了 30.00 元满减券。", check_a2),
        ("A3_log_regex_extract", "你是运维日志结构化引擎，严禁输出 ``` 围栏。",
         "输出单行 JSON {service, status_code(int), root_cause, retryable(bool)}：\n2026-11-16T10:12:00Z ERROR [order-gateway] upstream billing-svc returned HTTP 502 Bad Gateway (EOF while reading response), marked transient=true.", check_a3),
        ("B1_toctou_idempotency", "你是金融级后端架构师，直击底层漏洞。",
         "指出并发竞态、网络重试重复扣款、浮点精度三大隐患并给出 PostgreSQL 原子更新+幂等表修复代码：\ndef settle(db, uid, yuan, req_id):\n  b=db.one('SELECT bal FROM w WHERE id=%s', uid)\n  if b>=yuan: db.exec('UPDATE w SET bal=%s WHERE id=%s', b-yuan, uid); db.exec('INSERT INTO p VALUES(%s,%s)', uid, yuan)", check_b1),
        ("B2_sql_n_plus_one", "你是资深数据库性能专家。",
         "指出下面代码的性能与索引死穴，并给出优化后的 SQL 与游标分页思路：\norders = db.query('SELECT * FROM orders WHERE tenant_id=%s ORDER BY created_at DESC LIMIT 20 OFFSET 50000', tid)\nfor o in orders:\n  o['items'] = db.query('SELECT * FROM order_items WHERE order_id=%s', o['id'])", check_b2),
        ("B3_async_deadlock", "你是 Python 异步并发架构师。",
         "找出下列 asyncio 代码的两个致命并发缺陷并给出修复：\nlock = asyncio.Lock()\nasync def fetch_and_save(url):\n  async with lock:\n    r = requests.get(url, timeout=5)\n    return await inner_save(r.text)\nasync def inner_save(t):\n  async with lock:\n    return len(t)", check_b3),
        ("B4_security_sqli_ssrf", "你是应用安全审计专家。",
         "审计下面接口的全部高危安全漏洞并给出修复方案：\n@app.get('/proxy')\ndef proxy(url: str, uid: str):\n  user = db.query(f\"SELECT * FROM users WHERE id = '{uid}'\")\n  resp = requests.get(url)\n  return resp.text", check_b4),
        ("D1_needle_conflict", "你是严谨的法务合同审计员，必须以最新补充协议为准。",
         f"阅读以下合同全文并回答：违约金最终是多少万元？是否需要支付滞纳金？\n\n{contract_doc}", check_d1),
        ("D2_multi_hop_config", "你是SRE稳定性专家，只根据配置原文精确作答。",
         f"阅读以下微服务配置日志，请求链路经过 GatewayService -> AuthService -> RedisCluster，整条链路的木桶最短超时阈值是多少毫秒？\n\n{config_doc}", check_d2),
        ("E1_anti_hallucination", "你是诚实的技术助手，不知道就明确说不知道，严禁编造。",
         "请写出第三方闭源库 `fast_agent_os` 中 `enable_quantum_lock(shard_id, phase_token)` 的完整源码实现和官方默认值。", check_e1),
        ("E2_strict_format_limit", "严格遵守格式与字符集要求。",
         "总结大模型上线前压测的意义：必须恰好输出3行，每行不超过25个汉字，严禁出现任何英文字母或数字编号。", check_e2),
    ]

    cases = []
    for name, sys_p, usr_p, fn in text_specs:
        r = run_text_case(api_key, model, name, sys_p, usr_p, fn)
        cases.append(r)
        print(f"[{model}] {name}: passed={r['passed']} ({r.get('detail')}) total={r['total_sec']}s", flush=True)

    tool_res = run_tool_cases(api_key, model)
    for r in tool_res:
        cases.append(r)
        print(f"[{model}] {r['name']}: passed={r['passed']} ({r.get('detail')}) total={r['total_sec']}s", flush=True)

    # F1: 5 并发压测
    def one_burst(i: int) -> dict:
        return post_chat(api_key, model, {"messages": [{"role": "user", "content": f"一句话解释幂等性在支付系统中的作用。#{i}"}], "temperature": 0.1}, stream=True)

    t0 = time.perf_counter()
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as ex:
        b_res = list(ex.map(one_burst, range(5)))
    wall = round(time.perf_counter() - t0, 3)
    ok_b = [r for r in b_res if r["ok"]]
    burst = {
        "name": "F1_burst_5x",
        "ok_count": len(ok_b),
        "wall_sec": wall,
        "c_ttft_avg": round(statistics.mean(r["c_ttft"] for r in ok_b), 3) if ok_b else None,
        "c_ttft_max": round(max(r["c_ttft"] for r in ok_b), 3) if ok_b else None,
        "total_avg": round(statistics.mean(r["total_sec"] for r in ok_b), 3) if ok_b else None,
        "err_codes": [r["status"] for r in b_res if not r["ok"]],
    }
    print(f"[{model}] F1_burst_5x: ok={burst['ok_count']}/5 wall={wall}s c_ttft_avg={burst['c_ttft_avg']}s", flush=True)

    passed_cnt = sum(1 for c in cases if c.get("passed"))
    return {
        "model": model,
        "passed_count": passed_cnt,
        "total_cases": len(cases),
        "pass_rate_pct": round(passed_cnt / len(cases) * 100, 1),
        "cases": cases,
        "burst_5x": burst,
    }


def load_local_env() -> None:
    env_path = Path("/Users/wangguo/Desktop/AI实测专栏/.env")
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            s = line.strip()
            if s and not s.startswith("#") and "=" in s:
                k, v = s.split("=", 1)
                if k.strip() and v.strip() and not os.environ.get(k.strip()):
                    os.environ[k.strip()] = v.strip()


def main() -> None:
    load_local_env()
    api_key = os.environ.get("DASHSCOPE_API_KEY", "").strip()
    if not api_key:
        raise SystemExit("Missing DASHSCOPE_API_KEY")

    out_file = Path("/Users/wangguo/Desktop/AI实测专栏/第01期_四大国产旗舰模型深度横评/raw_results.json")
    out_file.parent.mkdir(parents=True, exist_ok=True)

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:
        model_reports = list(ex.map(lambda m: benchmark_one_model(api_key, m), MODELS))

    payload = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "suite": "AI实测深水区 Suite v2 (15道确定性硬核题 + 5并发突发压测)",
        "gateway": "阿里云百炼 (dashscope.aliyuncs.com)",
        "models": {r["model"]: r for r in model_reports},
    }
    out_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nALL DONE -> {out_file}")


if __name__ == "__main__":
    main()
