"""Neural AI: FastAPI application (web chat, accounts, API keys and the /v1 REST API)."""
import json
import logging
import os
import re
import secrets
import time
from contextlib import asynccontextmanager
from typing import Any, List, Optional
from urllib.parse import urlparse

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import ai, config, db, mailer, security, services
from .ratelimit import limiter
from .services import ServiceError

log = logging.getLogger("neural")
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")
COOKIE = "neural_session"


@asynccontextmanager
async def lifespan(app: FastAPI):
    if not config.APP_SECRET:
        if config.ON_RENDER:
            raise RuntimeError("APP_SECRET must be set in production.")
        config.APP_SECRET = secrets.token_urlsafe(48)
        log.warning("APP_SECRET not set: using a temporary one. Sessions reset on restart.")
    db.migrate()
    yield


app = FastAPI(title="Neural AI", version="2.0.0", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)


# ------------------------------------------------------------ middleware
@app.middleware("http")
async def protect(request: Request, call_next):
    if request.method in ("POST", "PUT", "PATCH", "DELETE") and request.url.path.startswith("/api/"):
        origin = request.headers.get("origin")
        if origin and urlparse(origin).netloc != request.headers.get("host", ""):
            return JSONResponse({"error": {"message": "Cross-site request blocked.", "code": "bad_origin"}}, status_code=403)
    resp = await call_next(request)
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("X-Frame-Options", "DENY")
    resp.headers.setdefault("Referrer-Policy", "same-origin")
    resp.headers.setdefault(
        "Content-Security-Policy",
        "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'",
    )
    if request.url.path.startswith("/api/") or request.url.path.startswith("/v1/"):
        resp.headers.setdefault("Cache-Control", "no-store")
    return resp


def v1_body(message, code, typ="invalid_request_error"):
    return {"error": {"message": message, "type": typ, "code": code}}


@app.exception_handler(ServiceError)
async def service_error_handler(request: Request, exc: ServiceError):
    headers = {"Retry-After": str(exc.retry_after)} if exc.retry_after else None
    if request.url.path.startswith("/v1/"):
        typ = "authentication_error" if exc.status == 401 else "rate_limit_error" if exc.status == 429 else "invalid_request_error"
        return JSONResponse(v1_body(exc.message, exc.code, typ), status_code=exc.status, headers=headers)
    return JSONResponse({"error": {"message": exc.message, "code": exc.code}}, status_code=exc.status, headers=headers)


@app.exception_handler(RequestValidationError)
async def validation_handler(request: Request, exc: RequestValidationError):
    if request.url.path.startswith("/v1/"):
        return JSONResponse(v1_body("Invalid request body.", "invalid_request"), status_code=400)
    return JSONResponse({"error": {"message": "Invalid request.", "code": "invalid_request"}}, status_code=400)


# --------------------------------------------------------------- helpers
def client_ip(request: Request) -> str:
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[-1].strip()
    return request.client.host if request.client else "unknown"


def session_user(request: Request):
    token = request.cookies.get(COOKIE)
    uid = security.read_session(token) if token else None
    return services.get_user(uid) if uid else None


def require_user(request: Request, verified: bool = True) -> dict:
    u = session_user(request)
    if not u:
        raise ServiceError("Please sign in.", 401, "not_authenticated")
    if verified and not u["email_verified"]:
        raise ServiceError("Verify your email address to use this feature.", 403, "email_not_verified")
    return u


def throttle(key: str, limit: int, window: int, message="Too many requests. Slow down."):
    ok, _, retry = limiter.hit(key, limit, window)
    if not ok:
        raise ServiceError(message, 429, "rate_limited", retry_after=retry)


def set_session(resp: JSONResponse, user_id: str):
    resp.set_cookie(COOKIE, security.sign_session(user_id), max_age=config.SESSION_DAYS * 86400,
                    httponly=True, samesite="lax", secure=config.SECURE_COOKIES, path="/")


# ------------------------------------------------------------------ models
class RegisterIn(BaseModel):
    username: str
    password: str
    email: Optional[str] = None


class CodeIn(BaseModel):
    code: str


class LoginIn(BaseModel):
    username: str
    password: str


