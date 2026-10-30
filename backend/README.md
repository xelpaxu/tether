# TETHER Python networking core

Independent Windows 10/11 networking modules, callable directly from Python. FastAPI contains only `/` and `/health`; the health check reports process liveness, not Internet access. No frontend, database, cloud service, port scan or feature API is included.

Python **3.10** is supported and used for validation on this machine, as requested during implementation. Python 3.11 is also a supported code target, but was not available here to test.

## Windows PowerShell setup

```powershell
cd C:\projects\tether\backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
Copy-Item .env.example .env
```

`python` must point to Python 3.10 or newer. If using a registered Python launcher instead, replace the virtual environment command with `py -3.10 -m venv .venv`. For the originally planned 3.11 environment, use `py -3.11 -m venv .venv`. If PowerShell prevents activation, use `.\.venv\Scripts\python.exe` directly instead of changing system execution policy.

```powershell
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
# From a second terminal:
Invoke-RestMethod http://127.0.0.1:8000/health
```

The server binds only to loopback with this command. There are no feature-specific routes. Core imports do not require a running server.

## Manual networking checks

```powershell
python scripts/test_network.py
python scripts/test_network.py --target 127.0.0.1 --monitor-seconds 15
python scripts/test_network.py --interface "Wi-Fi" --discover --monitor-seconds 30 --report
python scripts/test_network.py --report --snapshot reports/observations.json --resolve-hostname
python scripts/verify_server.py
```

The first command detects real interfaces, selects the lowest-effective-metric active IPv4 default route, calculates the subnet, checks gateway reachability and pings that gateway (or loopback if no gateway exists). It prints warnings for unavailable observations. It does **not** scan until `--discover` is supplied. Use `--interface` to override selection, `--local-ip` for an adapter with multiple IPv4 addresses, and `--target` for a numeric IP you are permitted to probe. No IP address is hardcoded into the selection logic. The loopback fallback tests only the local ICMP backend. `--resolve-hostname` requests optional reverse DNS for the selected probe target, with a one-second wait inside the disposable probe process. DNS/hosts-file names are unverified observations. `verify_server.py` launches its own temporary loopback Uvicorn instance, checks both endpoints over HTTP, then shuts it down.

`--discover` explicitly authorizes an ARP scan of the selected directly connected subnet, within the configured address cap. Do this only on a network you own or are permitted to inspect. Large subnets are rejected rather than silently truncated. The core accepts a smaller subnet within the interface's connected network. Routed and arbitrary public ranges are not supported for ARP discovery.

Reports are uniquely named under `backend/reports/` when run from the backend directory. `.env` is loaded only by `Settings.from_env()` (used by the script), never at module import. Core function defaults remain explicit; applications can pass settings as arguments. Report paths are relative to the caller's working directory unless absolute.

## Automated checks

```powershell
pytest -v
# Optional live local-machine checks; no Internet access or ARP scan:
$env:TETHER_RUN_INTEGRATION = "1"
pytest -v -m integration
Remove-Item Env:TETHER_RUN_INTEGRATION
```

Unit tests mock external networking and do not need Internet, administrator access or Npcap. Integration tests query actual adapters/routes and exercise loopback ping and monitoring. They require Windows networking commands to be permitted by local policy. A disconnected computer may legitimately have no gateway. ARP is separately exercised by the manual script because it sends local-network traffic and requires Npcap.

## Architecture

```text
backend/
  app/
    core/        config.py, logging.py
    models/      network.py
    network/     addressing.py, interfaces.py, gateway.py, platform.py,
                 discovery.py, connectivity.py, monitoring.py, diagnostics.py
    analysis/    performance.py
    reports/     generator.py
    main.py
  scripts/       test_network.py
  tests/         unit tests and opt-in integration tests
  reports/       generated PDFs (ignored)
  .env.example
  .gitignore
  pytest.ini
  requirements.txt
  README.md
```

Each Python package has an `__init__.py`. The added `network/platform.py` isolates synchronous Windows NetTCPIP/NetAdapter JSON queries and their errors. `connectivity.py` owns the asynchronous Windows ICMP subprocess lifecycle. Neither imports FastAPI. Pydantic models carry UTC timestamps, explicit unknown values and serializable calculated connectivity fields.

