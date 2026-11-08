# Local fixture gate verification

Run on 8 November 2026 with the Student A API and indexer, local Chroma 1.0.12, Redis 7.4.1, the CI fixture embedding double, and the stub answer provider. The indexer wrote 11 chunks from three fixture documents. The API's readiness endpoint passed before each evaluation.

| Setting | Recall@3 | Recall@5 | Citation validity | Abstention correctness | Gate |
| --- | ---: | ---: | ---: | ---: | --- |
| TOP_K=5 | 80% | 100% | 100% | 100% | Passed |
| TOP_K=1 | 80% | 80% | 100% | 100% | Failed |

The failing run reported:

```text
GATE FAILED
  - recall@5 fell 20.0 points below the baseline (0.800 vs 1.000; limit 5)
```

The second indexing run logged six Redis cache keys removed, so it evaluated fresh retrieval. The stub generator's injection resistance was 0% in both runs. The fixture gate checks retrieval, citation validity and abstention. Use the production model and the separate prompt tests for injection behavior. This was a local HTTP run. GitHub's blocked and green PR screenshots require a hosted workflow run.

A separate Docker smoke test started the built API image with a read-only root filesystem, no Linux capabilities, and no-new-privileges. Docker reported user 10001:10001. The stub API returned 200 from /readyz and answered from context through /api/ask.
