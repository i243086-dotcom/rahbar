# Real-corpus Minikube run

The demo ran in a disposable GitHub Actions runner on Minikube with Calico, ingress-nginx and metrics-server. It fetched the public corpus, checked all nine files against the committed manifest, and built the app images from the submission code. Ollama used `nomic-embed-text` for embeddings and `llama3.2:3b` for answers. [Successful demo run](https://github.com/i243086-dotcom/rahbar/actions/runs/42848939008)

| Check | Observation | Evidence |
| --- | --- | --- |
| Corpus and indexing | All 9 files matched the manifest. The Job processed 41 OCR pages and indexed 665 chunks in 734 seconds. | [Corpus checksums](minikube-corpus-verification.txt), [Job and rollout output](minikube-real-deploy.txt) |
| Pod resources | 130 indexer samples. Highest observed memory was 509 MiB. Highest observed CPU was 1,250m. | [Pod samples](minikube-real-indexer-resources.txt) |
| Services | Three API endpoints and HPA CPU at 3% against a 70% target. | [Cluster status](minikube-real-cluster-status.txt) |
| Calico NetworkPolicy | The UI resolved Chroma but its connection timed out. The API received a Chroma heartbeat. | [NetworkPolicy output](minikube-real-network-policy.txt) |
| Ingress | Two requests used the `rahbar.local` Host header and the port-forward to the ingress-nginx controller. The academic-warning question returned citations and the hostel rules question returned `answered_from_context: false`. | [Port-forward output](minikube-ingress-forward.txt), [cited answer](minikube-real-ingress-cited.json), [abstention](minikube-real-ingress-abstention.json) |

See the [UI screenshots](real-corpus-ui-demo.md) for the separate localhost demo.
