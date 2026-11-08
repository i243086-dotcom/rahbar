# Hosted fixture and platform verification

GitHub Actions run [42481055325](https://github.com/i243086-dotcom/rahbar/actions/runs/42481055325) passed on 8 November 2026 at commit `5911781`. The hosted kind cluster indexed 11 chunks from the three fixture documents. Through Ingress, recall@5, citation validity and abstention correctness were all 100%. The fixture uses a deterministic embedding double and stub generator.

The following files are unedited outputs from the [platform evidence artifact](https://github.com/i243086-dotcom/rahbar/actions/runs/42481055325/artifacts/13617751200). Its SHA-256 matched the digest reported by Actions.

- [Endpoints and pod recovery](hosted-endpoints-and-pod-recovery.txt) records three ready endpoints and a cited response during replacement.
- [Re-index without redeploy](hosted-reindex-without-redeploy.txt) records the completed CronJob-triggered run, cache invalidation and API generation 2 before and after.
- [Embedding pin](hosted-embedding-pin.txt) records the unready mismatched pod, its `embedding_pin` log and the successful response after the configuration was restored.

On the same date GitHub's branch API reported `main` as protected with required status checks off and no required check contexts. It reported `dev` as unprotected. Repository admin access is required to enforce a gate and capture the protected merge control. [GitHub branch API](https://api.github.com/repos/i243086-dotcom/rahbar/branches/main)

Run [42481702942](https://github.com/i243086-dotcom/rahbar/actions/runs/42481702942) also passed. Its [platform artifact](https://github.com/i243086-dotcom/rahbar/actions/runs/42481702942/artifacts/13617497641) supplied two additional outputs with a verified archive checksum.

- [Rollout and rollback](hosted-rollout-and-rollback.txt) records a new API image with debug logging, successful answers after both rollouts and restoration of the previous image.
- [Fixture HPA and resources](hosted-fixture-hpa-and-resources.txt) records actual CPU utilization at 2% against a 70% target, three replicas and per-container resource readings. These readings describe fixture traffic. The real-corpus OCR peak remains a separate measurement.
