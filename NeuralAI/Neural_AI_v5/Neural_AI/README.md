# Neural AI

Neural is a FastAPI chat app with username + password login (no email needed), private server-side chat history, per-account memories, daily usage limits, an **API key dashboard** and an OpenAI-style **REST API**. It uses SQLite locally and PostgreSQL on Render, and talks to any OpenAI-compatible model server (Ollama + `qwen3.5:4b` by default).

| Page | Purpose |
|---|---|
| `/` | Chat (sign in, chats, memories, optional web search) |
| `/keys` | Generate, name, copy-once, and revoke API keys |
| `/doc` | Documentation |
| `/policy` | Privacy, data handling, acceptable use, limits |
| `/v1/models`, `/v1/chat/completions` | REST API (Bearer key, JSON or streaming, rate limited) |

## Local Windows setup

1. Install Python 3.11+ and [Ollama](https://ollama.com). Run `ollama pull qwen3.5:4b`.
2. Double-click `start.bat`. It creates `.venv`, installs packages, creates `.env` (with a generated `APP_SECRET`) and starts the server.
3. Open http://127.0.0.1:8000.

Manual start (PowerShell):

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python scripts\init_env.py
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

The local database is `data/neural.db`. If `qwen3.5:4b` feels slow because it "thinks" first, set `AI_REASONING_EFFORT=none` in `.env`.

## Environment variables

| Variable | Required | Notes |
|---|---|---|
| `APP_SECRET` | yes (production) | Signs sessions and hashes codes. Render generates it. |
| `DATABASE_URL` | production | PostgreSQL URL. Empty = local SQLite. |
| `AI_BASE_URL`, `AI_API_KEY`, `AI_MODEL` | yes | OpenAI-compatible provider. Default `http://127.0.0.1:11434/v1`, `ollama`, `qwen3.5:4b`. |
| `AI_PUBLIC_MODEL` | no | Model id shown by the API (default `neural-1`). |
| `AI_REASONING_EFFORT` | no | e.g. `none`. |
| `FREE_CHAT_TOKENS_PER_DAY` | no | Free plan: web chat tokens per account per day (10000). |
| `FREE_MAX_ACTIVE_KEYS`, `FREE_KEYS_PER_DAY`, `FREE_TOKENS_PER_KEY_PER_DAY` | no | Free plan: active API keys (3), new keys per day (3), tokens per key per day (10000). |
| `MAX_MESSAGE_CHARS`, `MAX_OUTPUT_TOKENS` | no | Web chat message size and reply length (8000 / 1024). |
| `API_RATE_LIMIT_PER_MIN`, `API_DAILY_REQUESTS`, `API_MAX_OUTPUT_TOKENS` | no | API limits (30 / 500 / 2048). |

## Deploy on Render

1. Push this folder to GitHub. In Render, create a **Blueprint** from the repo and review plan costs (the Blueprint includes a paid PostgreSQL database).
2. Set `AI_BASE_URL`, `AI_API_KEY`, `AI_MODEL` to a **hosted** OpenAI-compatible provider. Render cannot reach Ollama on your own PC (`127.0.0.1`).
3. Deploy, then register an account, create a key at `/keys`, and call the API (see `/doc`).

## Database safety

Startup only runs `CREATE TABLE IF NOT EXISTS` for **new tables prefixed `nx_`** plus a small `nx_migrations` table. It never resets or deletes any existing data, and it only ever alters this app's own `nx_` tables (for example adding the `tokens` column). Because those tables are new, accounts from a previous version of the app are **not** automatically imported; see "Known limits" below.

## Install as an app

- **Windows:** open `/download` on your site and download `NeuralAI.exe`. It is a tiny native launcher that opens the site in its own Edge/Chrome app window. The server writes its own address into the file as it is downloaded, so it works on any domain. Source is in `windows-app/` (`build.sh` rebuilds it). The exe is unsigned, so Windows SmartScreen shows a warning ("More info" then "Run anyway"). Set `PUBLIC_URL` (e.g. `https://your-app.onrender.com`) if the address comes out wrong behind a proxy.
- **Android, iPhone, Mac, Linux:** the site is an installable PWA. Use "Install app" / "Add to Home Screen" in the browser.

## Python SDK

The `neuralai` package source is in `sdk/`. It is **not published on PyPI** by this project.

```bash
pip install ./sdk
```

After you publish it yourself (`python -m build` and `twine upload`), `pip install neuralai` will work. Examples are in `sdk/examples/`; examples for Python (requests), JavaScript, Node.js, PHP and cURL are in `examples/`.

## Tests

```bash
python -m unittest discover -s tests -v
```

`tests/test_core.py` covers hashing, sessions, accounts, API keys, quotas and the SDK (against a local stub server). `tests/test_api.py` runs HTTP smoke tests when `fastapi` and `httpx` are installed.

## Security notes

- Passwords: salted PBKDF2-HMAC-SHA256. API keys are stored hashed only.
- Rate limits for the API and login are kept in memory per server process (fine for one Render instance; use Redis if you scale out).
- Add provider-side spending caps, backups and monitoring before a public launch.

## Known limits

- Image/video generation (Replicate) from the old `start.bat` text is not included.
- Users from a previous deployment's tables are not migrated automatically.
