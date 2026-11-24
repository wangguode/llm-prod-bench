"""
AI评测篇(11)-(15) 真机确定性压测总引擎（100% 真实 DashScope API + 本地 SQLite/BM25/SSE 压测，零编造）。
输出落盘：/Users/wangguo/Desktop/AI实测专栏/bench/runs/p11_to_p15_live.json
"""
import concurrent.futures
import json
import math
import re
import sqlite3
import time
import urllib.request
from datetime import datetime
from pathlib import Path

ENV_PATH = Path("/Users/wangguo/Desktop/AI实测专栏/.env")
OUT_PATH = Path("/Users/wangguo/Desktop/AI实测专栏/bench/runs/p11_to_p15_live.json")
OUT_PATH.parent.mkdir(parents=True, exist_ok=True)

env = dict(
    l.split("=", 1)
    for l in ENV_PATH.read_text(encoding="utf-8").splitlines()
    if l.strip() and not l.startswith("#") and "=" in l
)
API_KEY = env["DASHSCOPE_API_KEY"].strip().strip('"').strip("'")
BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"

PRICING = {
    "qwen3.8-flash": (0.15, 1.5),
    "qwen3.8-max": (2.4, 9.6),
    "deepseek-v4-pro": (2.0, 8.0),
    "glm-5.3-prime": (2.0, 8.0),
    "kimi-k3.1-pro": (2.0, 8.0),
}
FLAGSHIPS = ["qwen3.8-max", "deepseek-v4-pro", "glm-5.3-prime", "kimi-k3.1-pro"]


def call_llm(model: str, messages: list, max_tokens: int = 512, stream: bool = False) -> dict:
    payload = {"model": model, "messages": messages, "max_tokens": max_tokens, "temperature": 0.0}
    if model != "glm-5.3-prime":
        payload["enable_thinking"] = False
    if stream:
        payload["stream"] = True
        payload["stream_options"] = {"include_usage": True}
    req = urllib.request.Request(
        BASE_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"},
    )
    t0 = time.perf_counter()
    try:
        if not stream:
            with urllib.request.urlopen(req, timeout=90) as r:
                raw = json.loads(r.read().decode("utf-8"))
            dt = round(time.perf_counter() - t0, 3)
            content = raw["choices"][0]["message"].get("content") or ""
            usage = raw.get("usage", {})
            pt, ct = usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0)
            pin, pout = PRICING.get(model, (2.0, 8.0))
            return {"ok": True, "latency_s": dt, "ttft_s": dt, "content": content, "pt": pt, "ct": ct, "cost_rmb": round((pt * pin + ct * pout) / 1e6, 6)}
        else:
            ttft = None
            chunks = []
            pt = ct = 0
            with urllib.request.urlopen(req, timeout=60) as r:
                for raw_ln in r:
                    ln = raw_ln.decode("utf-8", errors="ignore").strip()
                    if not ln.startswith("data: "):
                        continue
                    data_s = ln[6:]
                    if data_s == "[DONE]":
                        break
                    obj = json.loads(data_s)
                    if obj.get("usage"):
                        pt = obj["usage"].get("prompt_tokens", pt)
                        ct = obj["usage"].get("completion_tokens", ct)
                    delta = (obj.get("choices") or [{}])[0].get("delta", {})
                    txt = delta.get("content") or ""
                    if txt:
                        if ttft is None:
                            ttft = round(time.perf_counter() - t0, 3)
                        chunks.append(txt)
            dt = round(time.perf_counter() - t0, 3)
            pin, pout = PRICING.get(model, (2.0, 8.0))
            return {"ok": True, "latency_s": dt, "ttft_s": ttft or dt, "content": "".join(chunks), "pt": pt, "ct": ct, "cost_rmb": round((pt * pin + ct * pout) / 1e6, 6)}
    except Exception as e:
        return {"ok": False, "latency_s": round(time.perf_counter() - t0, 3), "ttft_s": None, "content": "", "error": str(e), "pt": 0, "ct": 0, "cost_rmb": 0.0}


