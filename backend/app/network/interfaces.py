import logging
import socket
import psutil
from app.models.network import Address, Interface
from app.network.platform import adapter_metadata, NetworkOperationError

logger = logging.getLogger(__name__)


def get_interfaces() -> list[Interface]:
    try:
        metadata = {a['Name']: a for a in adapter_metadata()}
    except NetworkOperationError as exc:
        logger.warning('Adapter descriptions unavailable: %s', exc)
        metadata = {}
    stats = psutil.net_if_stats()
    result = []
    for name, addresses in psutil.net_if_addrs().items():
        meta = metadata.get(name, {})
        ipv4 = [Address(address=a.address, netmask=a.netmask) for a in addresses if a.family == socket.AF_INET]
        ipv6 = [Address(address=a.address, netmask=a.netmask) for a in addresses if a.family == socket.AF_INET6]
        mac = next((a.address for a in addresses if a.family == psutil.AF_LINK), None)
        kind, reason = 'unknown', None
        if any(a.address.startswith('127.') for a in ipv4) or any(a.address == '::1' for a in ipv6):
            kind, reason = 'loopback', 'Loopback IP address'
        elif meta.get('Virtual'):
            kind, reason = 'virtual', 'Windows Virtual flag; may include VPN adapters'
        elif meta.get('HardwareInterface'):
            kind, reason = 'physical', 'Windows HardwareInterface flag'
        result.append(Interface(name=name, description=meta.get('InterfaceDescription') or None,
                                index=meta.get('ifIndex'), ipv4=ipv4, ipv6=ipv6, mac=mac,
                                is_up=bool(stats.get(name) and stats[name].isup),
                                kind=kind, classification_reason=reason))
    return result


def select_active_interface(interfaces: list[Interface], gateways: list) -> Interface | None:
    """Lowest effective default-route metric; otherwise require unambiguous selection."""
    eligible = {i.name: i for i in interfaces if i.is_up and i.ipv4 and i.kind != 'loopback'}
    for gateway in sorted(gateways, key=lambda g: g.metric):
        if gateway.interface in eligible:
            return eligible[gateway.interface]
    return next(iter(eligible.values())) if len(eligible) == 1 else None
