# llm-prod-bench

**Production AI Benchmarks** — Deterministic, code-asserted engineering probes for LLMs, Cloud MaaS gateways, long-context retrieval, structured outputs, and multimodal vision APIs.

Zero LLM-as-a-judge. Zero synthetic leaderboard hype. Every benchmark is reproducible via direct OpenAI-compatible HTTP probes.

---

## Benchmark Suites

- **`suite_v2/`** — 6-dimension, 16-task deterministic production Agent benchmark (`suite_v2.py` + `render_charts.py`):
  - **Dimension A**: Dirty ERP JSON extraction & strict schema compliance
  - **Dimension B**: Production code audit (TOCTOU race conditions, N+1 SQL, `asyncio` deadlock, SQLi/SSRF)
  - **Dimension C**: Agent Tool Calling (unauthorized write trap, 2-turn error recovery, strict integer-cent typing)
  - **Dimension D**: 16K long-context noise resistance
  - **Dimension E**: Anti-hallucination refusal & negative constraints
  - **Dimension F**: 5-way burst concurrency
- **`p02_gateway/`** — Production MaaS Gateway stress-test (`gateway_bench.py`):
  - Streaming TTFT (p50 / p95 / p99) & throughput stability
  - 100-way burst concurrency & rate-limit behavior
  - Context caching & token billing reconciliation quirks
- **`p06_to_p10/`** — Enterprise Cost, Reasoning, Security & Routing Probes (`run_p06_to_p10.py` + `p06_to_p10_live.json`, 120 live API calls):
  - Flash vs Flagship limit testing (-88% cost)
  - `enable_thinking` ON vs OFF latency & `reasoning_tokens` explosion (18x cost)
  - Indirect Prompt Injection & unauthorized tool-call defense across 4 flagships
  - 16-turn Agent context rot vs async state compaction (-91% input tokens)
  - LLM gatekeeper router vs 0ms deterministic rule routing (False-Hard trap)
- **`p11_to_p15/`** — End-to-End Engineering Workflow & Concurrency Probes (`run_p11_to_p15.py` + `p11_to_p15_live.json` + `p11_p12_p14_glm_fair.json`, 168 live API calls):
  - **P11**: Live SQLite 3 Text-to-SQL (1:N JOIN fan-out silent 37% error trap)
  - **P12**: AI Code Review (6 real production bugs + 2 clean functions false-positive check)
  - **P13**: Hybrid BM25 Top-3 RAG vs Full Long-Context across 30 policy docs (151x cost gap)
  - **P14**: Mixed CN/EN tech meeting Action Item extraction with verbal date overrides
  - **P15**: Streaming SSE burst concurrency (`1 -> 10 -> 25`) TTFT p50/p95 tail spread

---

## Quick Start

```bash
export DASHSCOPE_API_KEY="your-api-key"
python3 suite_v2/suite_v2.py
python3 suite_v2/render_charts.py
```

---

## Published Reports (Bilingual Reach)

- **English Series (DEV.to)**: [Production AI Benchmarks (@wangguode)](https://dev.to/wangguode)
  - Issue #01: [Benchmarking 4 Chinese Flagship LLMs Under Real Agent Load (16 Deterministic Production Tests)](https://dev.to/wangguode/benchmarking-4-chinese-flagship-llms-under-real-agent-load-16-deterministic-production-tests-32eh)
  - Issue #02: [Production MaaS Gateway Benchmark: Streaming TTFT, 100-Way Burst Concurrency & Token Billing Quirks](https://dev.to/wangguode/production-maas-gateway-benchmark-streaming-ttft-100-way-burst-concurrency-token-billing-quirks-1cm1)
  - Issue #03: [128K Long-Context Needle-in-a-Haystack: Multi-Hop Contract Audits & Context Caching Economics](https://dev.to/wangguode/128k-long-context-needle-in-a-haystack-multi-hop-contract-audits-context-caching-economics-23hd)
  - Issue #04: [Structured Output & Function Calling Under Stress: 5 Production Failure Modes Across 201 Calls](https://dev.to/wangguode/structured-output-function-calling-under-stress-5-production-failure-modes-across-201-calls-62e)
  - Issue #05: [Multimodal Vision Models on Dirty Invoices, UI Screenshots & Architecture Diagrams: 45 Live Calls](https://dev.to/wangguode/multimodal-vision-models-on-dirty-invoices-ui-screenshots-architecture-diagrams-45-live-calls-3d7j)
- **Chinese Series (Zhihu, 12K+ followers, Lv8)**: 《AI评测篇》([Issue #01](https://zhuanlan.zhihu.com/p/2105786958261887463) · [Issue #02](https://zhuanlan.zhihu.com/p/2106130232684107687) · [Issue #03](https://zhuanlan.zhihu.com/p/2106132039657317156) · [Issue #04](https://zhuanlan.zhihu.com/p/2106135589607170990) · [Issue #05](https://zhuanlan.zhihu.com/p/2106136384415196171))

---

## Want Your LLM, MaaS Gateway, or AI DevTool Benchmarked?

We partner with **LLM providers, API gateways, cloud inference platforms, and AI coding / Agent tool teams** to run transparent, reproducible production stress-tests.

### How Our Independent Sponsorship Works
1. **Zero Fabricated Data**: Every number comes from deterministic Python probes committed to this repo.
2. **Pre-Flight Check First**: Before any sponsored deep-dive goes live, we run a private pre-flight probe to surface real latency/compatibility bugs for your engineering team and identify your genuine production strengths.
3. **Bilingual Engineering Distribution**: Published across **DEV.to + GitHub + X (60fps visual demo) + Zhihu (China's #1 engineering community)**.

| Tier | Deliverables | Best For |
| :--- | :--- | :--- |
| **Community Test Key** | Included in our upcoming multi-provider comparison table + private bug/latency feedback | Any LLM / MaaS gateway wanting fair, non-rate-limited testing |
| **Sponsored Deep-Dive** | Dedicated reproducible probe suite + English deep-dive (DEV.to) + X promo thread/video + GitHub sponsor badge | Global AI Infra, API routers, LLM observability & DevTools |
| **Bilingual Launch Pack** | Everything above + full Chinese engineering report on Zhihu (12K+ tech followers) | Teams targeting both global & Chinese enterprise developers |

### Get in Touch
- **Fastest**: DM on X ([@sansaxypy](https://x.com/sansaxypy))
- **GitHub**: Open a `[Benchmark Request]` issue on this repo
- **DEV.to**: Message [@wangguode](https://dev.to/wangguode)
