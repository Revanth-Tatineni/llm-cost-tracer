"""Best-effort token extraction from provider SDK response objects, so a wrapped call doesn't
have to compute its own usage. Each extractor takes whatever the wrapped function returned and
gives back (input_tokens, output_tokens), or None if that object doesn't match -- the tracer
treats None as "leave the token counts at 0, the caller can set them manually instead."

Response objects are read duck-typed (attribute first, dict fallback) so this works against
both a real SDK object and a plain dict built in a test, without importing either SDK.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

Extractor = Callable[[Any], "tuple[int, int] | None"]


def _usage_of(response: Any) -> Any:
    usage = getattr(response, "usage", None)
    if usage is None and isinstance(response, dict):
        usage = response.get("usage")
    return usage


def _field(usage: Any, attr: str, key: str) -> int | None:
    value = getattr(usage, attr, None)
    if value is None and isinstance(usage, dict):
        value = usage.get(key)
    return value


def extract_anthropic(response: Any) -> tuple[int, int] | None:
    """Anthropic Messages API: response.usage.{input_tokens,output_tokens}."""
    usage = _usage_of(response)
    if usage is None:
        return None
    input_tokens = _field(usage, "input_tokens", "input_tokens")
    output_tokens = _field(usage, "output_tokens", "output_tokens")
    if input_tokens is None or output_tokens is None:
        return None
    return int(input_tokens), int(output_tokens)


def extract_openai(response: Any) -> tuple[int, int] | None:
    """OpenAI Chat Completions: response.usage.{prompt_tokens,completion_tokens}."""
    usage = _usage_of(response)
    if usage is None:
        return None
    input_tokens = _field(usage, "prompt_tokens", "prompt_tokens")
    output_tokens = _field(usage, "completion_tokens", "completion_tokens")
    if input_tokens is None or output_tokens is None:
        return None
    return int(input_tokens), int(output_tokens)


_EXTRACTORS: dict[str, Extractor] = {
    "anthropic": extract_anthropic,
    "openai": extract_openai,
}


def extract_tokens(provider: str, response: Any) -> tuple[int, int] | None:
    extractor = _EXTRACTORS.get(provider)
    if extractor is None:
        return None
    return extractor(response)


def register_extractor(provider: str, extractor: Extractor) -> None:
    """Add support for another SDK's response shape, e.g. register_extractor("gemini", ...)."""
    _EXTRACTORS[provider] = extractor
