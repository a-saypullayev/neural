// Works in Node 18+ and in browsers. Never put your API key in public browser code:
// call the API from your own server instead.
const BASE_URL = process.env.NEURAL_BASE_URL || "http://127.0.0.1:8000";
const API_KEY = process.env.NEURAL_API_KEY;

async function main() {
  const res = await fetch(`${BASE_URL}/v1/chat/completions`, {
    method: "POST",
    headers: { Authorization: `Bearer ${API_KEY}`, "Content-Type": "application/json" },
    body: JSON.stringify({
      model: "neural-1",
      messages: [{ role: "user", content: "Say hello in five words." }],
    }),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(`${res.status}: ${data.error.message}`);
  console.log(data.choices[0].message.content);
}
main().catch((e) => { console.error(e.message); process.exit(1); });