| Module | Responsibility |
| --- | --- |
| `interfaces` | psutil addresses/status plus Windows descriptions, index and physical/virtual flags; route-based selection; preserves all adapters and all IPs |
| `addressing` | IPv4 mask, CIDR, network/broadcast and arithmetic host ranges, including /31 and /32 without enumerating hosts |
| `gateway` | All IPv4 default gateways or gateways filtered to one interface; sorts route metric plus interface metric; separate optional echo check |
| `discovery` | Scapy ARP on an explicitly selected interface; verifies connected scope, scan limits and adapter mapping; optional DNS and caller-supplied offline OUI map |
| `connectivity` | Validated numeric IPv4/IPv6 echo tests via Windows .NET `Ping`; per-packet status and measured integer-ms RTT; timeout/cancellation cleanup |
| `monitoring` | Fixed async worker pool, non-overlapping cycles, bounded history/events, threshold streaks, ICMP state changes and recovery; explicit start/stop |
| `performance` | Packet-weighted RTT/loss, per-check availability, min/max, trend and transparent classifications |
| `diagnostics` | Recommendations with observations and reasons; gateways, interfaces, thresholds, monitoring events and a caller-supplied known-MAC baseline |
| `generator` | Independently callable ReportLab PDF with wrapping tables, page numbers, UTC generation time, real observations, missing-data labels and limitations |

### Direct Python usage

Run from `backend/` with the environment activated:

```python
import asyncio
from app.network.interfaces import get_interfaces, select_active_interface
from app.network.gateway import get_gateways
from app.network.addressing import calculate_network
from app.network.connectivity import ping
from app.network.monitoring import Monitor
from app.analysis.performance import analyze, Thresholds
from app.network.diagnostics import diagnose
from app.reports.generator import generate_report

interfaces = get_interfaces()
gateways = get_gateways()
interface = select_active_interface(interfaces, gateways)
network = None
if interface and len(interface.ipv4) == 1 and interface.ipv4[0].netmask:
    address = interface.ipv4[0]
    network = calculate_network(address.address, address.netmask)

async def collect():
    result = await ping("127.0.0.1", count=4, timeout_ms=1000)
    monitor = Monitor(["127.0.0.1"], interval=1, concurrency=2,
                      thresholds=Thresholds(high_latency_ms=100, loss_percent=5,
                                            consecutive_checks=3))
    monitor.start()
    try:
        await asyncio.sleep(5)
    finally:
        await monitor.stop()
    results = [result, *monitor.history["127.0.0.1"]]
    stats = analyze(results)
    recs = diagnose(interface=interface, gateways=gateways, results=results,
                    events=list(monitor.events))
    path = generate_report(interface=interface, network=network, gateways=gateways,
                           results=results, performance=stats,
                           events=list(monitor.events), recommendations=recs)
    print(result.model_dump(), path)

asyncio.run(collect())
```

If already inside an async application, `await collect()` instead of `asyncio.run()`. Synchronous interface/gateway queries can take up to 30 seconds each; use `await asyncio.to_thread(get_interfaces)` and `await asyncio.to_thread(get_gateways)` there. Use `await discover_devices_async(interface, network.cidr)` for cancellable, off-loop ARP collection. Selection must succeed before discovery. Synchronous `discover_devices(..., resolve_hostnames=True, concurrency=4)` supports reverse DNS; async discovery intentionally disables it because system resolver timeouts cannot be reliably controlled. Discovery preserves first-seen times when passed a previous IP-to-Device map with matching MACs. Vendor lookup requires a reliable local OUI mapping supplied by the caller, with six uppercase hex-digit keys; locally administered MACs never receive a vendor attribution.

`--snapshot` saves the actual supplied observations as JSON (without a database). To regenerate a report later:

```python
from pathlib import Path
from app.models.network import ReportSnapshot
from app.reports.generator import generate_report_from_snapshot
snapshot = ReportSnapshot.model_validate_json(Path('reports/observations.json').read_text(encoding='utf-8'))
path = generate_report_from_snapshot(snapshot)
```

### Measurement definitions and lifecycle

RTTs are actual .NET Ping measurements with millisecond resolution; `0` is a valid measurement, and `None` means no successful echo. This avoids parsing translated `ping.exe` output. Operational failures raise errors rather than creating fabricated 100%-loss samples. Hostname resolution is opt-in in discovery and with `ping(..., resolve_hostname=True)`; it is unknown by default. IPv6 numeric probes are supported except scope-qualified link-local literals; discovery/subnet/gateway logic is IPv4 only.

Monitoring `interval` is the pause **after** all targets in a cycle finish; cycles never overlap. A fixed pool caps concurrent probes. `stop()` cancels the engine/workers and kills/reaps pending ICMP subprocesses. Starting twice raises an error; stopping twice is safe. History and events use bounded deques, so export them periodically for longer sessions. State continues across a stop/restart on the same monitor. Probe errors produce `probe_error` events, not fabricated samples. There are no background threads on import. Async ARP permits one in-flight scan and waits for finite ARP work on cancellation because a Scapy thread cannot be forcibly killed; synchronous callers must manage their own scan scheduling.

