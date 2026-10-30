import asyncio
import pytest
from app.analysis.performance import Thresholds
from app.models.network import ConnectivityResult
from app.network.monitoring import Monitor


def record(monitor, values):
    monitor.record(ConnectivityResult(target='10.0.0.1', response_times_ms=values))


def test_transitions_and_sustained_conditions():
    monitor = Monitor(['10.0.0.1'], thresholds=Thresholds(consecutive_checks=2))
    for values in [[10], [None], [None], [10], [200, None], [200, None]]:
        record(monitor, values)
    kinds = [event.kind for event in monitor.events]
    assert kinds.count('icmp_interruption') == 1
    assert kinds.count('recovery') == 1
    assert kinds.count('sustained_failure') == 1
    assert kinds.count('sustained_latency') == 1
    assert kinds.count('sustained_loss') == 2


def test_bounded_history():
    monitor = Monitor(['10.0.0.1'], history_limit=2)
    for _ in range(5):
        record(monitor, [1])
    assert len(monitor.history['10.0.0.1']) == 2


def test_clean_cancellation_and_worker_bound():
    async def scenario():
        active = peak = 0
        entered = asyncio.Event()

        async def probe(target, **kwargs):
            nonlocal active, peak
            active += 1
            peak = max(peak, active)
            if active == 2:
                entered.set()
            try:
                await asyncio.Event().wait()
            finally:
                active -= 1

        monitor = Monitor(['10.0.0.1', '10.0.0.2', '10.0.0.3'], concurrency=2, probe=probe)
        monitor.start()
        with pytest.raises(RuntimeError):
            monitor.start()
        await asyncio.wait_for(entered.wait(), 1)
        await monitor.stop()
        assert not monitor.running and active == 0 and peak == 2
        await monitor.stop()
    asyncio.run(scenario())


def test_probe_errors_are_not_fabricated_packet_loss():
    async def scenario():
        called = asyncio.Event()

        async def probe(target, **kwargs):
            called.set()
            raise OSError('Permission denied')

        monitor = Monitor(['10.0.0.1'], probe=probe)
        monitor.start()
        await asyncio.wait_for(called.wait(), 1)
        await asyncio.sleep(0)
        await monitor.stop()
        assert not monitor.history['10.0.0.1']
        assert monitor.events[0].kind == 'probe_error'
    asyncio.run(scenario())
