"""Short local HTTP smoke check; shuts down its own Uvicorn process on exit."""
import json
from pathlib import Path
import socket
import subprocess
import sys
import time
from urllib.request import urlopen
from urllib.error import URLError


def main() -> None:
    # Ephemeral loopback port avoids taking over a developer's existing server.
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    process = subprocess.Popen([sys.executable, '-m', 'uvicorn', 'app.main:app', '--host',
                                '127.0.0.1', '--port', str(port)], cwd=Path(__file__).resolve().parents[1],
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    try:
        for _ in range(100):
            if process.poll() is not None:
                raise RuntimeError(process.stdout.read().decode(errors='replace'))
            try:
                with urlopen(f'http://127.0.0.1:{port}/health', timeout=1) as response:
                    health = json.load(response)
                break
            except URLError:
                time.sleep(0.1)
        else:
            raise TimeoutError('Uvicorn did not start within the smoke-check deadline')
        assert health == {'status': 'ok'}
        with urlopen(f'http://127.0.0.1:{port}/', timeout=1) as response:
            root = json.load(response)
        assert root['application'] == 'TETHER'
        print(json.dumps({'root': root, 'health': health, 'host': '127.0.0.1'}))
    finally:
        process.terminate()
        try:
            output, _ = process.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            output, _ = process.communicate()
        print(output.decode(errors='replace'))


if __name__ == '__main__':
    main()
