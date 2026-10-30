"""Explicitly scoped, bounded ARP discovery. Never infer offline from silence."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from ipaddress import IPv4Address, IPv4Network
import socket
import threading
import time
from typing import Mapping
from app.models.network import Device, DiscoveryResult, Interface
from app.network.addressing import calculate_network
from app.network.platform import NetworkOperationError


def validate_scope(interface: Interface, subnet: str, max_hosts: int = 1024) -> IPv4Network:
    network = IPv4Network(subnet, strict=True)
    if not interface.is_up or interface.kind == 'loopback':
        raise ValueError('Select an active non-loopback interface')
    if not 1 <= max_hosts <= 4096 or network.num_addresses > max_hosts:
        raise ValueError('Subnet exceeds scan address limit (maximum 4096)')
    configured = [IPv4Network(calculate_network(a.address, a.netmask).cidr)
                  for a in interface.ipv4 if a.netmask]
    if not any(network.subnet_of(local) for local in configured):
        raise ValueError('ARP scan must be within the explicitly selected directly connected subnet')
    if any((network.is_loopback, network.is_multicast, network.is_unspecified, network.is_reserved)):
        raise ValueError('Unsupported discovery subnet')
    return network


def _arp_scan(interface: Interface, network: IPv4Network, timeout: float, batch_size: int,
              max_duration_seconds: float = 120) -> list[tuple[str, str]]:
    try:
        from scapy.all import ARP, Ether, conf, srp
        # Map psutil MAC to Scapy's own interface object, never trust an alias match alone.
        candidates = [i for i in conf.ifaces.values()
                      if i.mac and interface.mac and i.mac.lower().replace('-', ':') == interface.mac.lower().replace('-', ':')]
        if interface.index is not None:
            candidates = [i for i in candidates if i.index == interface.index]
        if len(candidates) != 1:
            raise NetworkOperationError('Cannot uniquely map selected adapter to a Scapy interface')
        hosts = [str(ip) for ip in network.hosts()]
        found = []
        deadline = time.monotonic() + max_duration_seconds
        for start in range(0, len(hosts), batch_size):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise NetworkOperationError('ARP scan exceeded its duration budget; results are incomplete')
            answers, _ = srp(Ether(dst='ff:ff:ff:ff:ff:ff') / ARP(pdst=hosts[start:start + batch_size]),
                             iface=candidates[0], timeout=min(timeout, remaining), verbose=False, inter=0.01)
            for sent, received in answers:
                if received.haslayer(ARP) and received[ARP].op == 2:
                    ip, mac = received[ARP].psrc, received[ARP].hwsrc
                    if IPv4Address(ip) in network and ip == sent[ARP].pdst:
                        found.append((ip, mac))
        return found
    except NetworkOperationError:
        raise
    except Exception as exc:
        raise NetworkOperationError('ARP unavailable or failed. Check Npcap, adapter support and capture permissions. '
                                    f'Original error: {exc}') from exc


def discover_devices(interface: Interface, subnet: str, *, timeout: float = 2,
                     max_hosts: int = 1024, batch_size: int = 64,
                     max_duration_seconds: float = 120,
                     resolve_hostnames: bool = False, concurrency: int = 4,
                     oui: Mapping[str, str] | None = None,
                     previous: Mapping[str, Device] | None = None) -> DiscoveryResult:
    """Call in a worker thread from async apps. OUI keys: six uppercase hex digits.

    DNS is opt-in: the system resolver's timeout cannot be controlled portably.
    Caller supplies an authoritative offline OUI mapping; no paid/remote lookups.
    """
    network = validate_scope(interface, subnet, max_hosts)
    if (not 0.1 <= timeout <= 30 or not 1 <= batch_size <= 256 or not 1 <= concurrency <= 32
            or not 1 <= max_duration_seconds <= 300):
        raise ValueError('Invalid discovery timeout, batch size or concurrency')
    pairs = dict(_arp_scan(interface, network, timeout, batch_size, max_duration_seconds))
    devices = []
    for ip, mac in sorted(pairs.items(), key=lambda pair: IPv4Address(pair[0])):
        prefix = mac.replace(':', '').replace('-', '').upper()[:6]
        # Locally administered MACs do not reliably identify a manufacturer.
        vendor = oui.get(prefix) if oui and not int(prefix[:2], 16) & 2 else None
        old = (previous or {}).get(ip)
        device = Device(ip=ip, mac=mac, vendor=vendor)
        if old and old.mac == mac:
            device.first_discovered = old.first_discovered
        devices.append(device)
    if resolve_hostnames:
        def resolve(device: Device) -> None:
            try:
                device.hostname = socket.gethostbyaddr(device.ip)[0]
            except (OSError, UnicodeError):
                pass  # Optional name remains explicitly unknown.
        with ThreadPoolExecutor(max_workers=concurrency) as pool:
            list(pool.map(resolve, devices))
    return DiscoveryResult(subnet=str(network), devices=devices,
                           warnings=['ARP sees only responding hosts on this layer-2 segment. '
                                     'Wi-Fi isolation, VPNs and filtering can hide devices; absence is inconclusive.'])


_scan_lock = threading.Lock()


async def discover_devices_async(*args, **kwargs) -> DiscoveryResult:
    """At most one asynchronous scan; cancellation waits for bounded ARP work to finish.

    Async scans disallow reverse DNS because the OS resolver may block indefinitely.
    """
    if kwargs.get('resolve_hostnames'):
        raise ValueError('Use synchronous discovery for optional reverse DNS')
    if not _scan_lock.acquire(blocking=False):
        raise NetworkOperationError('An asynchronous discovery scan is already running')
    def scan():
        try:
            return discover_devices(*args, **kwargs)
        finally:
            _scan_lock.release()

    task = asyncio.create_task(asyncio.to_thread(scan))
    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError:
        # Shield against repeated cancellation: worker retains lock until it really exits.
        while not task.done():
            try:
                await asyncio.shield(task)
            except asyncio.CancelledError:
                continue
            except Exception:
                break
        # Retrieve an exception without substituting it for caller cancellation.
        if not task.cancelled():
            task.exception()
        raise
