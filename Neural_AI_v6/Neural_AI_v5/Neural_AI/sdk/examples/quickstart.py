"""Basic chat completion. Set NEURAL_API_KEY and NEURAL_BASE_URL first."""
from neuralai import Neural

client = Neural()  # reads NEURAL_API_KEY and NEURAL_BASE_URL from the environment

print([m.id for m in client.models.list().data])

reply = client.chat.completions.create(
    model="neural-1",
    messages=[
        {"role": "system", "content": "You are concise."},
        {"role": "user", "content": "Explain what an API key is in one sentence."},
    ],
    temperature=0.5,
    max_tokens=200,
)
print(reply.choices[0].message.content)
print(reply.usage)
