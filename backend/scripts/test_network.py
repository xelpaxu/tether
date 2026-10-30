"""Live Windows smoke check. Discovery only runs when explicitly requested."""
__test__ = False
import argparse
import asyncio
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.analysis.performance import analyze
from app.core.config import Settings
from app.core.logging import configure_logging
from app.network.addressing import calculate_network
from app.network.connectivity import ping
from app.network.diagnostics import diagnose
from app.network.discovery import discover_devices_async
from app.network.gateway import get_gateways, check_gateway
from app.network.interfaces import get_interfaces, select_active_interface
from app.network.monitoring import Monitor
from app.network.platform import NetworkOperationError
from app.models.network import ReportSnapshot


async def main(args) -> None:
    configure_logging()
    settings = Settings.from_env()
    interfaces = await asyncio.to_thread(get_interfaces)
    print('Detected interfaces (actual observations):')
    for interface in interfaces:
        print(interface.model_dump_json(indent=2))
    warnings = []
    try:
        gateways = await asyncio.to_thread(get_gateways)
    except NetworkOperationError as exc:
        gateways = []
        warnings.append(str(exc))
    selected = (next((i for i in interfaces if i.name == args.interface), None) if args.interface
                else select_active_interface(interfaces, gateways))
    if args.interface and selected is None:
        raise ValueError('Named interface not found')
    network = None
    if selected:
        print('Selected:', selected.name)
        gateways = [g for g in gateways if g.interface == selected.name]
        addresses = [a for a in selected.ipv4 if not args.local_ip or a.address == args.local_ip]
        if len(addresses) == 1 and addresses[0].netmask:
            network = calculate_network(addresses[0].address, addresses[0].netmask)
            print(network.model_dump_json(indent=2))
        else:
            warnings.append('Select a configured IPv4 using --local-ip; subnet is ambiguous or incomplete.')
    else:
        warnings.append('No unambiguous active interface; select --interface explicitly.')
    results, checked_gateways = [], []
    for gateway in gateways:
        try:
            checked = await check_gateway(gateway)
            checked_gateways.append(checked)
            print('Gateway:', checked.model_dump_json())
        except Exception as exc:
            warnings.append(f'Gateway probe failed: {exc}')
            checked_gateways.append(gateway)
    target = args.target or (gateways[0].ip if gateways else '127.0.0.1')
    result = await ping(target, count=settings.ping_count, timeout_ms=settings.timeout_ms,
                        resolve_hostname=args.resolve_hostname)
    results.append(result)
    print('Connectivity:', result.model_dump_json(indent=2))
    print(json.dumps({'sent': result.packets_sent, 'received': result.packets_received,
                      'loss_percent': result.packet_loss_percent, 'average_ms': result.average_ms,
                      'reachability': result.reachability}))
    devices = []
    if args.discover:
        if not selected or not network:
            raise ValueError('Discovery requires an unambiguous active interface and IPv4 subnet')
        print('Explicit local ARP scan requested; requires Npcap and capture permission.')
        try:
            discovery = await discover_devices_async(selected, network.cidr, max_hosts=settings.max_scan_hosts)
            devices = discovery.devices
            warnings.extend(discovery.warnings)
            print(discovery.model_dump_json(indent=2))
        except (NetworkOperationError, ValueError) as exc:
            warnings.append(f'Discovery not completed: {exc}')
    events = []
    if args.monitor_seconds:
        monitor = Monitor([target], interval=settings.interval_seconds, count=settings.ping_count,
                          timeout_ms=settings.timeout_ms, concurrency=settings.concurrency)
        monitor.start()
        try:
            await asyncio.sleep(args.monitor_seconds)
        finally:
            await monitor.stop()
        results.extend(monitor.history[target])
        events = list(monitor.events)
        print('Monitoring stopped; samples:', len(monitor.history[target]))
    performance = analyze(results)
    print('Calculated performance:', performance.model_dump_json(indent=2))
    recommendations = diagnose(interface=selected, gateways=checked_gateways, results=results, events=events, devices=devices)
    for recommendation in recommendations:
        print(recommendation.model_dump_json())
    for warning in warnings:
        print('WARNING:', warning)
    snapshot = ReportSnapshot(interface=selected, network=network, gateways=checked_gateways,
                                        devices=devices, results=results, performance=performance, events=events,
                                        recommendations=recommendations, warnings=warnings)
    if args.snapshot:
        output = Path(args.snapshot)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(snapshot.model_dump_json(indent=2), encoding='utf-8')
        print('Actual collection snapshot:', output)
    if args.report:
        from app.reports.generator import generate_report_from_snapshot
        print('Report:', generate_report_from_snapshot(snapshot, output_dir=settings.report_dir))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--interface', help='Exact adapter name, such as Wi-Fi')
    parser.add_argument('--local-ip', help='Choose among multiple IPv4 addresses on selected adapter')
    parser.add_argument('--target', help='Numeric IPv4/IPv6 to test; default selected gateway or loopback')
    parser.add_argument('--discover', action='store_true', help='Authorize ARP on selected connected local subnet')
    parser.add_argument('--monitor-seconds', type=float, default=0)
    parser.add_argument('--report', action='store_true')
    parser.add_argument('--resolve-hostname', action='store_true', help='Optional reverse DNS for selected ping target; 1-second DNS wait')
    parser.add_argument('--snapshot', help='Save actual observations as JSON for report replay')
    arguments = parser.parse_args()
    if arguments.monitor_seconds < 0:
        parser.error('--monitor-seconds must be non-negative')
    try:
        asyncio.run(main(arguments))
    except KeyboardInterrupt:
        print('Stopped by user.')
    except Exception as exc:
        print(f'Collection failed: {exc}', file=sys.stderr)
        sys.exit(1)
