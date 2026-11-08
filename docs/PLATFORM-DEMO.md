# Student B evidence

Run the commands against the Calico minikube cluster. Keep actual command output and screenshots under `docs/evidence/`.

1. Save `kubectl -n rahbar get endpoints api` and `kubectl -n rahbar get hpa` after the API has three Ready replicas and metrics-server has sampled them.
2. While the real indexer Job runs, sample `kubectl -n rahbar top pods --containers` repeatedly. Record the largest observed indexer memory and justify the requests and limits for each workload.
3. Run a cited question through Ingress, delete one API pod, and repeat the question while the replacement becomes Ready. Capture the cited UI screenshot and the response for the absent hostel topic.
4. Build and load a visibly changed API image under a new tag. Run `kubectl -n rahbar set image deployment/api api=rahbar-api:<tag>`, `kubectl -n rahbar rollout status deployment/api`, then `kubectl -n rahbar rollout undo deployment/api` and verify the previous image serves.
5. Capture the API deployment generation before and after `make index`, plus the Job's chunking and cache invalidation logs. An unchanged deployment generation shows the rebuild did not redeploy readers.
6. Record the pin guardrail by patching only `EMBED_MODEL` and restarting the API. Capture the unready new pod and its `embedding_pin` log. Restore the shared value and restart the API before continuing.
7. From the UI pod, try `wget -T 3 -O- http://chroma:8000/api/v2/heartbeat`. Capture the failure and a successful heartbeat from an allowed workload. Compare to the Calico policy.
8. Require CI and one approving review in the branch rules. In a review PR, temporarily set the fixture top-k to one to demonstrate the recall gate, then restore it. Capture the blocked and green merge states. Include the successful CD link and the three SHA-tagged images.

The production threshold values and real-corpus baseline should come from Student A's measured run. Record the team's actual revisions and manual checks in AI-USAGE.
