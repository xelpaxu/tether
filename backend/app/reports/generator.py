"""Flow-based PDF layout with escaped, wrapping cells and repeatable table headers."""
from pathlib import Path
from xml.sax.saxutils import escape
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from app.models.network import (ConnectivityResult, Device, Event, Gateway, Interface,
                                NetworkInfo, Performance, Recommendation, ReportSnapshot, utcnow)


def generate_report(*, interface: Interface | None = None, network: NetworkInfo | None = None,
                    gateways: list[Gateway] = (), devices: list[Device] = (),
                    results: list[ConnectivityResult] = (), performance: Performance | None = None,
                    events: list[Event] = (), recommendations: list[Recommendation] = (),
                    warnings: list[str] = (), output_dir: str | Path = 'reports') -> Path:
    """Only caller-supplied observations; missing sections explicitly say not collected.

    The output directory is caller-controlled. Unique filenames avoid overwrites.
    """
    from uuid import uuid4
    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    now = utcnow()
    path = directory / f'tether-{now:%Y%m%dT%H%M%S}-{uuid4().hex[:8]}.pdf'
    styles = getSampleStyleSheet()
    styles['BodyText'].fontSize = 9
    styles['BodyText'].leading = 12
    styles['Heading2'].keepWithNext = True
    story = []

    def paragraph(value, style='BodyText'):
        return Paragraph(escape(str(value)), styles[style])

    def section(title: str, lines) -> None:
        story.append(paragraph(title, 'Heading2'))
        values = list(lines)
        for value in values or ['Not collected / unavailable.']:
            story.append(paragraph(value))
            story.append(Spacer(1, 5))

    def table(headers, rows):
        if not rows:
            story.append(paragraph('Not collected / unavailable.'))
            return
        data = [[paragraph(value) for value in row] for row in [headers, *rows]]
        item = Table(data, colWidths=[(A4[0]-80)/len(headers)]*len(headers), repeatRows=1, hAlign='LEFT')
        item.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#e5eef5')),
                                  ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                                  ('GRID', (0, 0), (-1, -1), 0.3, colors.lightgrey),
                                  ('LEFTPADDING', (0, 0), (-1, -1), 6),
                                  ('RIGHTPADDING', (0, 0), (-1, -1), 6)]))
        story.append(item)

    story.append(paragraph('TETHER Network Monitoring Report', 'Title'))
    story.append(paragraph(f'Generated {now.isoformat()} (UTC)'))
    def stamp(value):
        return value.strftime('%Y-%m-%d %H:%M:%S UTC')

    section('Selected interface', [
        f'{interface.name} - {interface.description or "Description unavailable"}',
        f'Status: {"up" if interface.is_up else "down"}; type: {interface.kind}; MAC: {interface.mac or "Unknown"}',
        f'IPv6: {", ".join(a.address for a in interface.ipv6) or "Not available"}'
    ] if interface else [])
    story.append(paragraph('Local IPv4 configuration', 'Heading2'))
    table(['Property', 'Value'], [[key.replace('_', ' ').capitalize(), value] for key, value in network.model_dump().items()] if network else [])
    section('Default gateways', [f'{g.ip} via {g.interface}; effective metric {g.metric}; ICMP {g.reachability}' for g in gateways])
    section('Discovered devices', []) if not devices else story.append(paragraph('Discovered devices', 'Heading2'))
    if devices:
        table(['IP / status', 'MAC / manufacturer', 'Hostname / timestamps'],
              [[f'{d.ip} / {d.reachability}', f'{d.mac or "Unknown"} / {d.vendor or "Unknown"}',
                f'{d.hostname or "Unknown"}; first {stamp(d.first_discovered)}; last {stamp(d.last_seen)}'] for d in devices])
    story.append(paragraph('Connectivity measurements', 'Heading2'))
    table(['Target / UTC', 'Sent / received / loss', 'RTT ms: min / mean / max'],
          [[f'{r.target} / {stamp(r.timestamp)}',
            f'{r.packets_sent} / {r.packets_received} / {r.packet_loss_percent:.1f}%',
            f'{r.minimum_ms} / {r.average_ms} / {r.maximum_ms}'] for r in results])
    story.append(paragraph('Calculated performance indicators', 'Heading2'))
    table(['Indicator', 'Value'], [[key.replace('_', ' ').capitalize(), value] for key, value in performance.model_dump().items()] if performance else [])
    section('Network events', [f'{e.timestamp.isoformat()} {e.target}: {e.kind} - {e.observation}' for e in events]
            or ['No network events supplied.'])
    section('Diagnostics and recommendations',
            [f'[{r.severity}] {r.code}. Observation: {r.observation}. Reason: {r.reason}. Action: {r.recommendation}' for r in recommendations]
            or ['No diagnostic recommendations supplied. This does not certify network security.'])
    section('Collection warnings', warnings or ['No collection warnings supplied.'])
    section('Interpretation', ['Availability is the percentage of checks with at least one ICMP echo, not time-weighted uptime. '
                              'Threshold classifications are configurable indicators, not an official networking health standard. '
                              'Missing ICMP or ARP replies do not prove a device is offline. '
                              'No intrusive vulnerability or port scan was performed. An open port alone does not establish a vulnerability. '
                              'These limited observations cannot certify network security.'])

    def footer(canvas, doc):
        canvas.saveState()
        canvas.setFont('Helvetica', 8)
        canvas.drawString(40, 22, f'TETHER | UTC | Page {doc.page}')
        canvas.restoreState()

    SimpleDocTemplate(str(path), pagesize=A4, rightMargin=40, leftMargin=40,
                      topMargin=40, bottomMargin=40).build(story, onFirstPage=footer, onLaterPages=footer)
    return path


def generate_report_from_snapshot(snapshot: ReportSnapshot, *, output_dir: str | Path = 'reports') -> Path:
    return generate_report(**{name: getattr(snapshot, name) for name in ReportSnapshot.model_fields},
                           output_dir=output_dir)
