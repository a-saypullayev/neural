"""Tests for the framework-independent core (stdlib only). Run: python -m unittest discover -s tests -v"""
import http.server
import json
import os
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "sdk"))
os.environ["APP_SECRET"] = "test-secret-for-unit-tests-only"
os.environ["SQLITE_PATH"] = os.path.join(tempfile.mkdtemp(), "t.db")
os.environ.pop("DATABASE_URL", None)

from app import config, db, security, services  # noqa: E402
from app.ratelimit import RateLimiter  # noqa: E402
from app.services import ServiceError  # noqa: E402

db.migrate()
db.migrate()  # idempotent


def mkuser(username="ann"):
    return services.register(username, "correct horse")



class EmailSignup(unittest.TestCase):
    def test_canonical_email(self):
        c = services.canonical_email
        self.assertEqual(c("a.b.c+x@gmail.com"), "abc@gmail.com")
        self.assertEqual(c("abc@googlemail.com"), "abc@gmail.com")
        self.assertEqual(c("a.b+tag@example.com"), "a.b@example.com")

    def test_clean_email_rejects(self):
        for bad in ("", "nope", "a@b", "a b@x.com", "x@mailinator.com", "x@sub.mailinator.com", "a..b@x.com"):
            with self.assertRaises(ServiceError):
                services.clean_email(bad)
        self.assertEqual(services.clean_email("  Ann@Example.COM "), "ann@example.com")

    def test_one_account_per_email(self):
        with mock.patch.object(config, "REQUIRE_EMAIL", True):
            with self.assertRaises(ServiceError) as cm:
                services.register("noemail1", "password123")
            self.assertEqual(cm.exception.code, "email_required")
            u = services.register("emailuser1", "password123", email="Kim.Lee+1@gmail.com")
            self.assertEqual(u["email_verified"], 0)
            self.assertEqual(u["email_to"], "kim.lee+1@gmail.com")
            code = services.issue_code(u)
            services.verify_code(u, code)
            self.assertEqual(services.get_user(u["id"])["email_verified"], 1)
            # same mailbox, other spellings -> refused
            for alias in ("kimlee@gmail.com", "k.i.m.l.e.e+spam@gmail.com", "kimlee@googlemail.com"):
                with self.assertRaises(ServiceError) as cm:
                    services.register("emailuser2", "password123", email=alias)
                self.assertEqual(cm.exception.code, "email_taken")

    def test_unverified_signup_does_not_block_owner(self):
        with mock.patch.object(config, "REQUIRE_EMAIL", True):
            squatter = services.register("squat1", "password123", email="victim@example.org")
            real = services.register("realowner", "password123", email="victim@example.org")
            self.assertIsNone(services.get_user(squatter["id"]))
            self.assertIsNotNone(services.get_user(real["id"]))


class Security(unittest.TestCase):
    def test_password(self):
        h = security.hash_password("pw12345678")
        self.assertNotIn("pw12345678", h)
        self.assertTrue(security.verify_password("pw12345678", h))
        self.assertFalse(security.verify_password("nope", h))

    def test_session(self):
        t = security.sign_session("u1")
        self.assertEqual(security.read_session(t), "u1")
        self.assertIsNone(security.read_session(t[:-2] + "xx"))
        self.assertIsNone(security.read_session("garbage"))
        self.assertIsNone(security.read_session(security.sign_session("u1", days=-1)))

    def test_code_format(self):
        for _ in range(200):
            c = security.generate_code()
            self.assertRegex(c, r"^\d{6}$")


class Accounts(unittest.TestCase):
    def test_register_login(self):
        u = mkuser("reguser")
        self.assertEqual(u["email_verified"], 1)  # no email verification any more
        self.assertNotEqual(u["password_hash"], "correct horse")
        self.assertEqual(services.authenticate("REGUSER", "correct horse")["id"], u["id"])
        with self.assertRaises(ServiceError) as c:
            services.authenticate("reguser", "wrong")
        self.assertEqual(c.exception.status, 401)
        with self.assertRaises(ServiceError) as c:
            mkuser("reguser")
        self.assertEqual(c.exception.status, 409)
        for bad in [("ab", "longenough"), ("bad name", "longenough"), ("", "longenough"), ("okname", "short")]:
            with self.assertRaises(ServiceError):
                services.register(*bad)


