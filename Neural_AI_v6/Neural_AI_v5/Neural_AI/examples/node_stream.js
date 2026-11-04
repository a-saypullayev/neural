// Node.js 18+ streaming example (no dependencies).
const BASE_URL = process.env.NEURAL_BASE_URL || "http://127.0.0.1:8000";
const API_KEY = process.env.NEURAL_API_KEY;

async function main() {
  const res = await fetch(`${BASE_URL}/v1/chat/completions`, {
    method: "POST",
    headers: { Authorization: `Bearer ${API_KEY}`, "Content-Type": "application/json" },
    body: JSON.stringify({ model: "neural-1", stream: true, messages: [{ role: "user", content: "Count to five." }] }),
  });
  if (!res.ok) throw new Error(`${res.status}: ${(await res.json()).error.message}`);
  const decoder = new TextDecoder();
  let buffer = "";
  for await (const chunk of res.body) {
    buffer += decoder.decode(chunk, { stream: true });
    let i;
    while ((i = buffer.indexOf("\n\n")) >= 0) {
      const event = buffer.slice(0, i).trim();
      buffer = buffer.slice(i + 2);
      if (!event.startsWith("data: ")) continue;
      const data = event.slice(6);
      if (data === "[DONE]") { process.stdout.write("\n"); return; }
      const delta = JSON.parse(data).choices?.[0]?.delta?.content;
      if (delta) process.stdout.write(delta);
    }
  }
}
main().catch((e) => { console.error(e.message); process.exit(1); });
