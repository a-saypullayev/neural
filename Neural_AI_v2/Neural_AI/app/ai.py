"""Real inference through any OpenAI-compatible provider (Ollama by default). No canned responses."""
import time

from . import config

_client = None


class AIError(Exception):
    def __init__(self, message, unavailable=False):
        super().__init__(message)
        self.unavailable = unavailable


def client():
    global _client
    if _client is None:
        from openai import OpenAI
        _client = OpenAI(base_url=config.AI_BASE_URL, api_key=config.AI_API_KEY or "none",
                         timeout=config.AI_TIMEOUT, max_retries=0)
    return _client


def resolve_model(name):
    """Map the public model name (or raw provider model) to the provider model; None if unknown."""
    if not name or name in (config.AI_PUBLIC_MODEL, config.AI_MODEL, "neural"):
        return config.AI_MODEL
    return None


def _kwargs(messages, max_tokens, temperature, stream):
    kw = dict(model=config.AI_MODEL, messages=messages, max_tokens=max_tokens, stream=stream)
    if temperature is not None:
        kw["temperature"] = temperature
    if config.AI_REASONING_EFFORT:
        kw["extra_body"] = {"reasoning_effort": config.AI_REASONING_EFFORT}
    return kw


def _wrap(e):
    name = type(e).__name__
    unavailable = name in ("APIConnectionError", "APITimeoutError")
    return AIError("The AI model is unavailable right now." if unavailable else "The AI provider returned an error.", unavailable)


def complete(messages, max_tokens, temperature=None):
    """Non-streaming. Returns (text, finish_reason, usage_dict_or_None)."""
    try:
        r = client().chat.completions.create(**_kwargs(messages, max_tokens, temperature, False))
    except Exception as e:
        raise _wrap(e) from e
    ch = r.choices[0]
    usage = None
    if getattr(r, "usage", None):
        usage = {"prompt_tokens": r.usage.prompt_tokens, "completion_tokens": r.usage.completion_tokens, "total_tokens": r.usage.total_tokens}
    return ch.message.content or "", ch.finish_reason or "stop", usage


def stream(messages, max_tokens, temperature=None):
    """Streaming generator yielding ('delta', text) items then ('finish', reason)."""
    try:
        it = client().chat.completions.create(**_kwargs(messages, max_tokens, temperature, True))
        finish = "stop"
        for chunk in it:
            if not chunk.choices:
                continue
            c = chunk.choices[0]
            if c.delta and c.delta.content:
                yield "delta", c.delta.content
            if c.finish_reason:
                finish = c.finish_reason
        yield "finish", finish
    except AIError:
        raise
    except Exception as e:
        raise _wrap(e) from e


def web_search(query: str, n: int = 5) -> str:
    """Optional DuckDuckGo context for the chat UI. Returns '' if the library/network is unavailable."""
    try:
        from ddgs import DDGS
        results = DDGS().text(query, max_results=n)
        return "\n".join(f"[{i+1}] {r.get('title','')}: {r.get('body','')} ({r.get('href','')})" for i, r in enumerate(results))
    except Exception:
        return ""


def now_ts() -> int:
    return int(time.time())
