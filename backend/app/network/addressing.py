from ipaddress import IPv4Interface
from app.models.network import NetworkInfo


def calculate_network(ip: str, netmask: str | int) -> NetworkInfo:
    interface = IPv4Interface(f'{ip}/{netmask}')
    network = interface.network
    if interface.ip.is_multicast or interface.ip.is_unspecified:
        raise ValueError('A unicast configured IPv4 address is required')
    offset = 1 if network.prefixlen < 31 else 0
    first = network.network_address + offset
    last = network.broadcast_address - offset
    return NetworkInfo(local_ip=str(interface.ip), netmask=str(network.netmask),
                       prefix=network.prefixlen, cidr=str(network),
                       network_address=str(network.network_address),
                       broadcast_address=str(network.broadcast_address),
                       first_usable=str(first), last_usable=str(last),
                       usable_hosts=network.num_addresses - 2 * offset,
                       network_range=f'{first} - {last}')
