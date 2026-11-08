# 0001 Run the indexer as a Job

Keep all indexing in a dedicated Job and its weekly CronJob template. Putting it in API startup would give three replicas concurrent write access to one logical index and force every deployment or restart to repeat OCR and embedding. It would also couple pod readiness to work that can take minutes.

The Job reads a shared corpus PVC and writes a temporary Chroma collection. The existing collection serves during extraction, embedding and upload. After a successful count check, the writer replaces the old name with the completed collection and invalidates the Redis cache. The delete and rename calls leave a brief cutover window, so the API retries if a lookup overlaps the swap. A failure during that window can require a new indexing run.

Use CronJob concurrency policy Forbid. Operators should wait for the active indexing run before starting another because the build collection name is shared. The API Deployment and its image can roll independently of the index.
