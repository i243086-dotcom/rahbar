"""Ollama provider: ollama-host or ollama-incluster (section 3.5).

The Answer JSON schema goes in `format`, which makes Ollama constrain decoding to it. We
still validate with Pydantic afterwards: enforcement guarantees structure, not truth.
"""

from __future__ import annotations

import httpx

from ...config import Settings
from ...schemas import Answer, Passage
from ...services.prompt import build_messages
from ..llm.base import ProviderError, parse_answer, usage_var


class OllamaProvider:
    name = "ollama"

    def __init__(self, settings: Settings, client: httpx.Client | None = None) -> None:
        self.settings = settings
        self.client = client or httpx.Client(
            timeout=httpx.Timeout(settings.llm_timeout, connect=5.0))

    def generate(
        self, question: str, passages: list[Passage], *, strict: bool = False
    ) -> Answer:
        s = self.settings
        messages, removed = build_messages(question, passages, s, strict=strict)
        payload = {
            "model": s.llm_model,
            "messages": messages,
            "stream": False,
            "format": Answer.model_json_schema(),
            # Low temperature: facts and JSON. num_ctx matters: Ollama's default window is
            # smaller than five 400-word chunks, and it truncates the START of the prompt
            # (the rules) without any error.
            "options": {"temperature": s.temperature, "num_ctx": s.llm_num_ctx},
        }
        try:
            r = self.client.post(f"{s.ollama_url.rstrip('/')}/api/chat", json=payload)
            r.raise_for_status()
            data = r.json()
            content = data["message"]["content"]
        except (httpx.HTTPError, KeyError, ValueError) as exc:
            raise ProviderError(f"ollama call failed: {exc!r}") from exc
        usage_var.set({"tokens_in": int(data.get("prompt_eval_count", 0)),
                       "tokens_out": int(data.get("eval_count", 0)),
                       "injection_removed": removed})
        return parse_answer(content)
