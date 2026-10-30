import asyncio
import pytest
from app.models.network import Address, Device, Interface
from app.network import discovery


@pytest.fixture
def adapter():
    return Interface(name='Ethernet', is_up=True, kind='physical',
                     ipv4=[Address(address='192.168.4.2', netmask='255.255.255.0')])


@pytest.mark.parametrize('subnet', ['8.8.8.0/24', '192.168.0.0/16', '192.168.4.2/24', '::/64'])
def test_scope_restrictions(adapter, subnet):
    with pytest.raises(ValueError):
        discovery.validate_scope(adapter, subnet)


def test_scan_limit(adapter):
    with pytest.raises(ValueError):
        discovery.validate_scope(adapter, '192.168.4.0/24', max_hosts=10)


def test_arp_deadline_reports_incomplete_scan(adapter, monkeypatch):
    import sys
    from types import SimpleNamespace
    from unittest.mock import Mock
    adapter.mac = '00:11:22:33:44:55'
    adapter.index = 3
    scapy = SimpleNamespace(ARP=Mock(), Ether=Mock(), srp=Mock(),
                            conf=SimpleNamespace(ifaces={3: SimpleNamespace(mac=adapter.mac, index=3)}))
    monkeypatch.setitem(sys.modules, 'scapy.all', scapy)
    times = iter([0, 121])
    monkeypatch.setattr(discovery.time, 'monotonic', lambda: next(times))
    with pytest.raises(discovery.NetworkOperationError, match='incomplete'):
        discovery.discover_devices(adapter, '192.168.4.0/24')
    scapy.srp.assert_not_called()


def test_cannot_map_adapter_never_scans_another_interface(adapter, monkeypatch):
    import sys
    from types import SimpleNamespace
    from unittest.mock import Mock
    scapy = SimpleNamespace(ARP=Mock(), Ether=Mock(), srp=Mock(), conf=SimpleNamespace(ifaces={}))
    monkeypatch.setitem(sys.modules, 'scapy.all', scapy)
    with pytest.raises(discovery.NetworkOperationError, match='map selected adapter'):
        discovery.discover_devices(adapter, '192.168.4.0/24')
    scapy.srp.assert_not_called()


def test_real_fields_only_and_first_seen(adapter, monkeypatch):
    old = Device(ip='192.168.4.5', mac='00:11:22:33:44:55')
    monkeypatch.setattr(discovery, '_arp_scan', lambda *args: [
        ('192.168.4.5', old.mac), ('192.168.4.6', '02:11:22:33:44:55')])
    result = discovery.discover_devices(adapter, '192.168.4.0/24',
                                        oui={'001122': 'Trusted vendor', '021122': 'Misleading'}, previous={old.ip: old})
    assert result.devices[0].first_discovered == old.first_discovered
    assert result.devices[0].vendor == 'Trusted vendor'
    assert result.devices[1].vendor is None
    assert all(d.hostname is None for d in result.devices)


def test_async_scan_cancellation_keeps_exclusive_lock(adapter, monkeypatch):
    import threading
    entered, release = threading.Event(), threading.Event()

    def scan(*args):
        entered.set()
        release.wait(2)
        return []

    monkeypatch.setattr(discovery, '_arp_scan', scan)

    async def scenario():
        task = asyncio.create_task(discovery.discover_devices_async(adapter, '192.168.4.0/24'))
        await asyncio.to_thread(entered.wait, 1)
        task.cancel()
        await asyncio.sleep(0)
        with pytest.raises(discovery.NetworkOperationError):
            await discovery.discover_devices_async(adapter, '192.168.4.0/24')
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert not discovery._scan_lock.locked()

    asyncio.run(scenario())
