"""A simple multi-turn chat loop."""
from neuralai import Neural

client = Neural()
history = [{"role": "system", "content": "You are a helpful assistant."}]
while True:
    text = input("You: ").strip()
    if text in ("", "exit", "quit"):
        break
    history.append({"role": "user", "content": text})
    print("Neural: ", end="", flush=True)
    answer = ""
    with client.chat.completions.create(messages=history, stream=True) as s:
        for piece in s.iter_text():
            answer += piece
            print(piece, end="", flush=True)
    print()
    history.append({"role": "assistant", "content": answer})
