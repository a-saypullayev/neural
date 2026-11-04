"""Neural AI client: models, chat completions, streaming, retries."""
import json
import os
import time
from typing import Iterator, List, Optional

import requests

from .errors import APIConnectionError, NeuralError, from_response

DEFAULT_BASE_URL = "http://127.0.0.1:8000"


class Obj(dict):
    """A dict that also allows attribute access (response.choices[0].message.content)."""

    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError:
            raise AttributeError(name)


def _wrap(value):
    if isinstance(value, dict):
        return Obj({k: _wrap(v) for k, v in value.items()})
    if isinstance(value, list):
        return [_wrap(v) for v in value]
    return value


class Stream:
    """Iterator over streamed chunks. Use as a context manager or call close()."""

    def __init__(self, response: requests.Response):
        self._response = response

    def __iter__(self) -> Iterator[Obj]:
        try:
            for raw in self._response.iter_lines(decode_unicode=True):
                if not raw or not raw.startswith("data:"):
                    continue
                data = raw[5:].strip()
                if data == "[DONE]":
                    return
                payload = json.loads(data)
                if isinstance(payload, dict) and "error" in payload:
                    raise from_response(502, payload)
                yield _wrap(payload)
        except requests.RequestException as e:
            raise APIConnectionError(str(e)) from e
        finally:
            self.close()

    def iter_text(self) -> Iterator[str]:
        """Yield only the text pieces of the reply."""
        for chunk in self:
            content = chunk["choices"][0]["delta"].get("content")
            if content:
                yield content

    def close(self):
        self._response.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


class _Http:
    def __init__(self, api_key, base_url, timeout, max_retries):
        self.base_url, self.timeout, self.max_retries = base_url.rstrip("/"), timeout, max_retries
        self.session = requests.Session()
        self.session.headers.update({"Authorization": f"Bearer {api_key}", "User-Agent": "neuralai-python/0.1.0"})

    def request(self, method, path, json_body=None, stream=False):
        attempt = 0
        while True:
            try:
                resp = self.session.request(method, self.base_url + path, json=json_body, timeout=self.timeout, stream=stream)
            except requests.RequestException as e:
                if attempt < self.max_retries:
                    attempt += 1
                    time.sleep(min(2 ** attempt * 0.5, 8))
                    continue
                raise APIConnectionError(f"Could not reach {self.base_url}: {e}") from e
            if resp.status_code in (502, 503) and attempt < self.max_retries:
                resp.close()
                attempt += 1
                time.sleep(min(2 ** attempt * 0.5, 8))
                continue
            if resp.status_code >= 400:
                try:
                    body = resp.json()
                except ValueError:
                    body = None
                ra = resp.headers.get("Retry-After")
                resp.close()
                raise from_response(resp.status_code, body, int(ra) if ra and ra.isdigit() else None)
            return resp


class _Completions:
    def __init__(self, http):
        self._http = http

    def create(self, *, messages: List[dict], model: str = "neural-1", stream: bool = False,
               temperature: Optional[float] = None, max_tokens: Optional[int] = None):
        """Create a chat completion. Returns a response object, or a Stream when stream=True."""
        body = {"model": model, "messages": messages, "stream": bool(stream)}
        if temperature is not None:
            body["temperature"] = temperature
        if max_tokens is not None:
            body["max_tokens"] = max_tokens
        resp = self._http.request("POST", "/v1/chat/completions", body, stream=stream)
        if stream:
            return Stream(resp)
        try:
            return _wrap(resp.json())
        except ValueError as e:
            raise NeuralError("The server returned an invalid response.") from e


class _Chat:
    def __init__(self, http):
        self.completions = _Completions(http)


class _Models:
    def __init__(self, http):
        self._http = http

    def list(self):
        return _wrap(self._http.request("GET", "/v1/models").json())


class Neural:
    """Client for the Neural AI API.

    >>> client = Neural(api_key="nrl_...", base_url="https://your-app.onrender.com")
    >>> client.chat.completions.create(messages=[{"role": "user", "content": "Hi"}])
    """

    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None, timeout: float = 120.0, max_retries: int = 2):
        api_key = api_key or os.environ.get("NEURAL_API_KEY")
        if not api_key:
            raise NeuralError("No API key. Pass api_key=... or set the NEURAL_API_KEY environment variable.")
        base_url = base_url or os.environ.get("NEURAL_BASE_URL") or DEFAULT_BASE_URL
        http = _Http(api_key, base_url, timeout, max_retries)
        self.chat = _Chat(http)
        self.models = _Models(http)
