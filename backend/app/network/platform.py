"""Windows commands return JSON, avoiding localized CLI text parsing."""
import json
import os
import subprocess


class NetworkOperationError(RuntimeError):
    pass


def powershell_json(script: str) -> list[dict]:
    if os.name != 'nt':
        raise NetworkOperationError('This operation requires Windows 10/11 NetTCPIP cmdlets')
    try:
        result = subprocess.run(
            ['powershell.exe', '-NoLogo', '-NoProfile', '-NonInteractive', '-Command',
             "$ErrorActionPreference='Stop'; [Console]::OutputEncoding=[Text.UTF8Encoding]::new(); "
             + script + ' | ConvertTo-Json -Depth 6 -Compress'],
            capture_output=True, timeout=30, check=True, encoding='utf-8-sig')
        value = json.loads(result.stdout) if result.stdout.strip() else []
        return value if isinstance(value, list) else [value]
    except subprocess.CalledProcessError as exc:
        raise NetworkOperationError(f'Windows network query failed: {exc.stderr.strip()}') from exc
    except (OSError, subprocess.SubprocessError, ValueError) as exc:
        raise NetworkOperationError(f'Windows network query failed: {exc}') from exc


def adapter_metadata() -> list[dict]:
    return powershell_json('Get-NetAdapter -IncludeHidden | Select-Object Name,InterfaceDescription,ifIndex,HardwareInterface,Virtual')


def default_routes() -> list[dict]:
    return powershell_json("Get-NetRoute -AddressFamily IPv4 | Where-Object { $_.DestinationPrefix -eq '0.0.0.0/0' -and $_.NextHop -ne '0.0.0.0' } | Select-Object NextHop,InterfaceAlias,InterfaceIndex,RouteMetric,InterfaceMetric")
