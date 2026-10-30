import pytest
from app.network.addressing import calculate_network


@pytest.mark.parametrize('ip,mask,cidr,first,last,count', [
    ('192.168.7.130', '255.255.255.128', '192.168.7.128/25', '192.168.7.129', '192.168.7.254', 126),
    ('10.1.9.3', 20, '10.1.0.0/20', '10.1.0.1', '10.1.15.254', 4094),
    ('10.0.0.0', 31, '10.0.0.0/31', '10.0.0.0', '10.0.0.1', 2),
    ('10.0.0.5', 32, '10.0.0.5/32', '10.0.0.5', '10.0.0.5', 1),
])
def test_subnets(ip, mask, cidr, first, last, count):
    result = calculate_network(ip, mask)
    assert (result.cidr, result.first_usable, result.last_usable, result.usable_hosts) == (cidr, first, last, count)
    assert result.network_range == f'{first} - {last}'
    assert result.local_ip == ip


@pytest.mark.parametrize('ip,mask', [('bad', 24), ('256.1.1.1', 24), ('::1', 64),
                                      ('10.1.1.1', 33), ('10.1.1.1', '255.0.255.0'),
                                      ('0.0.0.0', 24), ('224.1.1.1', 24)])
def test_invalid(ip, mask):
    with pytest.raises(ValueError):
        calculate_network(ip, mask)


def test_broadcast_and_mask():
    result = calculate_network('172.16.5.100', 23)
    assert result.network_address == '172.16.4.0'
    assert result.broadcast_address == '172.16.5.255'
    assert result.netmask == '255.255.254.0'
