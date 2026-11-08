# Platform architecture

Ingress accepts one host and keeps the /api prefix for FastAPI. nginx serves the chat at /. Chroma and Redis are internal ClusterIP services. Chroma is a one-replica StatefulSet because the vector store needs a stable pod identity and a claim that outlives the pod. Its volume claim template attaches persistent storage at /data. Redis uses a Recreate Deployment with an append-only file and a separate claim. Recreate avoids overlapping replicas writing the same Redis volume during a rollout.

The API Deployment has three replicas, a startup probe, dependency-free liveness, and dependency-aware readiness. Readiness withholds traffic on missing data, an embedding pin mismatch or loss of Redis. Rolling updates surge by one replica and keep existing ready replicas while the new one starts. A preStop delay lets endpoint changes propagate before the API handles SIGTERM.

An indexer Job and weekly CronJob share a pod template, configuration keys and a read-only corpus claim. They are the sole index writers. CronJob concurrency policy forbids overlapping scheduled runs. Manual runs must be serialized as well because each uses the same Chroma build collection name.

Default-deny policies isolate the namespace. API and indexer reach Chroma and Redis, CoreDNS serves DNS, and the two model clients can reach only the configured host IP and Ollama port. The indexer reaches Redis to invalidate the cache after publication. The UI may reach the API and cannot reach Chroma. Service accounts have no mounted token. Workloads start as non-root with a read-only root filesystem and all Linux capabilities dropped. Chroma and Redis write to their claims. nginx and OCR use /tmp mounts.