class ChatIn(BaseModel):
    message: str
    chat_id: Optional[str] = None
    search: bool = False


class TextIn(BaseModel):
    content: str


class NameIn(BaseModel):
    name: str


class TitleIn(BaseModel):
    title: str


# -------------------------------------------------------------------- pages
def page(name: str):
    return FileResponse(os.path.join(STATIC_DIR, name), media_type="text/html")


@app.get("/")
def home():
    return page("index.html")


@app.get("/keys")
def keys_page():
    return page("keys.html")


@app.get("/doc")
def doc_page():
    return page("doc.html")


@app.get("/policy")
def policy_page():
    return page("policy.html")


@app.get("/favicon.ico")
def favicon():
    return FileResponse(os.path.join(STATIC_DIR, "favicon.svg"), media_type="image/svg+xml")


URL_MARKER = b"@@NEURAL_URL@@"
URL_SLOT = 256
HOST_RE = re.compile(r"^[A-Za-z0-9.-]{1,200}(:\d{1,5})?$")


def site_origin(request: Request) -> str:
    """The address people use to reach this site, e.g. https://neural-6mzi.onrender.com"""
    if config.PUBLIC_URL.startswith(("http://", "https://")):
        return config.PUBLIC_URL
    host = (request.headers.get("host") or "").strip()
    if not HOST_RE.match(host):
        raise ServiceError("Could not work out this site's address. Set PUBLIC_URL.", 500, "no_public_url")
    local = host.split(":")[0] in ("localhost", "127.0.0.1")
    proto = request.headers.get("x-forwarded-proto", "").split(",")[0].strip() or ("http" if local else "https")
    return f"{proto if proto in ('http', 'https') else 'https'}://{host}"


@app.get("/download")
def download_page():
    return page("download.html")


@app.get("/download/NeuralAI.exe")
def download_windows(request: Request):
    """Windows app: a tiny launcher .exe with this site's address written into it."""
    origin = site_origin(request).encode("ascii")
    if len(origin) >= URL_SLOT:
        raise ServiceError("Site address is too long for the app.", 500, "url_too_long")
    with open(os.path.join(BASE_DIR, "downloads", "NeuralAI.template.exe"), "rb") as f:
        data = f.read()
    i = data.find(URL_MARKER)
    if i < 0:
        raise ServiceError("Windows app is not available.", 404, "not_found")
    data = data[:i] + origin + b"\x00" * (URL_SLOT - len(origin)) + data[i + URL_SLOT:]
    return Response(data, media_type="application/vnd.microsoft.portable-executable",
                    headers={"Content-Disposition": 'attachment; filename="NeuralAI.exe"', "Cache-Control": "no-store"})


@app.get("/manifest.webmanifest")
def manifest():
    return FileResponse(os.path.join(STATIC_DIR, "manifest.webmanifest"), media_type="application/manifest+json")


@app.get("/sw.js")
def service_worker():
    # Must be served from the site root so it can control every page; never cache it.
    return FileResponse(os.path.join(STATIC_DIR, "sw.js"), media_type="text/javascript",
                        headers={"Cache-Control": "no-cache", "Service-Worker-Allowed": "/"})


@app.get("/api/health")
def health():
    return {"status": "ok"}


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


# --------------------------------------------------------------------- auth
@app.get("/api/auth/me")
def me(request: Request):
    u = session_user(request)
    if not u:
        return {"user": None}
    return {"user": services.public_user(u), "usage": services.usage_summary(u)}


def send_verification(u: dict) -> None:
    """Create a code and email it. A failed send does not burn the user's cooldown."""
    code = services.issue_code(u)
    try:
        mailer.send_code(u["email_to"], code)
    except mailer.MailError:
        services.cancel_latest_code(u["id"])
        raise ServiceError("We could not send the verification email. Try again in a minute.", 503, "email_failed")


@app.post("/api/auth/register")
def register(request: Request, body: RegisterIn):
    throttle("reg:" + client_ip(request), config.SIGNUPS_PER_IP_HOUR, 3600, "Too many sign-ups from this network. Try again later.")
    u = services.register(body.username, body.password, email=body.email)
    if not u["email_verified"]:
        try:
            send_verification(u)
        except ServiceError:
            services.delete_unverified(u["id"])  # let them retry cleanly
            raise
    resp = JSONResponse({"user": services.public_user(u)}, status_code=201)
    set_session(resp, u["id"])
    return resp


