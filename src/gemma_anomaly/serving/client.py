"""OpenAI compatible client for the Gemma endpoint.

One route for the untuned base model and one for the tuned adapter, so the two
can be compared on identical inputs. The adapter is never silently substituted
during an evaluation run.

vLLM is the candidate runtime. Architecture support, quantization, adapter
loading, and structured output must be tested against the exact Gemma revision
before this is treated as working.
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass

from .. import settings


@dataclass(frozen=True)
class Route:
    name: str
    model: str
    adapter: str | None
    base_url: str


def base_route() -> Route:
    return Route("base", settings.SERVING_MODEL, None, settings.SERVING_BASE_URL)


def tuned_route() -> Route:
    return Route("tuned", settings.SERVING_MODEL,
                 settings.SERVING_ADAPTER or None, settings.SERVING_BASE_URL)


class ServingError(RuntimeError):
    pass


def complete(messages: list[dict], route: Route, *, max_tokens: int = 400,
             temperature: float = 0.0, timeout: int = 45,
             extra_headers: dict | None = None) -> tuple[str, float]:
    """Returns (text, latency_ms). Raises ServingError on transport failure."""
    if not route.model:
        raise ServingError("GEMMA_MODEL is unset. Pin the exact checkpoint revision.")

    model = route.adapter or route.model  # vLLM addresses a LoRA by its served name
    body = json.dumps({
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "stream": False,
    }).encode()

    headers = {"Content-Type": "application/json"}
    if extra_headers:
        headers.update(extra_headers)

    req = urllib.request.Request(
        f"{route.base_url.rstrip('/')}/chat/completions", data=body, headers=headers
    )
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode())
    except Exception as exc:
        raise ServingError(str(exc)) from exc
    latency_ms = (time.perf_counter() - started) * 1000.0

    try:
        return payload["choices"][0]["message"]["content"], latency_ms
    except (KeyError, IndexError) as exc:
        raise ServingError(f"unexpected response shape: {payload}") from exc


def health(route: Route | None = None, timeout: int = 5) -> dict:
    route = route or base_route()
    try:
        with urllib.request.urlopen(
            f"{route.base_url.rstrip('/')}/models", timeout=timeout
        ) as resp:
            return {"reachable": True, "models": json.loads(resp.read().decode())}
    except Exception as exc:
        return {"reachable": False, "error": str(exc)}
