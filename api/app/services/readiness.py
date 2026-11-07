"""What /readyz checks (sections 4.3 and 4.4). Liveness checks nothing; readiness checks
every dependency the pod needs to serve a question, and names the one that failed."""

from __future__ import annotations

import logging
from typing import Any

from ..config import Settings

log = logging.getLogger("rahbar.readiness")
_last_state: dict[str, str] = {}


def pin_mismatch(metadata: dict[str, Any], settings: Settings) -> str | None:
    """The embedding-pin guardrail. None when the index was built with the model this API
    would embed questions with; otherwise a message naming exactly what conflicts."""
    built_with = metadata.get("embed_model")
    if not built_with:
        return "the index records no embed_model; re-run the indexer Job"
    if built_with != settings.embed_model:
        return (f"embedding model mismatch: the index was built with {built_with!r} "
                f"(dimension {metadata.get('dimension', '?')}) but this API is configured with "
                f"EMBED_MODEL={settings.embed_model!r}; vectors from different models are not "
                f"comparable, so retrieval would return nonsense")
    return None


def check_readiness(state: Any) -> tuple[bool, dict[str, str]]:
    """Returns (ready, checks). `checks` maps each dependency to "ok" or the reason it failed."""
    settings: Settings = state.settings
    checks: dict[str, str] = {}

    if settings.retriever == "chroma":
        try:
            info = state.retriever.info()
            checks["chroma"] = "ok"
            if info.count == 0:                                    # non-empty collection
                checks["collection"] = "empty: run the indexer Job"
            else:
                checks["collection"] = f"ok ({info.count} chunks)"
            conflict = pin_mismatch(info.metadata, settings)
            checks["embedding_pin"] = conflict or f"ok ({settings.embed_model})"
        except Exception as exc:     # noqa: BLE001
            checks["chroma"] = f"unreachable: {type(exc).__name__}: {exc}"
    else:
        checks["retriever"] = f"ok ({settings.retriever})"

    if settings.cache_enabled:
        try:
            state.cache.ping()
            checks["redis"] = "ok"
        except Exception as exc:     # noqa: BLE001
            checks["redis"] = f"unreachable: {type(exc).__name__}: {exc}"

    failed = {k: v for k, v in checks.items() if not v.startswith("ok")}
    for name, reason in failed.items():                           # log changes, not every probe
        if _last_state.get(name) != reason:
            log.error("not ready", extra={"dependency": name, "reason": reason})
    for name in checks.keys() - failed.keys():
        if name in _last_state and _last_state[name] != checks[name] and name not in failed:
            log.info("recovered", extra={"dependency": name})
    _last_state.clear()
    _last_state.update(checks)
    return not failed, checks
