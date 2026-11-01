from fastapi import FastAPI

app = FastAPI(title='TETHER', version='0.1.0')


@app.get('/')
def root() -> dict[str, str]:
    return {'application': 'TETHER', 'version': '0.1.0'}


@app.get('/health')
def health() -> dict[str, str]:
    """Process liveness only; does not assert network connectivity."""
    return {'status': 'ok'}
