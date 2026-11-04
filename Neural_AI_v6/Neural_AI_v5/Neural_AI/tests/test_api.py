"""HTTP-level smoke test using FastAPI's TestClient. Skipped automatically if fastapi/httpx are not installed.
Run:  pip install -r requirements.txt httpx  &&  python -m unittest tests.test_api -v
"""
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("APP_SECRET", "test-secret-for-unit-tests-only-0123456789")
os.environ["SQLITE_PATH"] = os.path.join(tempfile.mkdtemp(), "api.db")
os.environ.pop("DATABASE_URL", None)

try:
    from fastapi.testclient import TestClient
    from app.main import app
    HAVE = True
except Exception:  # pragma: no cover
    HAVE = False


@unittest.skipUnless(HAVE, "fastapi/httpx not installed")
class Smoke(unittest.TestCase):
    def test_pages_and_auth(self):
        with TestClient(app) as c:
            self.assertEqual(c.get("/api/health").json(), {"status": "ok"})
            for path in ("/", "/keys", "/doc", "/policy"):
                self.assertEqual(c.get(path).status_code, 200, path)
            m = c.get("/manifest.webmanifest")
            self.assertEqual(m.status_code, 200)
            self.assertEqual(m.json()["display"], "standalone")
            for icon in m.json()["icons"]:
                self.assertEqual(c.get(icon["src"]).status_code, 200, icon["src"])
            sw = c.get("/sw.js")
            self.assertEqual(sw.status_code, 200)
            self.assertEqual(sw.headers["service-worker-allowed"], "/")
            self.assertEqual(c.get("/static/offline.html").status_code, 200)
            self.assertIn("manifest.webmanifest", c.get("/").text)
            self.assertEqual(c.get("/download").status_code, 200)
            exe = c.get("/download/NeuralAI.exe", headers={"host": "neural-6mzi.onrender.com", "x-forwarded-proto": "https"})
            self.assertEqual(exe.status_code, 200)
            self.assertEqual(exe.content[:2], b"MZ")
            self.assertIn(b"https://neural-6mzi.onrender.com\x00", exe.content)
            self.assertNotIn(b"@@NEURAL_URL@@", exe.content)
            self.assertIn("attachment", exe.headers["content-disposition"])
            tpl = open(os.path.join(ROOT, "app", "downloads", "NeuralAI.template.exe"), "rb").read()
            self.assertEqual(len(exe.content), len(tpl))  # patched in place, file size unchanged
            self.assertEqual(c.get("/v1/models").status_code, 401)
            self.assertEqual(c.get("/v1/models", headers={"Authorization": "Bearer nrl_nope"}).status_code, 401)
            r = c.post("/api/auth/register", json={"username": "suser", "password": "password123"})
            self.assertEqual(r.status_code, 201)
            self.assertEqual(c.get("/api/keys").status_code, 200)  # usable straight away
            self.assertEqual(c.get("/api/auth/me").json()["user"]["username"], "suser")
            c.post("/api/auth/logout")
            self.assertEqual(c.post("/api/auth/login", json={"username": "SUSER", "password": "nope"}).status_code, 401)
            self.assertEqual(c.post("/api/auth/login", json={"username": "suser", "password": "password123"}).status_code, 200)


@unittest.skipUnless(HAVE, "fastapi/httpx not installed")
class Metering(unittest.TestCase):
    def test_chat_and_api_token_limits(self):
        from unittest import mock
        from app import ai, db
        fake = lambda msgs, max_tokens, temperature=None: ("x" * 400, "stop", None)      # 100 tokens out
        fake_stream = lambda msgs, max_tokens, temperature=None: iter([("delta", "y" * 400), ("finish", "stop")])
        with TestClient(app) as c, mock.patch.object(ai, "complete", fake), mock.patch.object(ai, "stream", fake_stream):
            c.post("/api/auth/register", json={"username": "meter1", "password": "password123"})
            me = c.get("/api/auth/me").json()
            self.assertEqual(me["usage"]["token_limit"], 10000)
            # web chat: one message of 40 chars (10 tokens) + 400-char reply (100 tokens) = 110
            r = c.post("/api/chat", json={"message": "z" * 40})
            self.assertEqual(r.status_code, 200)
            self.assertEqual(c.get("/api/auth/me").json()["usage"]["tokens"], 110)
            # use up the rest of the day, then chat is refused
            from app import services
            uid = me["user"]["id"]
            services.add_tokens(uid, "chat", 10000)
            r = c.post("/api/chat", json={"message": "hello"})
            self.assertEqual(r.status_code, 429)
            self.assertIn("tokens", r.json()["error"]["message"])
            # API keys: three allowed, a fourth is refused, each key meters on its own
            keys = []
            for i in range(3):
                kr = c.post("/api/keys", json={"name": f"k{i}"})
                self.assertEqual(kr.status_code, 201)
                keys.append(kr.json()["secret"])
            self.assertEqual(c.post("/api/keys", json={"name": "k4"}).status_code, 400)
            h = lambda k: {"Authorization": "Bearer " + k}
            body = {"model": "neural-1", "messages": [{"role": "user", "content": "hi there"}]}
            r = c.post("/v1/chat/completions", json=body, headers=h(keys[0]))
            self.assertEqual(r.status_code, 200)
            self.assertEqual(r.headers["x-tokens-limit"], "10000")
            self.assertEqual(r.headers["x-tokens-remaining"], str(10000 - (2 + 100)))
            # exhaust key 0 only
            kid0 = c.get("/api/keys").json()["keys"][-1]["id"]
            services.add_tokens("key:" + kid0, "api", 10000)
            self.assertEqual(c.post("/v1/chat/completions", json=body, headers=h(keys[0])).status_code, 429)
            self.assertEqual(c.post("/v1/chat/completions", json=body, headers=h(keys[1])).status_code, 200)
            # streaming is metered too
            s = c.post("/v1/chat/completions", json=dict(body, stream=True), headers=h(keys[2]))
            self.assertEqual(s.status_code, 200)
            kid2 = [k for k in c.get("/api/keys").json()["keys"] if k["tokens_used"] > 0 and k["id"] != kid0]
            self.assertTrue(any(k["tokens_used"] >= 100 for k in kid2))

    def test_nav_has_download_button(self):
        with TestClient(app) as c:
            js = c.get("/static/js/common.js").text
            self.assertIn('href="/download"', js)


if __name__ == "__main__":
    unittest.main()