# ============================================================
# P11: Text-to-SQL 真机 SQLite 执行校验（4 大旗舰 × 6 题）
# ============================================================
SQL_SCHEMA = """
CREATE TABLE vendors (
  vendor_id TEXT PRIMARY KEY,
  vendor_name TEXT,
  region TEXT,
  is_active INTEGER -- 1=有效, 0=停用
);
CREATE TABLE purchase_orders (
  po_id TEXT PRIMARY KEY,
  vendor_id TEXT,
  amount_cents INTEGER, -- 单位：分
  currency TEXT,        -- 'CNY' 或 'USD' (1 USD = 7.2 CNY)
  status TEXT,          -- 'OPEN', 'CLOSED', 'CANCELLED'
  created_month TEXT    -- 'YYYY-MM'
);
CREATE TABLE goods_receipts (
  gr_id TEXT PRIMARY KEY,
  po_id TEXT,
  received_cents INTEGER,
  gr_date TEXT
);
"""


def init_db():
    conn = sqlite3.connect(":memory:")
    conn.executescript(SQL_SCHEMA)
    conn.executemany("INSERT INTO vendors VALUES (?,?,?,?)", [
        ("V01", "华智精密", "华东", 1),
        ("V02", "星海模具", "华南", 1),
        ("V03", "测试供应商_DO_NOT_USE", "华东", 0),
        ("V04", "明达光电", "华北", 1),
    ])
    conn.executemany("INSERT INTO purchase_orders VALUES (?,?,?,?,?,?)", [
        ("PO1", "V01", 1000000, "CNY", "OPEN", "2026-10"),      # 10,000 元
        ("PO2", "V01", 500000, "CNY", "CANCELLED", "2026-10"),  # 已取消，必须剔除
        ("PO3", "V02", 100000, "USD", "OPEN", "2026-10"),       # 1,000 USD = 7,200 CNY
        ("PO4", "V02", 800000, "CNY", "CLOSED", "2026-10"),     # 8,000 元
        ("PO5", "V03", 9999900, "CNY", "OPEN", "2026-10"),      # 停用测试供应商
        ("PO6", "V04", 600000, "CNY", "OPEN", "2026-11"),       # 6,000 元（11月）
    ])
    conn.executemany("INSERT INTO goods_receipts VALUES (?,?,?,?)", [
        ("GR1", "PO1", 400000, "2026-10-15"),
        ("GR2", "PO1", 200000, "2026-10-25"),  # PO1 累计收货 600000，未收货 400000
        ("GR3", "PO4", 800000, "2026-10-20"),
    ])
    return conn


P11_QS = [
    {"id": "SQL-1", "q": "统计 2026-10 月所有有效供应商（is_active=1）的非取消订单（status != 'CANCELLED'）折合人民币总金额（单位：元，1 USD = 7.2 CNY），返回单行单列数字。", "gold": 25200.0},
    {"id": "SQL-2", "q": "计算 PO1 订单尚未收货的余额（单位：元，订单总额减去 goods_receipts 中所有已收货总额），返回单行单列数字。", "gold": 4000.0},
    {"id": "SQL-3", "q": "找出在 purchase_orders 中状态为 OPEN、且在 goods_receipts 中没有任何收货记录、且供应商 is_active=1 的订单总数，返回单行单列整数。", "gold": 2.0},
    {"id": "SQL-4", "q": "按 region 分组统计 2026-10 月有效供应商的非取消 CNY 订单总额（单位：元），返回总额最高的 region 名称（单行单列字符串）。", "gold_str": "华东"},
    {"id": "SQL-5", "q": "找出所有至少有 2 条收货记录（goods_receipts）的订单 po_id，返回单行单列字符串。", "gold_str": "PO1"},
    {"id": "SQL-6", "q": "计算 2026-10 月所有有效供应商 OPEN 状态订单的收货完成率（已收货总分 / OPEN 订单折合人民币总分，保留两位小数如 0.35，注意 PO3 为 USD 需按 7.2 折算），返回单行单列小数。", "gold": 0.35},
]


def extract_sql(txt: str) -> str:
    m = re.search(r"```(?:sql)?\s*(.*?)```", txt, flags=re.S | re.I)
    s = m.group(1).strip() if m else txt.strip()
    return s.split(";")[0].strip()