ARP work has a 120-second duration budget by default (`max_duration_seconds`, configurable 1..300); it checks the budget between batches and caps each receive timeout to remaining time. An in-progress batch may take its sending time plus timeout. An exceeded budget raises an explicit incomplete-scan error. Optional synchronous reverse DNS is outside that ARP budget and uses the OS resolver timeout.

Packet loss is `(sent - received) / sent * 100`, aggregated across packets. Mean RTT weights successful packets equally. Availability is the percentage of checks with at least one successful echo, **not** time-weighted uptime; samples with some loss can still count as available. Zero samples yield unknown statistics, not 100% availability. Trend compares mean per-check RTT in the first/second halves after sorting by timestamp; at least four responding checks are required. Aggregate measurements across distinct devices only when that is intentional; for device-specific analysis call `analyze(list(monitor.history[target]))` separately.

Default configurable `Thresholds`: high mean RTT 100 ms; loss 5%; sustained condition 3 consecutive checks; trend delta 10 ms. A summary is `degraded` if mean RTT or packet loss meets its threshold, `normal` otherwise; all-silent results are `no_icmp_response`, and an empty series is `no_data`. These are custom transparent indicators, not an official network health standard. Sustained events fire once per streak; recovery resets the streak. ICMP interruption/recovery refers only to observed echo behavior.

## Dependencies and Windows setup

Direct dependencies actually used: psutil, Pydantic, python-dotenv, Scapy, FastAPI, Uvicorn, ReportLab and pytest. Standard library modules handle IP arithmetic, subprocesses, socket DNS and concurrency. No additional runtime libraries or paid services are required. Dependency version ranges in `requirements.txt` exclude the next major versions; `requirements-lock.txt` records the tested environment for reproducibility.

Windows PowerShell 5.1/.NET and the Windows NetAdapter/NetTCPIP cmdlets are used for metadata/routes and language-independent ICMP. Command targets are validated numeric addresses and subprocesses never invoke a shell. Restricted CIM/WMI policies can deny metadata/route reads; the interface list still returns psutil data with a logged warning, while gateway calls raise `NetworkOperationError`. The engine never silently escalates privileges or changes network configuration. VPNs may use split routes more specific than `0.0.0.0/0`; active selection is only a likely default IPv4 adapter and users can override it. VPN identity is not guessed from marketing names: an adapter is `unknown` or `virtual` unless Windows reliably reports hardware; a virtual flag alone cannot prove it is a VPN.

For ARP on Windows install [Npcap from its official site](https://npcap.com/), then restart the Python process. Follow the [Scapy Windows installation guidance](https://scapy.readthedocs.io/en/stable/installation.html). If Npcap was installed with administrator-only access, run the discovery terminal as Administrator. Other operations normally run without administrator privileges, subject to machine policy. Npcap is a separately licensed Windows driver; review its terms before redistribution, automated installation or commercial deployment. TETHER does not install or bundle it. Raw Wi-Fi monitor mode is not needed for ordinary ARP on an associated LAN.

## Implemented behavior and limits

All listed modules contain executable implementations and unit coverage; live verification results are recorded in `VALIDATION.md`. Physical network coverage always depends on capture permissions and topology. ARP covers only the selected layer-2 segment; Wi-Fi client isolation, sleeping hosts, filtering, VPN routing and virtual switches can hide hosts. A nonresponsive ping/ARP is never proof a host is offline. No fallback silently scans a different interface or public network. ARP responses, reverse DNS and MAC vendor information are observations, not authenticated identities. Randomized/spoofed MACs can mislead inventories. Baseline comparison is caller-supplied and in memory only.

DNS resolution can fail or block at the OS layer. Vendor data is unknown without an offline OUI map. IPv6 discovery/default gateways, routed scan authorization, time-weighted uptime, persistent inventory/history, bandwidth/throughput/jitter testing, port scanning, security certification, feature HTTP routes, WebSockets and UI are outside this phase. Reports summarize supplied measurements; they cannot certify network security. An open port by itself does not mean a vulnerability. No intrusive security scanning is performed.

ReportLab's default fonts cover basic Latin text; adapter/hostname text outside that range may need a future embedded Unicode font. Reports may contain private network inventory; generated files are local and ignored by git. Monitoring retains only bounded in-memory history; SQLite is intentionally deferred.
