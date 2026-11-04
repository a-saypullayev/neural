#!/usr/bin/env sh
# Usage: NEURAL_API_KEY=nrl_... NEURAL_BASE_URL=https://your-app.onrender.com sh curl.sh
BASE="${NEURAL_BASE_URL:-http://127.0.0.1:8000}"

echo "== Models"
curl -s "$BASE/v1/models" -H "Authorization: Bearer $NEURAL_API_KEY"

echo; echo "== Chat completion"
curl -s "$BASE/v1/chat/completions" \
  -H "Authorization: Bearer $NEURAL_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model":"neural-1","messages":[{"role":"user","content":"Say hello in five words."}]}'

echo; echo "== Streaming (-N disables buffering)"
curl -N -s "$BASE/v1/chat/completions" \
  -H "Authorization: Bearer $NEURAL_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model":"neural-1","stream":true,"messages":[{"role":"user","content":"Count to five."}]}'