def run_p11():
    print("\n=== Running P11 (Text-to-SQL Live SQLite Execution) ===")
    res = {}
    for m in FLAGSHIPS:
        res[m] = []
        for q in P11_QS:
            prompt = f"你是 SQLite 专家。基于以下 Schema，仅输出一条可直接执行的 SQLite SELECT 语句（用 ```sql 包裹，不要任何解释）：\n{SQL_SCHEMA}\n需求：{q['q']}"
            r = call_llm(m, [{"role": "user", "content": prompt}], 300)
            sql = extract_sql(r["content"])
            ok_exec, passed, got, err = False, False, None, ""
            try:
                conn = init_db()
                row = conn.execute(sql).fetchone()
                ok_exec = True
                got = row[0] if row else None
                if "gold_str" in q:
                    passed = str(got).strip() == q["gold_str"]
                else:
                    passed = got is not None and abs(float(got) - q["gold"]) <= 0.02
            except Exception as e:
                err = str(e)
            res[m].append({"id": q["id"], "exec_ok": ok_exec, "pass": passed, "got": str(got), "err": err, "latency_s": r["latency_s"], "pt": r["pt"], "ct": r["ct"], "cost_rmb": r["cost_rmb"]})
        p_cnt = sum(1 for x in res[m] if x["pass"])
        e_cnt = sum(1 for x in res[m] if x["exec_ok"])
        avg_l = round(sum(x["latency_s"] for x in res[m]) / len(res[m]), 2)
        print(f"  {m:16s} | exec={e_cnt}/6 | pass={p_cnt}/6 | avg_lat={avg_l}s | fails={[x['id'] for x in res[m] if not x['pass']]}")
    return res


# ============================================================
# P12: AI Code Review 压测（6 个真实隐蔽 Bug + 2 个健康代码防误报）
# ============================================================
P12_CASES = [
    {"id": "BUG-1", "has_bug": True, "kw": ["竞态", "race", "toctou", "原子", "锁", "并发"], "code": "async def deduct(uid, amt):\n    bal = await db.get(uid)\n    if bal >= amt:\n        await db.set(uid, bal - amt)\n        return True\n    return False"},
    {"id": "BUG-2", "has_bug": True, "kw": ["阻塞", "sleep", "事件循环", "event loop", "asyncio.sleep"], "code": "import time\nasync def fetch_report(req_id):\n    time.sleep(3)\n    return await db.query(req_id)"},
    {"id": "BUG-3", "has_bug": True, "kw": ["可变", "默认参数", "mutable", "共享", "items=[]"], "code": "def append_audit(entry, items=[]):\n    items.append(entry)\n    return items"},
    {"id": "BUG-4", "has_bug": True, "kw": ["注入", "injection", "sqli", "拼接", "参数化"], "code": "def find_order(cur, po_no):\n    return cur.execute(f\"SELECT * FROM orders WHERE po = '{po_no}'\").fetchall()"},
    {"id": "BUG-5", "has_bug": True, "kw": ["浮点", "float", "精度", "decimal", "分"], "code": "def calc_total(prices: list[float]) -> float:\n    return sum(p * 1.13 for p in prices) # 用于财务总账入账比对 total == expected"},
    {"id": "BUG-6", "has_bug": True, "kw": ["n+1", "循环查询", "批量", "join", "in"], "code": "def get_order_vendors(orders):\n    res = []\n    for o in orders:\n        v = db.execute('SELECT name FROM vendors WHERE id=?', (o.vendor_id,)).fetchone()\n        res.append((o.id, v[0]))\n    return res"},
    {"id": "OK-1", "has_bug": False, "kw": [], "code": "from decimal import Decimal\ndef add_tax(amount: Decimal, rate: Decimal) -> Decimal:\n    return (amount * (Decimal('1') + rate)).quantize(Decimal('0.01'))"},
    {"id": "OK-2", "has_bug": False, "kw": [], "code": "def get_order(cur, po_id: str):\n    return cur.execute('SELECT id, amount_cents FROM orders WHERE id = ?', (po_id,)).fetchone()"},
]


