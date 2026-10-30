import subprocess
from types import SimpleNamespace
import pytest
from app.network import platform


@pytest.mark.parametrize('payload,expected', [('[]', []), ('', []),
                                           ('{"Name":"Ethernet"}', [{'Name': 'Ethernet'}]),
                                           ('[{"Name":"Wi-Fi"}]', [{'Name': 'Wi-Fi'}])])
def test_json_shapes(monkeypatch, payload, expected):
    def run(command, **kwargs):
        assert command[0] == 'powershell.exe'
        assert kwargs['timeout'] == 30
        assert 'shell' not in kwargs
        return SimpleNamespace(stdout=payload)
    monkeypatch.setattr(platform.subprocess, 'run', run)
    assert platform.powershell_json('Get-NetAdapter') == expected


def test_permission_failure_preserves_evidence(monkeypatch):
    def run(*args, **kwargs):
        raise subprocess.CalledProcessError(1, 'powershell.exe', stderr='Access denied')
    monkeypatch.setattr(platform.subprocess, 'run', run)
    with pytest.raises(platform.NetworkOperationError, match='Access denied'):
        platform.powershell_json('Get-NetAdapter')