class ApiKeys(unittest.TestCase):
    def test_lifecycle(self):
        u = mkuser("user_k1")
        self.assertIsNone(services.authenticate_key("nrl_whatever"))
        meta, plain = services.create_key(u, "My key")
        self.assertTrue(plain.startswith("nrl_"))
        stored = db.query("SELECT * FROM nx_api_keys WHERE id = ?", (meta["id"],))[0]
        self.assertNotIn(plain, json.dumps(stored))           # plaintext never stored
        self.assertEqual(stored["key_hash"], security.hash_api_key(plain))
        self.assertEqual(stored["user_id"], u["id"])          # associated with owner
        self.assertNotIn("secret", json.dumps(services.list_keys(u)))  # never listed again
        user, key = services.authenticate_key(plain)
        self.assertEqual(user["id"], u["id"])
        # another user cannot revoke it
        other = mkuser("user_k2")
        with self.assertRaises(ServiceError):
            services.revoke_key(other, meta["id"])
        services.revoke_key(u, meta["id"])
        self.assertIsNone(services.authenticate_key(plain))
        self.assertTrue(services.list_keys(u)[0]["revoked"])

    def test_free_plan_key_limits(self):
        u = mkuser("user_k3")
        free = config.PLANS["free"]
        self.assertEqual((free["max_active_keys"], free["keys_per_day"], free["tokens_per_key_per_day"]), (3, 3, 10000))
        metas = [services.create_key(u, f"k{i}")[0] for i in range(3)]
        self.assertEqual(metas[0]["token_limit"], 10000)
        with self.assertRaises(ServiceError) as c:
            services.create_key(u, "fourth")
        self.assertEqual(c.exception.code, "key_limit")
        # revoking frees an active slot, but the 3-per-day creation cap still applies
        services.revoke_key(u, metas[0]["id"])
        with self.assertRaises(ServiceError) as c:
            services.create_key(u, "fourth again")
        self.assertEqual(c.exception.code, "key_daily_limit")
        # a new UTC day lets the user create keys again
        db.execute("UPDATE nx_api_keys SET created_at = created_at - 90000 WHERE user_id = ?", (u["id"],))
        services.create_key(u, "tomorrow")


class Tokens(unittest.TestCase):
    def test_estimate(self):
        self.assertEqual(services.est_tokens(""), 0)
        self.assertEqual(services.est_tokens("abcd"), 1)
        self.assertEqual(services.est_tokens("a" * 41), 11)

    def test_chat_budget(self):
        u = mkuser("user_t1")
        self.assertEqual(services.plan_limits(u)["chat_tokens_per_day"], 10000)
        self.assertEqual(services.usage_summary(u)["token_limit"], 10000)
        self.assertEqual(services.token_usage(u["id"], "chat"), 0)
        services.add_tokens(u["id"], "chat", 9000)
        services.add_tokens(u["id"], "chat", 500)
        self.assertEqual(services.usage_summary(u)["tokens"], 9500)
        self.assertEqual(services.tokens_left(u["id"], "chat", 10000, 100, "Your account"), 500)
        with self.assertRaises(ServiceError) as c:      # input bigger than what is left
            services.tokens_left(u["id"], "chat", 10000, 500, "Your account")
        self.assertEqual(c.exception.status, 429)
        services.add_tokens(u["id"], "chat", 500)
        with self.assertRaises(ServiceError) as c:      # nothing left
            services.tokens_left(u["id"], "chat", 10000, 1, "Your account")
        self.assertEqual(c.exception.code, "daily_limit")

    def test_each_key_has_its_own_budget(self):
        u = mkuser("user_t2")
        (m1, _), (m2, _) = services.create_key(u, "a"), services.create_key(u, "b")
        services.add_tokens("key:" + m1["id"], "api", 10000)
        with self.assertRaises(ServiceError):
            services.tokens_left("key:" + m1["id"], "api", 10000, 1, "This API key")
        self.assertEqual(services.tokens_left("key:" + m2["id"], "api", 10000, 1, "This API key"), 10000)
        listed = {k["id"]: k for k in services.list_keys(u)}
        self.assertEqual(listed[m1["id"]]["tokens_used"], 10000)
        self.assertEqual(listed[m2["id"]]["tokens_used"], 0)


