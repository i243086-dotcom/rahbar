"""Expire the API's semantic cache after a re-index (section 3.3).

If the index changes and the cache does not, the API keeps serving answers computed from
the old index. The indexer deletes every cache entry once the new collection is live.
The API also tags each entry with the index_id it was computed from and ignores entries
whose id differs, so an entry written by an in-flight request just after this runs is
harmless too. Key prefix is part of the contract in docs/CONTRACT.md.
"""

from __future__ import annotations

import json
import time
from typing import Any

from .config import IndexerSettings

CACHE_PREFIX = "rahbar:cache:"


def invalidate_cache(settings: IndexerSettings, client: Any | None = None) -> int | None:
    """Delete all cache entries. Returns how many keys were removed, or None when there
    is no Redis to talk to. Never raises: a failed flush must not fail a finished index."""
    if not settings.redis_host and client is None:
        return None
    try:
        if client is None:
            import redis

            client = redis.Redis(host=settings.redis_host, port=settings.redis_port,
                                 socket_timeout=5, decode_responses=True)
        keys = list(client.scan_iter(match=f"{CACHE_PREFIX}*", count=500))
        if keys:
            client.delete(*keys)
        return len(keys)
    except Exception as exc:
        print(json.dumps({"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                          "logger": "rahbar.indexer", "level": "WARNING",
                          "msg": "cache invalidation failed; API ignores stale entries by index_id",
                          "error": repr(exc)}), flush=True)
        return None