@app.post("/api/auth/verify")
def verify_email(request: Request, body: CodeIn):
    u = require_user(request, verified=False)
    throttle("verify:" + u["id"], 20, 3600, "Too many attempts. Try again later.")
    services.verify_code(u, body.code)
    return {"user": services.public_user(services.get_user(u["id"]))}


@app.post("/api/auth/resend")
def resend_code(request: Request):
    u = require_user(request, verified=False)
    if u["email_verified"]:
        raise ServiceError("This email is already verified.", 400, "already_verified")
    if not u.get("email_to"):
        raise ServiceError("No email on this account.", 400, "no_email")
    throttle("resend:" + client_ip(request), 10, 3600, "Too many requests. Try again later.")
    send_verification(u)
    return {"ok": True}


@app.post("/api/auth/login")
def login(request: Request, body: LoginIn):
    throttle(f"login:{client_ip(request)}:{body.username.strip().lower()}", 10, 300, "Too many sign-in attempts. Try again in a few minutes.")
    u = services.authenticate(body.username, body.password)
    resp = JSONResponse({"user": services.public_user(u)})
    set_session(resp, u["id"])
    return resp


@app.post("/api/auth/logout")
def logout():
    resp = JSONResponse({"ok": True})
    resp.delete_cookie(COOKIE, path="/")
    return resp


# --------------------------------------------------------------------- chat
@app.get("/api/chats")
def chats(request: Request):
    u = require_user(request)
    return {"chats": services.list_chats(u["id"])}


@app.get("/api/chats/{chat_id}")
def chat_detail(request: Request, chat_id: str):
    u = require_user(request)
    c = services.get_chat(u["id"], chat_id)
    if not c:
        raise ServiceError("Chat not found.", 404, "not_found")
    return {"id": c["id"], "title": c["title"], "messages": services.chat_messages(u["id"], chat_id)}


@app.delete("/api/chats/{chat_id}")
def chat_delete(request: Request, chat_id: str):
    u = require_user(request)
    if not services.delete_chat(u["id"], chat_id):
        raise ServiceError("Chat not found.", 404, "not_found")
    return {"ok": True}


@app.patch("/api/chats/{chat_id}")
def chat_rename(request: Request, chat_id: str, body: TitleIn):
    u = require_user(request)
    if not services.rename_chat(u["id"], chat_id, body.title):
        raise ServiceError("Chat not found.", 404, "not_found")
    return {"ok": True}


@app.get("/api/memories")
def memories(request: Request):
    u = require_user(request)
    return {"memories": services.list_memories(u["id"])}


@app.post("/api/memories")
def memory_add(request: Request, body: TextIn):
    u = require_user(request)
    return services.add_memory(u["id"], body.content)


@app.delete("/api/memories/{memory_id}")
def memory_delete(request: Request, memory_id: str):
    u = require_user(request)
    if not services.delete_memory(u["id"], memory_id):
        raise ServiceError("Memory not found.", 404, "not_found")
    return {"ok": True}


def ndjson(obj) -> str:
    return json.dumps(obj, ensure_ascii=False) + "\n"


