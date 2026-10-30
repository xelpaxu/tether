"""Recommendations cite observations, never certify security or device absence."""
from app.analysis.performance import Thresholds, analyze
from app.models.network import ConnectivityResult, Device, Event, Gateway, Interface, Recommendation


def diagnose(*, interface: Interface | None = None, gateways: list[Gateway] = (),
             results: list[ConnectivityResult] = (), events: list[Event] = (),
             devices: list[Device] = (), known_macs: set[str] | None = None,
             thresholds: Thresholds | None = None) -> list[Recommendation]:
    recommendations = []

    def add(code: str, severity: str, observation: str, reason: str, advice: str) -> None:
        recommendations.append(Recommendation(code=code, severity=severity, observation=observation,
                                              reason=reason, recommendation=advice))

    if interface is None:
        add('missing_interface', 'warning', 'No interface selected', 'Network scope is unknown',
            'Select an active adapter; inspect Windows network settings if none is available.')
    elif not interface.is_up or not interface.ipv4 or any(not a.netmask for a in interface.ipv4):
        add('interface_configuration', 'warning',
            f'{interface.name}: up={interface.is_up}, IPv4={interface.ipv4}',
            'Inactive adapters or missing addresses prevent local IPv4 discovery',
            'Check cable/Wi-Fi association, DHCP and the selected VPN or virtual adapter.')
    if not gateways:
        add('missing_gateway', 'info', 'No default IPv4 gateway supplied',
            'A local-only network may legitimately have no default route',
            'Inspect default routes if access beyond this subnet is expected.')
    for gateway in gateways:
        if gateway.reachability == 'no_icmp_response':
            add('gateway_no_echo', 'warning', f'{gateway.ip} did not return ICMP echoes',
                'Routing failure or ICMP filtering can cause this result',
                'Check local association and route configuration; verify gateway access by another permitted method.')
    grouped: dict[str, list[ConnectivityResult]] = {}
    for result in results:
        grouped.setdefault(str(result.target), []).append(result)
    limits = thresholds or Thresholds()
    for target, measurements in grouped.items():
        summary = analyze(measurements, limits)
        if summary.packet_loss_percent is not None and summary.packet_loss_percent >= limits.loss_percent:
            add('packet_loss', 'warning', f'{target}: {summary.packet_loss_percent:.1f}% packet loss across {summary.checks} checks',
                'Missing echoes may indicate congestion, wireless interference or ICMP rate limiting',
                'Repeat measurements and compare wired/Wi-Fi results before attributing a fault.')
        if summary.average_ms is not None and summary.average_ms >= limits.high_latency_ms:
            add('high_latency', 'warning', f'{target}: measured mean RTT {summary.average_ms:.1f} ms',
                f'Mean RTT exceeds the configured {limits.high_latency_ms} ms threshold',
                'Check link utilization, Wi-Fi signal and competing traffic; compare against a baseline.')
    for event in events:
        if event.kind in {'sustained_latency', 'sustained_loss', 'sustained_failure', 'icmp_interruption', 'probe_error'}:
            add(event.kind, 'warning', f'{event.target} at {event.timestamp.isoformat()}: {event.observation}',
                'Monitoring observed repeated degradation, a connectivity change or a measurement error',
                'Correlate with adapter, router and system logs. Missing ICMP alone does not establish a disconnection.')
    if known_macs is not None:
        normalize = lambda mac: mac.replace('-', ':').lower()
        known = {normalize(mac) for mac in known_macs}
        for device in devices:
            if device.mac and normalize(device.mac) not in known:
                add('new_device', 'info', f'ARP observed {device.ip}, MAC {device.mac}, absent from supplied baseline',
                    'A new MAC can be a legitimate device or address randomization; identity is unverified',
                    'Compare with your device inventory and router client list before deciding whether access is unauthorized.')
    return recommendations
