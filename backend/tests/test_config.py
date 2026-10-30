import pytest
from pydantic import ValidationError
from app.core.config import Settings


def test_env_configuration(tmp_path, monkeypatch):
    path = tmp_path / 'test.env'
    path.write_text('TETHER_CONCURRENCY=3\nTETHER_PING_COUNT=2\n', encoding='utf-8')
    for name in Settings.model_fields:
        monkeypatch.delenv('TETHER_' + name.upper(), raising=False)
    monkeypatch.setenv('TETHER_PING_COUNT', '5')
    settings = Settings.from_env(str(path))
    assert settings.concurrency == 3 and settings.ping_count == 5


def test_limits():
    with pytest.raises(ValidationError):
        Settings(concurrency=0)
