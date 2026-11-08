#!/usr/bin/env bash
# Exercise recovery and readiness on the disposable kind fixture stack.
set -euo pipefail
evidence=${1:?pass an evidence directory}
mkdir -p "$evidence"
# The disposable kind kubelets use self-signed serving certificates.
kubectl apply -f https://github.com/kubernetes-sigs/metrics-server/releases/download/v0.8.1/components.yaml
kubectl -n kube-system patch deployment metrics-server --type=json \
  -p '[{"op":"add","path":"/spec/template/spec/containers/0/args/-","value":"--kubelet-insecure-tls"}]'
k() { kubectl -n rahbar "$@"; }
ask() {
  curl --fail --silent --show-error --max-time 20 \
    -H 'Host: rahbar.local' -H 'Content-Type: application/json' \
    --data '{"question":"What is the minimum attendance needed to sit the final exam?"}' \
    http://127.0.0.1:8080/api/ask |
    python -c 'import json,sys; a=json.load(sys.stdin); assert a["answered_from_context"] and a["citations"]; print(json.dumps(a, indent=2))'
}

{
  date -u +%FT%TZ
  k get endpoints api
  k get endpointslices -l kubernetes.io/service-name=api -o json |
    python -c 'import json,sys; es=[e for s in json.load(sys.stdin)["items"] for e in s["endpoints"] if e["conditions"].get("ready")]; print(f"{len(es)} ready endpoints"); assert len(es) >= 3'
  victim=$(k get pods -l app=api -o jsonpath='{.items[0].metadata.name}')
  k delete "pod/$victim" --wait=false
  ask
  k wait --for=delete "pod/$victim" --timeout=120s
  k rollout status deployment/api --timeout=150s
  k get pods -l app=api -o wide
} | tee "$evidence/endpoints-and-pod-recovery.txt"

{
  before=$(k get deployment api -o jsonpath='{.metadata.generation}')
  job="evidence-reindex-$(date +%s)"
  k create job --from=cronjob/reindex "$job"
  k wait --for=condition=complete "job/$job" --timeout=180s
  k logs "job/$job"
  after=$(k get deployment api -o jsonpath='{.metadata.generation}')
  printf 'API generation before=%s after=%s\n' "$before" "$after"
  test "$before" = "$after"
  ask
} | tee "$evidence/reindex-without-redeploy.txt"

original=$(k get configmap rahbar-config -o jsonpath='{.data.EMBED_MODEL}')
restore_pin() {
  k patch configmap rahbar-config --type merge -p "{\"data\":{\"EMBED_MODEL\":\"$original\"}}"
  k rollout restart deployment/api
}
trap restore_pin EXIT
{
  k patch configmap rahbar-config --type merge -p '{"data":{"EMBED_MODEL":"fixture-mismatch"}}'
  k rollout restart deployment/api
  match=
  for _ in $(seq 1 30); do
    logs=$(k logs -l app=api --tail=30 --prefix=true || true)
    match=$(printf '%s\n' "$logs" | grep -m1 '"dependency": "embedding_pin".*fixture-mismatch' || true)
    if [[ -n "$match" ]]; then break; fi
    sleep 2
  done
  test -n "$match"
  printf '%s\n' "$match"
  k get pods -l app=api -o wide
  restore_pin
  trap - EXIT
  k rollout status deployment/api --timeout=180s
  ask
} > "$evidence/embedding-pin.txt" 2>&1
cat "$evidence/embedding-pin.txt"
{
  previous=$(k get deployment api -o jsonpath='{.spec.template.spec.containers[0].image}')
  canary=rahbar-api:rollout-proof
  docker build --tag "$canary" - <<EOF
FROM $previous
ENV LOG_LEVEL=DEBUG
EOF
  kind load docker-image --name rahbar "$canary"
  k set image deployment/api "api=$canary"
  k rollout status deployment/api --timeout=180s
  k exec deployment/api -- printenv LOG_LEVEL
  ask
  k rollout undo deployment/api
  k rollout status deployment/api --timeout=180s
  current=$(k get deployment api -o jsonpath='{.spec.template.spec.containers[0].image}')
  printf 'Restored image: %s\n' "$current"
  test "$current" = "$previous"
  ask
} | tee "$evidence/rollout-and-rollback.txt"

{
  kubectl -n kube-system rollout status deployment/metrics-server --timeout=180s
  utilization=
  for _ in $(seq 1 24); do
    utilization=$(k get hpa api -o jsonpath='{.status.currentMetrics[0].resource.current.averageUtilization}')
    if [[ -n "$utilization" ]]; then break; fi
    sleep 5
  done
  test -n "$utilization"
  k get hpa api
  k top pods --containers
} | tee "$evidence/fixture-hpa-and-resources.txt"
