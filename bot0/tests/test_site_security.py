from __future__ import annotations

import hashlib
import hmac
import sys
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SITE_DIR = ROOT / "site"
if str(SITE_DIR) not in sys.path:
    sys.path.insert(0, str(SITE_DIR))

import api  # noqa: E402


class SiteSecurityTests(unittest.TestCase):
    def test_verify_telegram_auth_accepts_valid_hash(self):
        token = "123456:test-token"
        data = {
            "id": "42",
            "first_name": "Test",
            "auth_date": str(int(time.time())),
        }
        data_check_string = "\n".join(f"{key}={value}" for key, value in sorted(data.items()))
        secret_key = hashlib.sha256(token.encode()).digest()
        data["hash"] = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()

        self.assertTrue(api.verify_telegram_auth(dict(data), token))

    def test_verify_telegram_auth_rejects_invalid_hash(self):
        self.assertFalse(api.verify_telegram_auth({"id": "42", "hash": "bad"}, "123456:test-token"))

    def test_health_endpoint_shape(self):
        client = api.app.test_client()
        response = client.get("/api/health")
        self.assertIn(response.status_code, {200, 503})
        payload = response.get_json()
        self.assertIn("status", payload)
        self.assertIn("db", payload)
        self.assertIn("timestamp", payload)

    def test_private_api_requires_session(self):
        client = api.app.test_client()
        response = client.get("/api/user_releases?user_id=42")
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.get_json()["error"], "Требуется авторизация")

    def test_private_api_rejects_different_user_id(self):
        client = api.app.test_client()
        with client.session_transaction() as session:
            session["user_id"] = 42
        response = client.get("/api/user_releases?user_id=43")
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.get_json()["error"], "Нет доступа к данным другого пользователя")

    def test_admin_query_parameter_does_not_authenticate(self):
        client = api.app.test_client()
        response = client.get("/api/admin/overview?admin_user_id=1398275867")
        self.assertEqual(response.status_code, 401)

    def test_logout_clears_session(self):
        client = api.app.test_client()
        with client.session_transaction() as session:
            session["user_id"] = 42
        response = client.post("/api/auth/logout")
        self.assertEqual(response.status_code, 200)
        with client.session_transaction() as session:
            self.assertNotIn("user_id", session)

    def test_public_release_query_excludes_author_and_performer_fields(self):
        source = Path(api.__file__).read_text(encoding="utf-8")
        public_feed = source[source.index("def get_recent_releases():"):source.index("def create_distribution():")]
        self.assertNotIn("'artist_name':", public_feed)
        self.assertNotIn("'performer_name':", public_feed)
        self.assertNotIn("'music_author':", public_feed)