class UsageAndChats(unittest.TestCase):
    def test_daily_quota(self):
        u = mkuser("user_u1")
        for _ in range(3):
            services.check_and_count(u["id"], "chat", 10, 3, 1000)
        with self.assertRaises(ServiceError) as c:
            services.check_and_count(u["id"], "chat", 10, 3, 1000)
        self.assertEqual(c.exception.status, 429)

    def test_chat_isolation(self):
        a, b = mkuser("user_c1"), mkuser("user_c2")
        cid = services.create_chat(a["id"], "hello")
        services.add_message(a["id"], cid, "user", "hi")
        self.assertIsNone(services.get_chat(b["id"], cid))
        self.assertEqual(services.chat_messages(b["id"], cid), [])
        for i in range(6):  # same-second inserts must keep insertion order
            services.add_message(a["id"], cid, "user" if i % 2 == 0 else "assistant", f"m{i}")
        self.assertEqual([m["content"] for m in services.chat_messages(a["id"], cid)], ["hi"] + [f"m{i}" for i in range(6)])
        self.assertFalse(services.delete_chat(b["id"], cid))
        self.assertTrue(services.delete_chat(a["id"], cid))
        m = services.add_memory(a["id"], "likes tea")
        self.assertFalse(services.delete_memory(b["id"], m["id"]))
        self.assertIn("likes tea", services.system_prompt_for(a["id"]))
        self.assertNotIn("likes tea", services.system_prompt_for(b["id"]))


class RateLimit(unittest.TestCase):
    def test_window(self):
        rl = RateLimiter()
        self.assertTrue(rl.hit("k", 2, 60)[0]); self.assertTrue(rl.hit("k", 2, 60)[0])
        ok, rem, retry = rl.hit("k", 2, 60)
        self.assertFalse(ok); self.assertGreater(retry, 0)
        self.assertTrue(rl.hit("other", 2, 60)[0])


class _Stub(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def _json(self, code, obj, headers=None):
        b = json.dumps(obj).encode()
        self.send_response(code); self.send_header("Content-Type", "application/json")
        for k, v in (headers or {}).items(): self.send_header(k, v)
        self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)
    def do_GET(self):
        if self.headers.get("Authorization") != "Bearer nrl_good":
            return self._json(401, {"error": {"message": "Invalid or revoked API key.", "code": "invalid_api_key"}})
        self._json(200, {"object": "list", "data": [{"id": "neural-1"}]})
    def do_POST(self):
        if self.headers.get("Authorization") != "Bearer nrl_good":
            return self._json(401, {"error": {"message": "bad key", "code": "invalid_api_key"}})
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        if body["messages"][0]["content"] == "limit":
            return self._json(429, {"error": {"message": "slow down", "code": "rate_limit_exceeded"}}, {"Retry-After": "7"})
        if body.get("stream"):
            self.send_response(200); self.send_header("Content-Type", "text/event-stream"); self.end_headers()
            for t in ["Hel", "lo"]:
                self.wfile.write(("data: " + json.dumps({"choices": [{"delta": {"content": t}}]}) + "\n\n").encode())
            self.wfile.write(b"data: [DONE]\n\n"); return
        self._json(200, {"id": "x", "choices": [{"index": 0, "message": {"role": "assistant", "content": "Hello"}, "finish_reason": "stop"}], "usage": None})


class SDK(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Stub)
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        cls.url = f"http://127.0.0.1:{cls.srv.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()

    def test_all(self):
        import neuralai
        from neuralai import Neural
        c = Neural(api_key="nrl_good", base_url=self.url)
        self.assertEqual(c.models.list().data[0].id, "neural-1")
        r = c.chat.completions.create(messages=[{"role": "user", "content": "hi"}])
        self.assertEqual(r.choices[0].message.content, "Hello")
        with c.chat.completions.create(messages=[{"role": "user", "content": "hi"}], stream=True) as s:
            self.assertEqual("".join(s.iter_text()), "Hello")
        with self.assertRaises(neuralai.AuthenticationError):
            Neural(api_key="nrl_bad", base_url=self.url).models.list()
        with self.assertRaises(neuralai.RateLimitError) as e:
            c.chat.completions.create(messages=[{"role": "user", "content": "limit"}])
        self.assertEqual(e.exception.retry_after, 7)
        with self.assertRaises(neuralai.APIConnectionError):
            Neural(api_key="k", base_url="http://127.0.0.1:1", max_retries=0).models.list()
        with self.assertRaises(neuralai.NeuralError):
            os.environ.pop("NEURAL_API_KEY", None); Neural()


if __name__ == "__main__":
    unittest.main()
