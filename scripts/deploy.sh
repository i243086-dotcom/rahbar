#!/usr/bin/env bash
# Seed the corpus (when needed), apply services, index, and wait for both rollouts.
set -euo pipefail
overlay=${1:?pass a Kustomize overlay}
corpus=${2:--}
loader_image=${3:-rahbar-indexer:dev}
scratch=$(mktemp -d)
loader_started=false
cleanup() {
  if $loader_started; then
    kubectl -n rahbar delete pod corpus-loader --ignore-not-found --wait=false >/dev/null
  fi
  rm -rf "$scratch"
}
trap cleanup EXIT

kubectl kustomize "$overlay" > "$scratch/full.yaml"
python - "$scratch" <<'PY'
import ipaddress
import os
import pathlib
import sys
import time
import yaml

root = pathlib.Path(sys.argv[1])
docs = list(yaml.safe_load_all((root / "full.yaml").read_text()))
jobs = [doc for doc in docs if doc["kind"] == "Job"]
if len(jobs) != 1:
    raise SystemExit("Expected one bootstrap Job")
job = jobs[0]
job["metadata"]["name"] += f"-{time.time_ns()}"
(root / "job-name").write_text(job["metadata"]["name"])
(root / "job.yaml").write_text(yaml.safe_dump(job))
stack = [doc for doc in docs if doc["kind"] != "Job"]
if host := os.environ.get("OLLAMA_HOST_IP"):
    host = str(ipaddress.IPv4Address(host))
    for doc in stack:
        if doc["kind"] == "ConfigMap" and doc["metadata"]["name"] == "rahbar-config":
            doc["data"]["OLLAMA_URL"] = f"http://{host}:11434"
        elif doc["kind"] == "NetworkPolicy" and doc["metadata"]["name"] == "ollama-host":
            doc["spec"]["egress"][0]["to"][0]["ipBlock"]["cidr"] = f"{host}/32"
(root / "stack.yaml").write_text(yaml.safe_dump_all(stack))
PY
if [[ "$corpus" != "-" ]]; then
  test -d "$corpus"
  kubectl apply -f k8s/base/namespace.yaml
  kubectl -n rahbar apply -f k8s/base/serviceaccounts.yaml -f k8s/base/corpus-pvc.yaml
  sed "s|image: rahbar-indexer:dev|image: $loader_image|" k8s/base/corpus-loader.yaml |
    kubectl create -f -
  loader_started=true
  kubectl -n rahbar wait --for=condition=Ready pod/corpus-loader --timeout=180s
  kubectl -n rahbar cp "$corpus/." corpus-loader:/corpus
  kubectl -n rahbar delete pod corpus-loader --wait=true
  loader_started=false
fi

kubectl apply -f "$scratch/stack.yaml"
kubectl -n rahbar rollout status statefulset/chroma --timeout=240s
kubectl -n rahbar rollout status deployment/redis --timeout=180s
kubectl -n rahbar create -f "$scratch/job.yaml"
job=$(cat "$scratch/job-name")
if ! kubectl -n rahbar wait --for=condition=complete "job/$job" --timeout="${INDEX_TIMEOUT:-20m}"; then
  kubectl -n rahbar describe "job/$job"
  kubectl -n rahbar logs "job/$job" --all-containers=true || true
  exit 1
fi
kubectl -n rahbar logs "job/$job"
kubectl -n rahbar rollout restart deployment/api
kubectl -n rahbar rollout status deployment/api --timeout=180s
kubectl -n rahbar rollout status deployment/ui --timeout=180s
