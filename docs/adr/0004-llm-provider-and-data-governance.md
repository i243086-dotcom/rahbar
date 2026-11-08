# ADR 0004: A pluggable LLM provider, and what data may leave the cluster

## Status
Accepted · 2026-11-07

## Context
The model is the least predictable part of the system, and the one that may sit outside our
control. Students type questions that can contain personal details. The documents are public, the
questions are not.

## Decision
One interface (`api/app/providers/llm/base.py`): `generate(question, passages, strict=False) -> Answer`,
raising `InvalidModelOutput` for a bad reply and `ProviderError` for a transport failure. The
provider is chosen by `LLM_PROVIDER`. Shipped fully: `ollama-host` (Ollama on the developer's laptop,
reached at `host.minikube.internal:11434`). Also implemented: `hosted` (any OpenAI-compatible
endpoint; the key comes from a Kubernetes Secret and is never logged). `stub` exists for tests and CI
so that no test ever calls a model.
Embeddings always go through Ollama at `OLLAMA_URL`, whichever provider generates, because the
pinned embedding model must be the one that built the index.

Data governance: with `ollama-host` nothing leaves the developer's machine. With `hosted`, the
question and the retrieved passages go to a third party. So: logs record chunk ids, scores and
request ids, never the API key, and the question text only at the length already in the request log;
the cache stores questions in the cluster's Redis only; and no user identifier is collected at all.

## Options considered
- **Hosted only.** Faster answers, but the key becomes the secret to protect and the questions
  leave the cluster.
- **Ollama in the cluster.** Self-contained, but needs about 8 GB for minikube and a long startup
  probe; kept as a bonus rather than the default.
- **Hard-code one provider.** Simplest, and makes the CI stub impossible.

## Consequences
Swapping providers is one file and one ConfigMap value. Small local models are the weak point:
they sometimes answer in prose, which is why validation, one strict retry and a canned fallback sit
behind the interface. `num_ctx` is set explicitly because Ollama truncates the start of an
oversized prompt (the rules) silently.