@app.post("/api/chat")
def chat(request: Request, body: ChatIn):
    u = require_user(request)
    msg = (body.message or "").strip()
    if not msg:
        raise ServiceError("Type a message first.", 400, "empty_message")
    if len(msg) > config.MAX_MESSAGE_CHARS:
        raise ServiceError(f"Message too long (max {config.MAX_MESSAGE_CHARS} characters).", 400, "message_too_long")
    throttle("chat:" + u["id"], 20, 60)
    chat_id = body.chat_id
    if chat_id and not services.get_chat(u["id"], chat_id):
        raise ServiceError("Chat not found.", 404, "not_found")
    limits = services.plan_limits(u)
    est_in = services.est_tokens(msg)
    left = services.tokens_left(u["id"], "chat", limits["chat_tokens_per_day"], est_in, "Your account")
    max_out = max(1, min(config.MAX_OUTPUT_TOKENS, left - est_in))
    if not chat_id:
        chat_id = services.create_chat(u["id"], msg[:50])
    history = services.chat_messages(u["id"], chat_id)[-20:]
    services.add_message(u["id"], chat_id, "user", msg)
    ctx = ai.web_search(msg) if body.search else ""
    msgs = [{"role": "system", "content": services.system_prompt_for(u["id"], ctx)}]
    total = 0
    trimmed = []
    for m in reversed(history):
        total += len(m["content"])
        if total > 12000:
            break
        trimmed.append({"role": m["role"], "content": m["content"]})
    msgs += list(reversed(trimmed)) + [{"role": "user", "content": msg}]
    uid = u["id"]

    def gen():
        parts = []
        yield ndjson({"type": "meta", "chat_id": chat_id})
        try:
            for kind, val in ai.stream(msgs, max_out):
                if kind == "delta":
                    parts.append(val)
                    yield ndjson({"type": "delta", "text": val})
            yield ndjson({"type": "done"})
        except ai.AIError as e:
            yield ndjson({"type": "error", "message": str(e)})
        finally:
            if parts:
                reply = "".join(parts)
                services.add_message(uid, chat_id, "assistant", reply)
                services.add_tokens(uid, "chat", est_in + services.est_tokens(reply))  # your message + the reply

    return StreamingResponse(gen(), media_type="application/x-ndjson", headers={"X-Accel-Buffering": "no"})


# --------------------------------------------------------------- API keys
@app.get("/api/keys")
def keys_list(request: Request):
    u = require_user(request)
    return {"keys": services.list_keys(u)}


@app.post("/api/keys")
def keys_create(request: Request, body: NameIn):
    u = require_user(request)
    throttle("keycreate:" + u["id"], 10, 3600)
    meta, plain = services.create_key(u, body.name)
    return JSONResponse({"key": meta, "secret": plain}, status_code=201)


@app.delete("/api/keys/{key_id}")
def keys_revoke(request: Request, key_id: str):
    u = require_user(request)
    services.revoke_key(u, key_id)
    return {"ok": True}


# ------------------------------------------------------------ /v1 REST API
class V1Message(BaseModel):
    role: str
    content: Any = None


class V1ChatIn(BaseModel):
    model: Optional[str] = None
    messages: List[V1Message]
    stream: bool = False
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None


def v1_auth(request: Request):
    throttle("v1ip:" + client_ip(request), 300, 60)
    h = request.headers.get("authorization", "")
    if not h.lower().startswith("bearer "):
        raise ServiceError("Missing API key. Send the header 'Authorization: Bearer <your key>'.", 401, "missing_api_key")
    res = services.authenticate_key(h[7:].strip())
    if not res:
        raise ServiceError("Invalid or revoked API key.", 401, "invalid_api_key")
    user, key = res
    ok, remaining, retry = limiter.hit("key:" + key["id"], config.API_RATE_LIMIT_PER_MIN, 60)
    if not ok:
        raise ServiceError(f"Rate limit exceeded ({config.API_RATE_LIMIT_PER_MIN} requests/minute).", 429, "rate_limit_exceeded", retry_after=retry)
    return user, key, remaining


def rl_headers(remaining: int) -> dict:
    return {"X-RateLimit-Limit": str(config.API_RATE_LIMIT_PER_MIN), "X-RateLimit-Remaining": str(remaining)}


@app.get("/v1/models")
def v1_models(request: Request):
    _, _, remaining = v1_auth(request)
    data = {"object": "list", "data": [{"id": config.AI_PUBLIC_MODEL, "object": "model", "created": 1767225600, "owned_by": "neural-ai"}]}
    return JSONResponse(data, headers=rl_headers(remaining))


