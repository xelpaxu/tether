"""Exercise the real ASGI app without an HTTP client dependency or listening socket."""
import asyncio
import json
from app.main import app


def test_root_and_health_asgi():
    async def request(path):
        messages = []

        async def receive():
            return {'type': 'http.request', 'body': b'', 'more_body': False}

        async def send(message):
            messages.append(message)

        await app({'type': 'http', 'asgi': {'version': '3.0'}, 'method': 'GET', 'path': path,
                   'query_string': b'', 'headers': [], 'scheme': 'http', 'root_path': '',
                   'server': ('127.0.0.1', 8000), 'client': ('127.0.0.1', 1), 'http_version': '1.1'}, receive, send)
        assert messages[0]['status'] == 200
        return json.loads(b''.join(m.get('body', b'') for m in messages[1:]))

    assert asyncio.run(request('/'))['application'] == 'TETHER'
    assert asyncio.run(request('/health')) == {'status': 'ok'}
