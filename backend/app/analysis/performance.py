from pydantic import BaseModel, Field
from app.models.network import ConnectivityResult, Performance


class Thresholds(BaseModel):
    high_latency_ms: float = Field(100, gt=0)
    loss_percent: float = Field(5, gt=0, le=100)
    consecutive_checks: int = Field(3, ge=1)
    trend_delta_ms: float = Field(10, ge=0)


def analyze(results: list[ConnectivityResult], thresholds: Thresholds | None = None) -> Performance:
    """Packet-weighted loss/latency; availability is percentage of checks with an echo.

    This sample-based indicator is not time-weighted uptime or an official health score.
    Trend compares mean per-check RTT in the first and second halves (at least 4 checks).
    """
    t = thresholds or Thresholds()
    ordered = sorted(results, key=lambda r: r.timestamp)
    latencies = [value for r in ordered for value in r.latencies]
    means = [r.average_ms for r in ordered if r.average_ms is not None]
    sent = sum(r.packets_sent for r in ordered)
    received = sum(r.packets_received for r in ordered)
    success = sum(r.packets_received > 0 for r in ordered)
    average = sum(latencies) / len(latencies) if latencies else None
    loss = 100 * (1 - received / sent) if sent else None
    trend = 'insufficient_data'
    if len(means) >= 4:
        half = len(means) // 2
        delta = sum(means[half:]) / len(means[half:]) - sum(means[:half]) / half
        trend = 'rising' if delta > t.trend_delta_ms else 'falling' if delta < -t.trend_delta_ms else 'stable'
    classification = ('no_data' if not ordered else 'no_icmp_response' if not received else
                      'degraded' if loss >= t.loss_percent or average >= t.high_latency_ms else 'normal')
    return Performance(checks=len(ordered), successful_checks=success, failed_checks=len(ordered)-success,
                       packets_sent=sent, packets_received=received, packet_loss_percent=loss,
                       availability_percent=100 * success / len(ordered) if ordered else None,
                       minimum_ms=min(latencies, default=None), average_ms=average,
                       maximum_ms=max(latencies, default=None), trend=trend, classification=classification,
                       period_start=ordered[0].timestamp if ordered else None,
                       period_end=ordered[-1].timestamp if ordered else None)
