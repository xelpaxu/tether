import asyncio
import pytest
from pydantic import ValidationError
from app.models.network import ConnectivityResult
from app.network import connectivity


def test_ping_structured_backend(monkeypatch):
    async def probe(target, count, timeout_ms):
        assert (target, count, timeout_ms) == ('10.0.0.2', 3, 750)
        return {'replies': [{'ms': 0, 'status': 'Success'}, {'ms': None, 'status': 'TimedOut'},
                            {'ms': 8, 'status': 'Success'}]}
    monkeypatch.setattr(connectivity, '_run_probe', probe)
    result = asyncio.run(connectivity.ping('10.0.0.2', 3, 750))
    assert result.packets_sent == 3 and result.packets_received == 2
    assert result.packet_loss_percent == pytest.approx(100/3)
    assert (result.minimum_ms, result.average_ms, result.maximum_ms) == (0, 4, 8)
    assert result.model_dump()['packets_received'] == 2
    assert result.timestamp.utcoffset().total_seconds() == 0


@pytest.mark.parametrize('target,count,timeout', [('bad;echo hello', 1, 1000), ('localhost', 1, 1000),
                                                ('127.0.0.1', 0, 1000), ('127.0.0.1', 101, 1000),
                                                ('127.0.0.1', 1, 99), ('fe80::1%12', 1, 1000)])
def test_invalid_probe(target, count, timeout):
    with pytest.raises(ValueError):
        asyncio.run(connectivity.ping(target, count, timeout))


def test_silence_is_inconclusive():
    result = ConnectivityResult(target='127.0.0.1', response_times_ms=[None, None])
    assert result.reachability == 'no_icmp_response'
    assert result.packet_loss_percent == 100
    assert result.average_ms is None


@pytest.mark.parametrize('data', [{}, {'replies': []}, {'replies': [{'status': 'Success', 'ms': None}]},
                                 {'replies': [{'status': 'Success', 'ms': -1}]}, {'replies': [None]}])
def test_malformed_backend_is_not_packet_loss(monkeypatch, data):
    async def probe(*args):
        return data
    monkeypatch.setattr(connectivity, '_run_probe', probe)
    with pytest.raises(connectivity.NetworkOperationError):
        asyncio.run(connectivity.ping('127.0.0.1', count=1))


@pytest.mark.parametrize('values', [[], [-1], [float('nan')], [float('inf')]])
def test_invalid_measurements(values):
    with pytest.raises(ValidationError):
        ConnectivityResult(target='127.0.0.1', response_times_ms=values)


def test_subprocess_cancel_kills_and_reaps(monkeypatch):
    class FakeProcess:
        returncode = None
        killed = False
        reaped = False

        async def communicate(self):
            if self.killed:
                self.reaped = True
                return b'', b''
            await asyncio.Event().wait()

        def kill(self):
            self.killed = True
            self.returncode = -1

    process = FakeProcess()

    async def create(*args, **kwargs):
        return process

    monkeypatch.setattr(connectivity.asyncio, 'create_subprocess_exec', create)

    async def scenario():
        task = asyncio.create_task(connectivity._run_probe('127.0.0.1', 1, 1000))
        await asyncio.sleep(0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert process.killed and process.reaped

    asyncio.run(scenario())
