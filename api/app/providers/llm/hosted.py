"""Hosted free-tier provider (Groq, Google AI Studio, OpenRouter): any OpenAI-compatible API.

The key arrives as LLM_API_KEY from a Kubernetes Secret created on the command line. It never
appears in a file that is committed, and never in a log line or an exception message.
"""

from __future__ import annotations

import httpx

from ...config import Settings
from ...schemas import Answer, Passage
from ...services.prompt import build_messages
from ..llm.base import ProviderError, parse_answer, usage_var


class HostedProvider:
    name = "hosted"

    def __init__(self, settings: Settings, client: httpx.Client | None = None) -> None:
        self.settings = settings
        self.client = client or httpx.Client(
            timeout=httpx.Timeout(settings.llm_timeout, connect=5.0))

    def generate(
        self, question: str, passages: list[Passage], *, strict: bool = False
    ) -> Answer:
        s = self.settings
        if not s.hosted_base_url or not s.llm_api_key:
            raise ProviderError("hosted provider needs HOSTED_BASE_URL and LLM_API_KEY")
        messages, removed = build_messages(question, passages, s, strict=strict)
        payload = {
            "model": s.llm_model, "messages": messages, "temperature": s.temperature,
            "response_format": {"type": "json_object"},
        }
        try:
            r = self.client.post(f"{s.hosted_base_url.rstrip('/')}/chat/completions",
                                 json=payload,
                                 headers={"Authorization": f"Bearer {s.llm_api_key}"})
            r.raise_for_status()
            data = r.json()
            content = data["choices"][0]["message"]["content"]
        except (httpx.HTTPStatusError) as exc:
            # status code only: the request (and its Authorization header) stays out of the message
            raise ProviderError(f"hosted call failed with HTTP {exc.response.status_code}") from None
        except (httpx.HTTPError, KeyError, IndexError, ValueError) as exc:
            raise ProviderError(f"hosted call failed: {type(exc).__name__}") from None
        usage = data.get("usage") or {}
        usage_var.set({"tokens_in": int(usage.get("prompt_tokens", 0)),
                       "tokens_out": int(usage.get("completion_tokens", 0)),
                       "injection_removed": removed})
        return parse_answer(content)