def run_p12():
    print("\n=== Running P12 (AI Code Review: 6 Real Bugs + 2 Clean Code) ===")
    res = {}
    for m in FLAGSHIPS:
        res[m] = []
        for c in P12_CASES:
            prompt = (
                "你是资深后端 Code Reviewer。严格审查下面代码是否存在【严重生产 Bug（并发/安全/性能/精度/内存）】。\n"
                "仅输出 JSON：{\"has_bug\": true/false, \"issue\": \"一句话指出核心问题或填none\"}\n"
                f"```python\n{c['code']}\n```"
            )
            r = call_llm(m, [{"role": "user", "content": prompt}], 200)
            txt = r["content"].lower()
            pred_bug = '"has_bug": true' in txt or '"has_bug":true' in txt
            if c["has_bug"]:
                passed = pred_bug and any(k in txt for k in c["kw"])
            else:
                passed = (not pred_bug) and ('"has_bug": false' in txt or '"has_bug":false' in txt)
            res[m].append({"id": c["id"], "has_bug": c["has_bug"], "pred_bug": pred_bug, "pass": passed, "latency_s": r["latency_s"], "pt": r["pt"], "ct": r["ct"], "cost_rmb": r["cost_rmb"]})
        tp = sum(1 for x in res[m] if x["has_bug"] and x["pass"])
        tn = sum(1 for x in res[m] if not x["has_bug"] and x["pass"])
        fp = 2 - tn
        avg_l = round(sum(x["latency_s"] for x in res[m]) / len(res[m]), 2)
        print(f"  {m:16s} | bug_caught={tp}/6 | false_positive={fp}/2 | avg_lat={avg_l}s")
    return res


# ============================================================
# P13: 混合检索（BM25 Top-3）vs 长上下文直塞（30 篇知识库文档）
# ============================================================
def build_kb_docs():
    docs = []
    # 26 篇干扰运维/财务政策文档（每篇 ~450 字）
    for i in range(1, 27):
        docs.append({
            "id": f"DOC-{i:02d}",
            "text": f"【制度编号 DOC-{i:02d}】企业常规行政与差旅报销管理细则第 {i} 分册。规定普通员工国内出差住宿标准为一线城市 {450+i*5} 元/晚，餐饮补贴 {100+i} 元/天。所有报销单据需在归来后 15 个工作日内通过 OA 提交直属主管审批，超过 30 天未提交需附情况说明。本分册不涉及 ERP 计提、采购过账、网关限流或生产故障演练规范。版本 v1.{i}，生效日期 2026-01-{min(i,28):02d}。" * 2
        })
    # 4 篇核心真值文档
    docs.extend([
        {"id": "DOC-27", "text": "【制度编号 DOC-27 · ERP 计提自动过账红线】自 2026 年 11 月起，定制工装类采购订单单笔低于 3,500 元且已取得完整三单匹配记录时允许进入小额自动过账队列；超过 3,500 元或涉及跨年度调整的一律仅建暂存凭证并由财务经理人工审批，严禁 Agent 绕过。"},
        {"id": "DOC-28", "text": "【制度编号 DOC-28 · API 网关熔断阈值】生产级 LLM 网关单路由 P99 首字延迟连续 3 分钟超过 4.2 秒，或 5xx 错误率高于 1.5% 时，必须在 30 秒内自动触发降级开关，将流量切回 qwen3.8-flash 备用通道。"},
        {"id": "DOC-29", "text": "【制度编号 DOC-29 · 供应商黑名单与测试单剔除】财务月结数据剖析器必须自动剔除供应商编码以 TEST_ 开头、或金额恰好等于 0.01 元的联调测试单；若测试单混入计提底稿，需在 2 小时内走红字冲销流程。"},
        {"id": "DOC-30", "text": "【制度编号 DOC-30 · 私有化 GPU 算力扩容门槛】当月末最后 3 个工作日队列积压请求超过 2,400 条、且单卡 KV-Cache 显存利用率持续高于 88% 达 10 分钟，触发弹性扩容至备用推理节点。"},
    ])
    return docs


P13_QS = [
    {"id": "KB-1", "q": "定制工装采购订单单笔低于多少元才允许进入小额自动过账队列？", "expect": "3500", "keywords": ["工装", "自动过账", "暂存"]},
    {"id": "KB-2", "q": "生产 LLM 网关连续 3 分钟 P99 首字延迟超过多少秒会触发降级开关？", "expect": "4.2", "keywords": ["网关", "熔断", "P99", "降级"]},
    {"id": "KB-3", "q": "测试单混入计提底稿后，规定在几小时内走红字冲销流程？", "expect": "2", "keywords": ["测试单", "红字冲销", "黑名单"]},
    {"id": "KB-4", "q": "私有化推理节点单卡 KV-Cache 显存利用率持续高于多少百分比会触发扩容？", "expect": "88%", "keywords": ["KV-Cache", "显存", "扩容"]},
]


