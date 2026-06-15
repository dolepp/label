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
