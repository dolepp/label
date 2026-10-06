from __future__ import annotations

import sys
import unittest
from html.parser import HTMLParser
from pathlib import Path

SITE_DIR = Path(__file__).resolve().parents[2] / 'site'
if str(SITE_DIR) not in sys.path:
    sys.path.insert(0, str(SITE_DIR))
import api


class MetaParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.api_bases = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'meta' and attrs.get('name') == 'twas-api-base':
            self.api_bases.append(attrs.get('content'))


class SitePagesTests(unittest.TestCase):
    def test_pages_origin_has_credentialed_cors(self):
        client = api.app.test_client()
        for origin in ('https://twaslabel.ru', 'https://www.twaslabel.ru',
                       'https://st124325.github.io', 'http://localhost:5000'):
            with self.subTest(origin=origin):
                response = client.get('/api/auth/bot-link', headers={'Origin': origin})
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.headers.get('Access-Control-Allow-Origin'), origin)
                self.assertEqual(response.headers.get('Access-Control-Allow-Credentials'), 'true')

    def test_private_api_preflight_needs_no_session(self):
        response = api.app.test_client().options('/api/admin/users/42/roles', headers={
            'Origin': 'https://twaslabel.ru',
            'Access-Control-Request-Method': 'PUT',
            'Access-Control-Request-Headers': 'Content-Type',
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get('Access-Control-Allow-Origin'), 'https://twaslabel.ru')
        self.assertEqual(response.headers.get('Access-Control-Allow-Credentials'), 'true')
        self.assertIn('PUT', response.headers.get('Access-Control-Allow-Methods', ''))
        self.assertIn('Content-Type', response.headers.get('Access-Control-Allow-Headers', ''))
        self.assertEqual(api.app.test_client().put('/api/admin/users/42/roles').status_code, 401)

    def test_html_has_empty_api_base_meta(self):
        for name in ('cabinet.html', 'admin.html'):
            with self.subTest(page=name):
                parser = MetaParser()
                parser.feed((SITE_DIR / name).read_text(encoding='utf-8'))
                self.assertEqual(parser.api_bases, [''])

    def test_media_policy_allows_other_origins(self):
        for path in ('/api/files/telegram/example', '/api/releases/1/media/audio'):
            with self.subTest(path=path), api.app.test_request_context(path):
                response = api.add_cache_policy(api.app.response_class())
                self.assertIn(response.headers.get('Cross-Origin-Resource-Policy'), (None, 'cross-origin'))

    def test_session_cookie_is_host_only_and_lax(self):
        self.assertEqual(api.app.config['SESSION_COOKIE_SAMESITE'], 'Lax')
        self.assertIsNone(api.app.config['SESSION_COOKIE_DOMAIN'])


if __name__ == '__main__':
    unittest.main()
