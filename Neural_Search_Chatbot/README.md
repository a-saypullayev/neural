# Neural — private AI chat

Neural is a FastAPI chat app with account login, private server-side chat history, per-account memories, daily usage limits, and SQLite for local development / PostgreSQL for deployment.

## Local Windows setup

1. Install Python 3.11+ and Ollama. Pull your model with `ollama pull qwen3.5:4b`.
2. Copy `.env.example` to `.env` and keep the default local Ollama endpoint/model.
3. In PowerShell, from this folder:

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:APP_SECRET = (python -c "import secrets; print(secrets.token_urlsafe(48))")
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Open http://127.0.0.1:8000. The local database is created in `data/neural.db`.

## Deploy on Render

The included `render.yaml` describes a Render web service and a **paid Render PostgreSQL database**. Review the selected plans and costs in Render before deploying. Render's free PostgreSQL database expires after 30 days, so it is not appropriate for permanent user histories.

1. Push this project to a private or public GitHub repository.
2. In Render, create a Blueprint from that repository and review the web-service and database plans before applying.
3. Set `AI_BASE_URL`, `AI_API_KEY`, and `AI_MODEL` in the Render service environment. These must point to a hosted OpenAI-compatible AI provider. `127.0.0.1:11434` will **not** reach Ollama on your own laptop from Render.
4. Render connects `DATABASE_URL` to PostgreSQL. Keep `APP_SECRET` private; Render generates it from the Blueprint.
5. Deploy and test account registration, sign-in, chat history, and memories.

## Security and usage limits

- Passwords are stored as salted PBKDF2-HMAC-SHA256 hashes, never as plaintext.
- Sessions use a signed, HTTP-only, SameSite=Lax cookie (Secure on Render).
- Chats and memories are scoped to the authenticated account on every database query.
- Default account limits: 25 AI requests per day, 15,000 input characters per day, 8,000 characters per individual user message, and 1,024 generated tokens per response.
- These are starter safeguards, not a complete anti-abuse system. Before a public launch, add email verification/password reset, login/IP throttling, bot protection, monitoring, backups, and a provider-side spending cap. Configure database backups appropriate to the data you need to retain.

## Important AI hosting note

A public Render deployment cannot use the Ollama server running at `127.0.0.1` on your personal computer. Configure a hosted API provider, or separately deploy a secured inference server. Never expose the raw Ollama port directly to the public internet.
