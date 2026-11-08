"""Runtime configuration, read once from environment variables.

On the cluster these variables come from your ConfigMap and Secret (section 4.1).
Nothing here is baked into the image, so one image runs in every environment.
Add your own keys (relevance floor, cache settings, ...) the same way.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field


def _int(name: str, default: int) -> int:
    return int(os.environ.get(name, default))


def _float(name: str, default: float) -> float:
    return float(os.environ.get(name, default))


@dataclass(frozen=True)
class Settings:
    # Which implementations to load. "stub" needs no cluster, no model, no network.
    retriever: str = "stub"          # RETRIEVER: stub | chroma
    llm_provider: str = "stub"       # LLM_PROVIDER: stub | ollama-host | ollama-incluster | hosted

    # The embedding pin (section 4.4). The indexer reads the same ConfigMap key.
    embed_model: str = "nomic-embed-text"

    # Vector store
    chroma_host: str = "chroma"
    chroma_port: int = 8000
    collection: str = "rahbar"

    # Retrieval and generation
    top_k: int = 5
    temperature: float = 0.2
    llm_model: str = "llama3.2:3b"
    ollama_url: str = "http://host.minikube.internal:11434"
    hosted_base_url: str = ""        # e.g. an OpenAI-compatible endpoint
    llm_api_key: str = field(default="", repr=False)   # from the Secret; never log it

    # Query pipeline (section 3.2 to 3.4). All of these come from the ConfigMap.
    relevance_floor: float = 0.63     # RELEVANCE_FLOOR: below this similarity, abstain
    fetch_k: int = 20                 # FETCH_K: candidates pulled before re-ranking to top_k
    exact_boost: float = 0.10         # EXACT_BOOST: added to a chunk that contains a query's exact term
    llm_timeout: float = 120.0        # LLM_TIMEOUT seconds
    llm_num_ctx: int = 8192           # LLM_NUM_CTX: Ollama truncates silently when evidence overflows it

    # Semantic cache (section 3.3). Off by default so `make dev` and the unit tests need no Redis.
    cache_enabled: bool = False       # CACHE_ENABLED
    cache_threshold: float = 0.92     # CACHE_THRESHOLD: cosine similarity for a hit
    cache_ttl_seconds: int = 21600    # CACHE_TTL_SECONDS
    cache_max_entries: int = 200      # CACHE_MAX_ENTRIES
    redis_host: str = "redis"         # REDIS_HOST
    redis_port: int = 6379            # REDIS_PORT

    # Failure-injection switches for docs/FAILURE-ANALYSIS.md. Defaults are the healthy values.
    include_superseded: bool = False  # stage E: INCLUDE_SUPERSEDED=true removes the version filter
    prompt_grounding: bool = True     # stage D: PROMPT_GROUNDING=false drops "use only the evidence"

    log_level: str = "INFO"


def _bool(name: str, default: bool) -> bool:
    return os.environ.get(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


def get_settings() -> Settings:
    return Settings(
        retriever=os.environ.get("RETRIEVER", "stub"),
        llm_provider=os.environ.get("LLM_PROVIDER", "stub"),
        embed_model=os.environ.get("EMBED_MODEL", "nomic-embed-text"),
        chroma_host=os.environ.get("CHROMA_HOST", "chroma"),
        chroma_port=_int("CHROMA_PORT", 8000),
        collection=os.environ.get("CHROMA_COLLECTION", "rahbar"),
        top_k=_int("TOP_K", 5),
        temperature=_float("TEMPERATURE", 0.2),
        llm_model=os.environ.get("LLM_MODEL", "llama3.2:3b"),
        ollama_url=os.environ.get("OLLAMA_URL", "http://host.minikube.internal:11434"),
        hosted_base_url=os.environ.get("HOSTED_BASE_URL", ""),
        llm_api_key=os.environ.get("LLM_API_KEY", ""),
        relevance_floor=_float("RELEVANCE_FLOOR", 0.63),
        fetch_k=_int("FETCH_K", 20),
        exact_boost=_float("EXACT_BOOST", 0.10),
        llm_timeout=_float("LLM_TIMEOUT", 120.0),
        llm_num_ctx=_int("LLM_NUM_CTX", 8192),
        cache_enabled=_bool("CACHE_ENABLED", False),
        cache_threshold=_float("CACHE_THRESHOLD", 0.92),
        cache_ttl_seconds=_int("CACHE_TTL_SECONDS", 21600),
        cache_max_entries=_int("CACHE_MAX_ENTRIES", 200),
        redis_host=os.environ.get("REDIS_HOST", "redis"),
        redis_port=_int("REDIS_PORT", 6379),
        include_superseded=_bool("INCLUDE_SUPERSEDED", False),
        prompt_grounding=_bool("PROMPT_GROUNDING", True),
        log_level=os.environ.get("LOG_LEVEL", "INFO"),
    )