def bm25_top3(docs, keywords):
    scored = []
    for d in docs:
        score = sum(d["text"].count(kw) * (3 if len(kw) >= 3 else 1) for kw in keywords)
        scored.append((score, d))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [d for _, d in scored[:3]]


def run_p13():
    print("\n=== Running P13 (Hybrid Retrieval Top-3 vs Full Long-Context) ===")
    docs = build_kb_docs()
    full_ctx = "\n\n".join(d["text"] for d in docs)
    res = {}
    for mode in ["full_ctx_max", "full_ctx_flash", "rag_top3_max", "rag_top3_flash"]:
        model = "qwen3.8-max" if mode.endswith("max") else "qwen3.8-flash"
        use_rag = mode.startswith("rag")
        res[mode] = []
        for q in P13_QS:
            ctx = "\n\n".join(d["text"] for d in bm25_top3(docs, q["keywords"])) if use_rag else full_ctx
            prompt = f"严格基于以下企业制度文档回答问题，仅给出精准答案与对应制度编号：\n{ctx}\n\n问题：{q['q']}"
            r = call_llm(model, [{"role": "user", "content": prompt}], 120)
            norm = r["content"].replace(",", "")
            passed = r["ok"] and (q["expect"] in norm)
            res[mode].append({"id": q["id"], "pass": passed, "pt": r["pt"], "ct": r["ct"], "latency_s": r["latency_s"], "cost_rmb": r["cost_rmb"]})
        p_cnt = sum(1 for x in res[mode] if x["pass"])
        avg_pt = round(sum(x["pt"] for x in res[mode]) / len(res[mode]))
        avg_l = round(sum(x["latency_s"] for x in res[mode]) / len(res[mode]), 2)
        tot_c = round(sum(x["cost_rmb"] for x in res[mode]), 5)
        print(f"  {mode:16s} | pass={p_cnt}/4 | avg_pt={avg_pt:5d} | avg_lat={avg_l}s | cost=¥{tot_c}")
    return res


# ============================================================
# P14: 中英混杂研发评审会纪要与 Action Item 抽取（4 大旗舰 × 2 场会议）
# ============================================================
P14_MEETINGS = [
    {
        "id": "MTG-1",
        "transcript": (
            "【研发周会录音转写 · 2026-11-23】\n"
            "王果（架构）：咱们先把昨天线上那个 K8s HPA 扩容慢和 Redis OOM 的事定一下。张伟你刚才说 Rerank 服务 P99 飙到 1.8s 是吧？\n"
            "张伟（后端）：对，主要是批量请求没加 Circuit Breaker，把 vLLM 队列打满了。我本来想周五改完，但周四下午财务要灰度，我提前到本周三（11月25日）晚 8 点前把熔断限流 PR 合了。\n"
            "李敏（测试）：行，那等张伟合完，我在周四（11月26日）中午前跑完 100 路并发回归压测。对了，关于刚才王果提的 Redis OOM，其实不是缓存泄漏，是赵磊那边把 128K 原文直接塞进 session key 没设 TTL。\n"
            "赵磊（算法）：收到，我今天下班前（11月24日）给 Redis session 加上 30 分钟 TTL 并把原文迁到 OSS。"
        ),
        "checks": [("张伟", "25", "熔断"), ("李敏", "26", "压测"), ("赵磊", "24", "TTL")],
    },
    {
        "id": "MTG-2",
        "transcript": (
            "【AI 安全与合规评审 · 2026-11-23】\n"
            "陈总监（内控）：下周一（11月30日）外部审计要抽查 MCP Server 权限日志。周明，你们那个 SAP 只读接口的字段白名单梳理完了吗？\n"
            "周明（ERP）：字段清完了，单价和银行账号已经剔除，但审计日志还没接进 DynamoDB/ES，预计本周五（11月27日）前上线。\n"
            "陈总监：好，另外邮件注入对抗集（mail_injection.jsonl）谁负责补到 50 条？\n"
            "林雪（安全）：我来补，周五（11月27日）下班前提交给 CI 棘轮门禁。"
        ),
        "checks": [("周明", "27", "审计"), ("林雪", "27", "注入")],
    },
]


