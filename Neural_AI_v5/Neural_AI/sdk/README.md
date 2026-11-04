# neuralai: Python SDK for the Neural AI API

```bash
pip install neuralai          # once published to PyPI
pip install ./sdk             # install from this repository today
```

> This package is **not** published on PyPI by this project. Until you publish it
> (`python -m build && twine upload dist/*`), install it from the `sdk/` folder.

```python
from neuralai import Neural

client = Neural(api_key="nrl_...", base_url="https://your-app.onrender.com")
r = client.chat.completions.create(model="neural-1", messages=[{"role": "user", "content": "Hello"}])
print(r.choices[0].message.content)
```

Streaming: `with client.chat.completions.create(..., stream=True) as s: for t in s.iter_text(): print(t, end="")`.
Errors: `AuthenticationError`, `RateLimitError` (with `retry_after`), `InvalidRequestError`, `NotFoundError`, `ServerError`, `APIConnectionError`.
Environment variables: `NEURAL_API_KEY`, `NEURAL_BASE_URL`. See `examples/`.