def normalize_messages(raw: List[V1Message]):
    if not raw:
        raise ServiceError("'messages' must be a non-empty array.", 400, "invalid_messages")
    if len(raw) > config.API_MAX_MESSAGES:
        raise ServiceError(f"Too many messages (max {config.API_MAX_MESSAGES}).", 400, "too_many_messages")
    out, total = [], 0
    for m in raw:
        if m.role not in ("system", "user", "assistant"):
            raise ServiceError("Each message role must be 'system', 'user' or 'assistant'.", 400, "invalid_role")
        c = m.content
        if isinstance(c, list):
            c = "".join(p.get("text", "") for p in c if isinstance(p, dict) and p.get("type") == "text")
        if not isinstance(c, str) or not c.strip():
            raise ServiceError("Each message needs non-empty text 'content'.", 400, "invalid_content")
        total += len(c)
        out.append({"role": m.role, "content": c})
    if total > config.API_MAX_INPUT_CHARS:
        raise ServiceError(f"Input too long (max {config.API_MAX_INPUT_CHARS} characters).", 400, "input_too_long")
    if out[-1]["role"] != "user":
        raise ServiceError("The last message must have role 'user'.", 400, "invalid_messages")
    return out, total


@app.post("/v1/chat/completions")
def v1_chat(request: Request, body: V1ChatIn):
    user, key, remaining = v1_auth(request)
    if ai.resolve_model(body.model) is None:
        raise ServiceError(f"Unknown model '{body.model}'. Use GET /v1/models.", 404, "model_not_found")
    msgs, chars = normalize_messages(body.messages)
    if body.temperature is not None and not (0 <= body.temperature <= 2):
        raise ServiceError("'temperature' must be between 0 and 2.", 400, "invalid_temperature")
    max_tokens = body.max_tokens if body.max_tokens is not None else config.API_MAX_OUTPUT_TOKENS
    if not (1 <= max_tokens <= config.API_MAX_OUTPUT_TOKENS):
        raise ServiceError(f"'max_tokens' must be between 1 and {config.API_MAX_OUTPUT_TOKENS}.", 400, "invalid_max_tokens")
    scope = "key:" + key["id"]
    key_limit = services.plan_limits(user)["tokens_per_key_per_day"]
    est_in = sum(services.est_tokens(x["content"]) for x in msgs)
    left = services.tokens_left(scope, "api", key_limit, est_in, "This API key")
    max_tokens = max(1, min(max_tokens, left - est_in))
    services.check_and_count(user["id"], "api", chars, config.API_DAILY_REQUESTS)
    cid, created, model = "chatcmpl-" + security.new_id(), int(time.time()), config.AI_PUBLIC_MODEL
    headers = rl_headers(remaining)
    headers.update({"X-Tokens-Limit": str(key_limit), "X-Tokens-Remaining": str(max(0, left))})

    if not body.stream:
        try:
            text, finish, usage = ai.complete(msgs, max_tokens, body.temperature)
        except ai.AIError as e:
            status, code = (503, "model_unavailable") if e.unavailable else (502, "upstream_error")
            return JSONResponse(v1_body(str(e), code, "api_error"), status_code=status, headers=headers)
        used = (usage or {}).get("total_tokens") or (est_in + services.est_tokens(text))
        services.add_tokens(scope, "api", used)
        headers["X-Tokens-Remaining"] = str(max(0, left - used))
        return JSONResponse({
            "id": cid, "object": "chat.completion", "created": created, "model": model,
            "choices": [{"index": 0, "message": {"role": "assistant", "content": text}, "finish_reason": finish}],
            "usage": usage,
        }, headers=headers)

    def chunk(delta, finish=None):
        return "data: " + json.dumps({"id": cid, "object": "chat.completion.chunk", "created": created, "model": model,
                                      "choices": [{"index": 0, "delta": delta, "finish_reason": finish}]}) + "\n\n"

    def gen():
        out = []
        yield chunk({"role": "assistant", "content": ""})
        try:
            for kind, val in ai.stream(msgs, max_tokens, body.temperature):
                if kind == "delta":
                    out.append(val)
                    yield chunk({"content": val})
                else:
                    yield chunk({}, val)
        except ai.AIError as e:
            code = "model_unavailable" if e.unavailable else "upstream_error"
            yield "data: " + json.dumps(v1_body(str(e), code, "api_error")) + "\n\n"
        finally:
            if out:
                services.add_tokens(scope, "api", est_in + services.est_tokens("".join(out)))
        yield "data: [DONE]\n\n"

    h = dict(headers)
    h.update({"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
    return StreamingResponse(gen(), media_type="text/event-stream", headers=h)
