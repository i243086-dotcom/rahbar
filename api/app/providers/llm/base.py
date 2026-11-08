"""The LLM provider interface (section 3.5). Swapping providers is one file."""

from __future__ import annotations

import json
import re
from contextvars import ContextVar
from typing import Protocol

from pydantic import ValidationError

from ...schemas import Answer, Passage

# Token usage of the call in progress; the answer service reads it for logs and metrics.
usage_var: ContextVar[dict[str, int]] = ContextVar("llm_usage", default={})


class ProviderError(Exception):
    """The model could not be reached or answered with an error."""


class InvalidModelOutput(ProviderError):
    """The model replied, but not with a valid Answer (prose, broken JSON, missing keys)."""


class LLMProvider(Protocol):
    name: str

    def generate(
        self, question: str, passages: list[Passage], *, strict: bool = False
    ) -> Answer:
        """Answer the question from the passages, as an `Answer`.

        Raise InvalidModelOutput for output that does not validate, ProviderError for
        transport failures. `strict=True` is the one retry: it adds a reminder to the prompt.
        """
        ...


_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE)


def parse_answer(raw: str) -> Answer:
    """Structure can be guaranteed; truth cannot. Parse and validate with Pydantic."""
    text = _FENCE.sub("", raw.strip())
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        raise InvalidModelOutput(f"no JSON object in the reply: {raw[:80]!r}")
    try:
        return Answer.model_validate_json(text[start:end + 1])
    except (ValidationError, json.JSONDecodeError) as exc:
        raise InvalidModelOutput(f"reply does not match the Answer schema: {exc}") from exc
