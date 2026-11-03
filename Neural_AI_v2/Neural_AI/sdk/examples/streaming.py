"""Stream a reply token by token."""
from neuralai import Neural

client = Neural()
with client.chat.completions.create(messages=[{"role": "user", "content": "Write a haiku about the sea."}], stream=True) as stream:
    for text in stream.iter_text():
        print(text, end="", flush=True)
print()
