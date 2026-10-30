import socket
from types import SimpleNamespace
from app.models.network import Address, Gateway, Interface
from app.network import interfaces, gateway
from app.network.platform import NetworkOperationError


def test_parse_interfaces(monkeypatch):
    addr = lambda family, address, mask=None: SimpleNamespace(family=family, address=address, netmask=mask)
    monkeypatch.setattr(interfaces, 'adapter_metadata', lambda: [
        {'Name': 'Wi-Fi', 'ifIndex': 4, 'HardwareInterface': True, 'InterfaceDescription': 'Wireless NIC'},
        {'Name': 'Tunnel', 'ifIndex': 5, 'Virtual': True}])
    monkeypatch.setattr(interfaces.psutil, 'net_if_addrs', lambda: {
        'Loopback': [addr(socket.AF_INET, '127.0.0.1', '255.0.0.0')],
        'Wi-Fi': [addr(socket.AF_INET, '10.1.0.5', '255.255.0.0'),
                  addr(socket.AF_INET6, 'fe80::2%4'), addr(interfaces.psutil.AF_LINK, 'aa-bb-cc-dd-ee-ff')],
        'Tunnel': [addr(socket.AF_INET, '10.2.0.1', '255.255.255.0')]})
    monkeypatch.setattr(interfaces.psutil, 'net_if_stats', lambda: {
        'Loopback': SimpleNamespace(isup=True), 'Wi-Fi': SimpleNamespace(isup=True),
        'Tunnel': SimpleNamespace(isup=False)})
    parsed = interfaces.get_interfaces()
    assert [i.kind for i in parsed] == ['loopback', 'physical', 'virtual']
    assert parsed[1].ipv6[0].address == 'fe80::2%4'
    assert parsed[1].description == 'Wireless NIC'
    assert parsed[1].mac == 'aa-bb-cc-dd-ee-ff'
    assert not parsed[2].is_up


def test_selection_uses_routes_not_first_adapter():
    adapters = [Interface(name=name, is_up=True, ipv4=[Address(address=ip)])
                for name, ip in [('Virtual', '10.0.0.2'), ('Wi-Fi', '192.168.1.3')]]
    routes = [Gateway(ip='192.168.1.254', interface='Wi-Fi', interface_index=2, metric=20),
              Gateway(ip='10.0.0.9', interface='Virtual', interface_index=1, metric=50)]
    assert interfaces.select_active_interface(adapters, routes).name == 'Wi-Fi'
    assert interfaces.select_active_interface(adapters, []) is None


def test_gateway_metric_and_interface(monkeypatch):
    monkeypatch.setattr(gateway, 'default_routes', lambda: [
        {'NextHop': '10.0.0.254', 'InterfaceAlias': 'Ethernet', 'InterfaceIndex': 3, 'RouteMetric': 5, 'InterfaceMetric': 30},
        {'NextHop': '10.1.0.254', 'InterfaceAlias': 'Wi-Fi', 'InterfaceIndex': 4, 'RouteMetric': 10, 'InterfaceMetric': 5}])
    assert gateway.get_gateways()[0].metric == 15
    assert gateway.get_gateways('Ethernet')[0].ip == '10.0.0.254'
    assert gateway.get_gateways('Missing') == []
