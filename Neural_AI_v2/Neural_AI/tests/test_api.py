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
            self.assertEqual(c.get("/v1/models").status_code, 401)
            self.assertEqual(c.get("/v1/models", headers={"Authorization": "Bearer nrl_nope"}).status_code, 401)
            r = c.post("/api/auth/register", json={"username": "suser", "password": "password123"})
            self.assertEqual(r.status_code, 201)
            self.assertEqual(c.get("/api/keys").status_code, 200)  # usable straight away
            self.assertEqual(c.get("/api/auth/me").json()["user"]["username"], "suser")
            c.post("/api/auth/logout")
            self.assertEqual(c.post("/api/auth/login", json={"username": "SUSER", "password": "nope"}).status_code, 401)
            self.assertEqual(c.post("/api/auth/login", json={"username": "suser", "password": "password123"}).status_code, 200)


if __name__ == "__main__":
    unittest.main()
