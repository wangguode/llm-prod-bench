# llm-prod-bench

**Production AI Benchmarks** — Deterministic, code-asserted engineering probes for LLMs, Cloud MaaS gateways, long-context retrieval, structured outputs, and multimodal vision APIs.

Zero LLM-as-a-judge. Zero synthetic leaderboard hype. Every benchmark is reproducible via direct OpenAI-compatible HTTP probes.

## Benchmark Suites

- **`suite_v2/`**: 6-dimension, 16-task deterministic production Agent benchmark (`suite_v2.py` + `render_charts.py`):
  - **Dimension A**: Dirty ERP JSON extraction & strict schema compliance
  - **Dimension B**: Production code audit (TOCTOU race conditions, N+1 SQL, `asyncio` deadlock, SQLi/SSRF)
  - **Dimension C**: Agent Tool Calling (unauthorized write trap, 2-turn error recovery, strict integer-cent typing)
  - **Dimension D**: 16K long-context noise resistance
  - **Dimension E**: Anti-hallucination refusal & negative constraints
  - **Dimension F**: 5-way burst concurrency

## Quick Start

```bash
export DASHSCOPE_API_KEY="your-api-key"
python3 suite_v2/suite_v2.py
python3 suite_v2/render_charts.py
```

## Full Reports

Read the **Production AI Benchmarks** series on [DEV.to (@wangguode)](https://dev.to/wangguode).

## Benchmarking & DevRel Collaborations

Open to independent technical evaluations, stress-test benchmarks, and DevRel collaborations. Reach out via [GitHub (@wangguode)](https://github.com/wangguode) or [X (@sansaxypy)](https://x.com/sansaxypy).
