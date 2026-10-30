"""No Internet, subnet scan, Npcap or admin privilege required."""
import asyncio
import os
import pytest
from app.network.connectivity import ping
from app.network.interfaces import get_interfaces
from app.network.monitoring import Monitor
from app.network.gateway import get_gateways

pytestmark = [pytest.mark.integration, pytest.mark.skipif(os.name != 'nt', reason='Windows backend')]


def test_actual_interfaces_and_routes():
    adapters = get_interfaces()
    assert adapters
    assert any(a.ipv4 or a.ipv6 for a in adapters)
    # A disconnected machine legitimately returns an empty default route list.
    routes = get_gateways()
    assert all(g.ip and g.interface and g.metric >= 0 for g in routes)


def test_actual_loopback_ping_and_monitor():
    async def scenario():
        result = await ping('127.0.0.1', count=2)
        assert result.packets_received == 2
        monitor = Monitor(['127.0.0.1'], count=1, interval=0.1)
        monitor.start()
        try:
            for _ in range(100):
                if monitor.history['127.0.0.1']:
                    break
                await asyncio.sleep(0.1)
        finally:
            await monitor.stop()
        assert monitor.history['127.0.0.1']
        assert not monitor.running
    asyncio.run(scenario())