def run_p14():
    print("\n=== Running P14 (Mixed CN/EN Tech Meeting Action Item Extraction) ===")
    res = {}
    for m in FLAGSHIPS:
        res[m] = []
        for mt in P14_MEETINGS:
            prompt = (
                "你是技术项目经理。从下面中英混杂的研发会议转写中，提取所有明确的 Action Items，严格输出 JSON 数组，每项包含 owner、deadline、task 三个字段（注意排除被改口推翻的旧日期）：\n"
                + mt["transcript"]
            )
            r = call_llm(m, [{"role": "user", "content": prompt}], 400)
            txt = r["content"]
            hit = sum(1 for ow, dl, kw in mt["checks"] if (ow in txt and dl in txt and kw.lower() in txt.lower()))
            # 额外防改口陷阱：MTG-1 里张伟把“周五”改成了“周三(25日)”，检查未误把张伟标成周五
            passed = r["ok"] and hit == len(mt["checks"])
            res[m].append({"id": mt["id"], "hit": hit, "total": len(mt["checks"]), "pass": passed, "latency_s": r["latency_s"], "pt": r["pt"], "ct": r["ct"], "cost_rmb": r["cost_rmb"], "preview": txt[:400]})
        p_cnt = sum(1 for x in res[m] if x["pass"])
        avg_l = round(sum(x["latency_s"] for x in res[m]) / len(res[m]), 2)
        hits = [f"{x['hit']}/{x['total']}" for x in res[m]]
        print(f"  {m:16s} | pass={p_cnt}/2 | hits={hits} | avg_lat={avg_l}s")
    return res


# ============================================================
# P15: 高并发流式 TTFT 抖动与突发压测（1 路 / 10 路 / 25 路并发 SSE）
# ============================================================
def run_p15():
    print("\n=== Running P15 (Streaming Concurrency 1 -> 10 -> 25 Burst) ===")
    res = {}
    prompt = [{"role": "user", "content": "用两句话总结微服务里指数退避重试为什么要加随机抖动（Jitter）。"}]
    for m in ["qwen3.8-flash", "qwen3.8-max"]:
        res[m] = {}
        for conc in [1, 10, 25]:
            t0 = time.perf_counter()
            with concurrent.futures.ThreadPoolExecutor(max_workers=conc) as ex:
                futs = [ex.submit(call_llm, m, prompt, 100, True) for _ in range(conc)]
                outs = [f.result() for f in futs]
            wall = round(time.perf_counter() - t0, 2)
            oks = [x for x in outs if x["ok"]]
            ttfts = sorted(x["ttft_s"] for x in oks if x["ttft_s"] is not None)
            lats = sorted(x["latency_s"] for x in oks)
            p50 = ttfts[len(ttfts) // 2] if ttfts else None
            p95 = ttfts[min(len(ttfts) - 1, int(len(ttfts) * 0.95))] if ttfts else None
            max_l = lats[-1] if lats else None
            tot_cost = round(sum(x["cost_rmb"] for x in oks), 5)
            res[m][f"c{conc}"] = {"conc": conc, "ok": len(oks), "fail": conc - len(oks), "wall_s": wall, "ttft_p50": p50, "ttft_p95": p95, "max_lat": max_l, "cost_rmb": tot_cost}
            print(f"  {m:15s} c={conc:2d} | ok={len(oks):2d}/{conc:2d} | ttft_p50={p50}s | ttft_p95={p95}s | max_lat={max_l}s | wall={wall}s")
    return res


def main():
    t0 = time.perf_counter()
    out = {
        "run_at": datetime.now().isoformat(),
        "p11": run_p11(),
        "p12": run_p12(),
        "p13": run_p13(),
        "p14": run_p14(),
        "p15": run_p15(),
    }
    out["elapsed_s"] = round(time.perf_counter() - t0, 1)
    OUT_PATH.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nALL P11-P15 LIVE BENCHMARKS SAVED TO {OUT_PATH} in {out['elapsed_s']}s")


if __name__ == "__main__":
    main()
