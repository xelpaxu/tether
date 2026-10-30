"""Numeric ICMP measurements via Windows .NET Ping, independent of OS language.

No shell, hostname interpolation or parsing of localized ping.exe summaries.
"""
import asyncio
import base64
from ipaddress import ip_address
import json
import os
from pydantic import ValidationError
from app.models.network import ConnectivityResult, utcnow
from app.network.platform import NetworkOperationError


async def _run_probe(target: str, count: int, timeout_ms: int, resolve_hostname: bool = False) -> dict:
    if os.name != 'nt':
        raise NetworkOperationError('The ICMP backend currently supports Windows only')
    script = f"""
    $ErrorActionPreference='Stop'
    $p=[System.Net.NetworkInformation.Ping]::new()
    try {{
      $r=@(for($i=0;$i -lt {count};$i++) {{
        $a=$p.Send('{target}',{timeout_ms})
        if($a.Status -eq [System.Net.NetworkInformation.IPStatus]::Success) {{
          @{{ms=[double]$a.RoundtripTime;status='Success'}}
        }} else {{ @{{ms=$null;status=$a.Status.ToString()}} }}
      }})
      $hostname=$null
      if (${str(resolve_hostname).lower()}) {{
        try {{
          $dns=[System.Net.Dns]::GetHostEntryAsync('{target}')
          if ($dns.Wait(1000)) {{ $hostname=$dns.Result.HostName }}
        }} catch {{ $hostname=$null }}
      }}
      ConvertTo-Json -InputObject @{{replies=$r;hostname=$hostname}} -Depth 4 -Compress
    }} finally {{ $p.Dispose() }}
    """
    encoded = base64.b64encode(script.encode('utf-16le')).decode('ascii')
    process = await asyncio.create_subprocess_exec(
        'powershell.exe', '-NoLogo', '-NoProfile', '-NonInteractive', '-EncodedCommand', encoded,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(), count * timeout_ms / 1000 + 15)
        if process.returncode:
            raise NetworkOperationError(stderr.decode(errors='replace').strip())
        return json.loads(stdout.decode('utf-8-sig'))
    except (asyncio.TimeoutError, asyncio.CancelledError):
        if process.returncode is None:
            process.kill()
        await process.communicate()
        raise
    except (ValueError, OSError) as exc:
        raise NetworkOperationError(f'Invalid ICMP command result: {exc}') from exc


async def ping(target: str, count: int = 4, timeout_ms: int = 1000, *,
               resolve_hostname: bool = False) -> ConnectivityResult:
    """A missing echo means no ICMP response, never proof a device is offline.

    Numeric IPv4/IPv6 only. RTT has Windows millisecond resolution (zero is valid).
    """
    address = str(ip_address(target))
    if '%' in address:
        raise ValueError('Scoped IPv6 addresses are not yet supported by this backend')
    if not 1 <= count <= 100 or not 100 <= timeout_ms <= 60000:
        raise ValueError('count must be 1..100 and timeout_ms 100..60000')
    timestamp = utcnow()
    try:
        data = (await _run_probe(address, count, timeout_ms, True) if resolve_hostname
                else await _run_probe(address, count, timeout_ms))
        replies = data['replies']
        if not isinstance(replies, list) or len(replies) != count:
            raise NetworkOperationError('ICMP backend returned an incomplete measurement')
        for reply in replies:
            if not isinstance(reply['status'], str) or (reply['status'] == 'Success' and reply['ms'] is None):
                raise NetworkOperationError('ICMP backend returned an invalid reply')
        return ConnectivityResult(target=address, hostname=data.get('hostname'), timestamp=timestamp,
                                  response_times_ms=[r['ms'] if r['status'] == 'Success' else None for r in replies],
                                  errors=[r['status'] for r in replies if r['status'] != 'Success'])
    except (KeyError, TypeError, OSError, ValidationError) as exc:
        raise NetworkOperationError(f'ICMP backend failed: {exc}') from exc
