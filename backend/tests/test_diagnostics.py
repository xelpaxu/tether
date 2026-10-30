from app.models.network import Device, Gateway, ConnectivityResult
from app.network.diagnostics import diagnose


def test_recommendations_have_evidence():
    recs = diagnose(gateways=[Gateway(ip='10.0.0.254', interface='Ethernet', interface_index=1,
                                     metric=5, reachability='no_icmp_response')],
                    results=[ConnectivityResult(target='10.0.0.2', response_times_ms=[200, None])],
                    devices=[Device(ip='10.0.0.3', mac='aa:bb:cc:dd:ee:ff')], known_macs=set())
    assert {'gateway_no_echo', 'packet_loss', 'high_latency', 'new_device'} <= {r.code for r in recs}
    assert all(r.observation and r.reason and r.recommendation for r in recs)


def test_unknown_baseline_does_not_mean_new_device():
    assert 'new_device' not in {r.code for r in diagnose(devices=[Device(ip='10.0.0.1', mac='aa:bb:cc:dd:ee:ff')])}
