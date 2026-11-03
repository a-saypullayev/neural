"""Call the Neural API from plain Python (pip install requests)."""
import json
import os

import requests

BASE_URL = os.environ.get("NEURAL_BASE_URL", "http://127.0.0.1:8000")
API_KEY = os.environ["NEURAL_API_KEY"]
HEADERS = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}

# 1) Non-streaming
r = requests.post(f"{BASE_URL}/v1/chat/completions", headers=HEADERS, timeout=120, json={
    "model": "neural-1",
    "messages": [{"role": "user", "content": "Say hello in five words."}],
})
r.raise_for_status()
print(r.json()["choices"][0]["message"]["content"])

# 2) Streaming (server-sent events)
with requests.post(f"{BASE_URL}/v1/chat/completions", headers=HEADERS, stream=True, timeout=120, json={
    "model": "neural-1",
    "stream": True,
    "messages": [{"role": "user", "content": "Count to five."}],
}) as resp:
    resp.raise_for_status()
    for line in resp.iter_lines(decode_unicode=True):
        if not line or not line.startswith("data: "):
            continue
        data = line[6:]
        if data == "[DONE]":
            break
        delta = json.loads(data)["choices"][0]["delta"].get("content", "")
        print(delta, end="", flush=True)
print()
