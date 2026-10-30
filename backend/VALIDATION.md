# Implementation validation - 2026-10-31 (Asia/Manila)

Validated on the user's Windows machine with **CPython 3.10.11** in `backend/.venv`. Python 3.10 was explicitly approved in place of the initially requested 3.11. No Python installation was changed. Existing files in `docs/` and the empty frontend were preserved.

## Automated results

| Check | Actual result |
| --- | --- |
| `python -m pip install -r requirements.txt` | Successful inside the project virtual environment after allowing package downloads outside the sandbox |
| `python -m pip check` | No broken requirements found |
| `python -m pytest -v` | **64 passed, 2 skipped**, 1.27 seconds on final run |
| `TETHER_RUN_INTEGRATION=1`, `python -m pytest -v -m integration` | **2 passed, 64 deselected**, 7.20 seconds on final run |
| `python -m compileall -q app scripts` | Successful |
| `python scripts/verify_server.py` | Real loopback Uvicorn instance started; `/health` and `/` returned HTTP 200 and expected JSON; child server stopped |
| PDF snapshot round trip and generation test | Passed; JSON preserves calculated packet statistics; PDF output created with distinct filenames and valid file markers |

The normal suite deliberately skips actual machine integration checks. Unit coverage includes non-/24 networks, /31 and /32 arithmetic, invalid input, packet-weighted calculations, unknown measurements, trends/thresholds, adapter parsing and route metrics, malformed ICMP command output, subprocess cancellation/reaping, bounded monitoring workers/history, sustained conditions and recovery, scan limits/scope/mapping/deadline, scan cancellation, diagnostics evidence, configuration and ASGI endpoints. Unit fixtures are synthetic test inputs only; live demonstrations and exported reports use actual observations.

## Actual networking checks

The sandbox denied NetAdapter/NetTCPIP CIM queries with `Access denied`. The application logged that limitation and returned actual psutil IP/MAC observations with unknown metadata; it did not guess a gateway or select among ambiguous adapters. Repeating the authorized live checks outside the sandbox succeeded.

The live script detected **seven interfaces**, including physical Wi-Fi, two VMware virtual adapters, Wi-Fi Direct virtual adapters, a tunnel and loopback. Selection used the default route's effective metric, choosing Wi-Fi rather than the first active VMware adapter. The detected gateway ended in **.254**, demonstrating there is no `.1` assumption.

Npcap was already installed and running; TETHER did not install or reconfigure it. Actual bounded local ARP scans completed. The first returned seven responding addresses; a subsequent scan returned five, and the final saved scan returned seven. These are per-scan observations, not a proof that missing devices disconnected. Unknown vendor and hostname values were left null. No external OUI service or public subnet scan was used.

The saved observation snapshot from the final report collection contains:

- Selected active interface: Wi-Fi; detected IPv4 subnet has 254 usable hosts.
- Default gateway: responding to ICMP.
- Seven ARP responders, including the local machine and gateway.
- Two connectivity checks (one standalone plus one monitoring sample), **eight packets attempted and eight echoes received**.
- Measured RTT: **minimum 4 ms, mean 4.875 ms, maximum 8 ms**; calculated packet loss **0%**.
- Check-based availability **100%** over those two checks only; trend correctly reports insufficient data.
- No threshold or connectivity-change events in that short collection. Degradation/recovery events were separately tested with controlled unit fixtures.

Loopback tests separately produced real zero-millisecond RTTs at Windows' measurement resolution. The optional bounded reverse-DNS path was exercised against loopback; it returned a system-resolver hostname. Such names can reflect local hosts-file entries and are not authenticated device identities.

## Report review

`reports/latest-observations.json` contains the actual final collection and can be loaded as `ReportSnapshot`. The reviewed final PDF is:

`reports/tether-20261030T164739-2ccf4dfa.pdf`

Its UTC filename/generation time corresponds to 2026-10-31 in Asia/Manila. It was regenerated from that saved collection after layout corrections, without inventing or remeasuring data. It includes all required sections, actual discovered devices and measurements, explicit unknown fields and interpretation notes. Both pages were rendered with the machine's existing PyMuPDF installation and visually inspected: tables wrap correctly, headings stay with content, page numbers are present and no text is clipped or overlapping. Poppler was unavailable; PyMuPDF was used for this development-only review and is not a runtime dependency.

## Limits of verification

Python 3.11, other Windows machines, Ethernet hardware, VPN-specific routing, Wi-Fi client isolation scenarios and long-duration monitoring were not physically tested. IPv6 discovery/gateway support and scoped IPv6 probes remain unsupported. Discovery still requires a compatible adapter, Npcap and applicable capture permissions. Some Windows policies can require elevated access for metadata queries. No test establishes that the network is secure or that a silent device is offline. See README for architecture, thresholds and remaining work.
