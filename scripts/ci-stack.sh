#!/usr/bin/env bash
# Run against the ephemeral kind cluster selected in CI.
set -euo pipefail
prefix=${1:-}
tag=${2:-dev}
overlay=$(mktemp -d k8s/overlays/.local-XXXXXX)
forward_pid=
model_container=
cleanup() {
  if [[ -n "$forward_pid" ]]; then kill "$forward_pid" || true; fi
  if [[ -n "$model_container" ]]; then docker rm -f "$model_container" >/dev/null || true; fi
  rm -rf "$overlay"
}
trap cleanup EXIT

kubectl apply -f https://raw.githubusercontent.com/kubernetes/ingress-nginx/controller-v1.12.8/deploy/static/provider/cloud/deploy.yaml
kubectl -n ingress-nginx rollout status deployment/ingress-nginx-controller --timeout=240s

model_container=$(docker run --detach --network kind \
  --mount "type=bind,source=$PWD/scripts/fixture-embeddings.py,target=/model.py,readonly" \
  python:3.12-slim-bookworm python /model.py)
ip=$(docker inspect -f '{{(index .NetworkSettings.Networks "kind").IPAddress}}' "$model_container")
cat > "$overlay/kustomization.yaml" <<EOF
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
resources:
  - ../prod
images:
  - name: rahbar-api
    newName: ${prefix}rahbar-api
    newTag: $tag
  - name: rahbar-ui
    newName: ${prefix}rahbar-ui
    newTag: $tag
  - name: rahbar-indexer
    newName: ${prefix}rahbar-indexer
    newTag: $tag
patches:
  - target:
      kind: ConfigMap
      name: rahbar-config
    patch: |-
      - op: replace
        path: /data/EMBED_MODEL
        value: fixture-lexical-v1
      - op: replace
        path: /data/LLM_PROVIDER
        value: stub
      - op: replace
        path: /data/RELEVANCE_FLOOR
        value: "0.05"
      - op: replace
        path: /data/CACHE_THRESHOLD
        value: "1.0"
EOF
OLLAMA_HOST_IP="$ip" bash scripts/deploy.sh "$overlay" eval/fixtures "${prefix}rahbar-indexer:$tag"

kubectl -n ingress-nginx port-forward svc/ingress-nginx-controller 8080:80 > /tmp/rahbar-ingress.log 2>&1 &
forward_pid=$!
curl --fail --retry 15 --retry-all-errors --retry-delay 2 \
  -H 'Host: rahbar.local' http://127.0.0.1:8080/ > /dev/null
baseline=eval/fixtures/baseline.fixture.json
test -s "$baseline"
python "${EVAL_RUNNER:-eval/run_eval.py}" --api http://127.0.0.1:8080 --host rahbar.local \
  --golden eval/fixtures/golden.fixture.yaml --baseline "$baseline" \
  --out /tmp/rahbar-fixture-results.json
python - <<'PY'
import json
from pathlib import Path
report = json.loads(Path("/tmp/rahbar-fixture-results.json").read_text())
if not report.get("citations_total") or report.get("abstention_correctness") != 1:
    raise SystemExit("Fixture smoke test requires cited answers and a correct abstention")
PY
