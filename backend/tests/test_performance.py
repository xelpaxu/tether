import pytest
from app.analysis.performance import analyze, Thresholds
from app.models.network import ConnectivityResult


def result(values):
    return ConnectivityResult(target='10.0.0.2', response_times_ms=values)


def test_packet_weighted_calculations():
    stats = analyze([result([10, 20, None]), result([40]), result([None, None])])
    assert stats.checks == 3 and stats.successful_checks == 2 and stats.failed_checks == 1
    assert stats.packets_sent == 6 and stats.packets_received == 3
    assert stats.packet_loss_percent == 50
    assert stats.availability_percent == pytest.approx(200/3)
    assert stats.average_ms == pytest.approx(70/3)
    assert (stats.minimum_ms, stats.maximum_ms) == (10, 40)
    assert stats.classification == 'degraded'


def test_no_data_is_unknown():
    stats = analyze([])
    assert stats.packet_loss_percent is None
    assert stats.availability_percent is None
    assert stats.average_ms is None
    assert stats.classification == 'no_data'


def test_no_replies():
    stats = analyze([result([None])])
    assert stats.packet_loss_percent == 100 and stats.availability_percent == 0
    assert stats.classification == 'no_icmp_response'


@pytest.mark.parametrize('values,trend', [([10, 10, 50, 50], 'rising'),
                                         ([50, 50, 10, 10], 'falling'), ([10, 12, 11, 12], 'stable')])
def test_trend(values, trend):
    assert analyze([result([v]) for v in values]).trend == trend


def test_thresholds_configurable():
    assert analyze([result([50])]).classification == 'normal'
    assert analyze([result([50])], Thresholds(high_latency_ms=40)).classification == 'degraded'
