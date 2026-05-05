# Eval baselines

Committed reference artifacts for the eval suites. The numbers in the project
README come from these files.

## `mna_v1_fake.json`

| Field | Value |
|---|---|
| Suite | `mna_v1` (version 1, 10 questions) |
| Provider | `FakeLLMProvider` — deterministic, scripted responses, no network |
| Model id | `fake-1` |
| Run date (UTC) | 2026-05-05 |
| Hardware | M-series Mac (laptop) |
| Reproduce | `make bench-eval` (writes a fresh artifact under `eval/runs/`) |

### What this measures

These numbers measure retrieval and pipeline correctness against scripted
`FakeProvider` responses, not real LLM faithfulness. Specifically:

* `precision_at_1` and `recall_at_5` — the hybrid searcher ranking is exercised
  end-to-end against the in-process demo corpus, so these are real signal.
* `cost_usd_avg` and `p95_latency_seconds` — measured against the fake provider
  on a single laptop, so the absolute numbers are meaningless for capacity
  planning. They exist to detect regressions in the pipeline overhead, not to
  predict production behaviour.
* `faithfulness` — the rubric in `packages/eval/lexscribe_eval/metrics.py`
  checks that long words from the answer appear in the cited chunks.
  `FakeLLMProvider` returns canned strings that intentionally do not echo
  retrieved text, so this metric is `0.0` here by construction. Real
  faithfulness numbers require the BYOK path (see the project README's "Live
  Eval (BYOK)" section).
* `refusal_rate` — fake responses never refuse, so this is `0.0`.

### How to regenerate the baseline

```bash
make install
.venv/bin/lexscribe eval run \
  --suite mna_v1 \
  --provider fake \
  --output eval/baselines/mna_v1_fake.json
```

Commit the regenerated artifact in the same change as the code that moved the
numbers.
