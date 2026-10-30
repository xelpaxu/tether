"""All timestamps are timezone-aware UTC; unknown observations remain None."""
from datetime import datetime, timezone
from typing import Literal
from pydantic import BaseModel, Field, IPvAnyAddress, computed_field, field_validator


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Address(BaseModel):
    address: str
    netmask: str | None = None


class Interface(BaseModel):
    name: str
    description: str | None = None
    index: int | None = None
    ipv4: list[Address] = Field(default_factory=list)
    ipv6: list[Address] = Field(default_factory=list)
    mac: str | None = None
    is_up: bool
    kind: Literal['loopback', 'physical', 'vpn', 'virtual', 'unknown'] = 'unknown'
    classification_reason: str | None = None


class NetworkInfo(BaseModel):
    local_ip: str
    netmask: str
    prefix: int
    cidr: str
    network_address: str
    broadcast_address: str
    first_usable: str
    last_usable: str
    usable_hosts: int
    network_range: str


class Gateway(BaseModel):
    ip: str
    interface: str
    interface_index: int
    metric: int
    reachability: str = 'untested'


class ConnectivityResult(BaseModel):
    target: IPvAnyAddress
    hostname: str | None = None
    timestamp: datetime = Field(default_factory=utcnow)
    response_times_ms: list[float | None] = Field(min_length=1, max_length=100)
    errors: list[str] = Field(default_factory=list)

    @field_validator('response_times_ms')
    @classmethod
    def validate_times(cls, values):
        import math
        if any(value is not None and (value < 0 or not math.isfinite(value)) for value in values):
            raise ValueError('RTT must be a finite non-negative number or None')
        return values

    @computed_field
    @property
    def packets_sent(self) -> int:
        return len(self.response_times_ms)

    @computed_field
    @property
    def packets_received(self) -> int:
        return sum(t is not None for t in self.response_times_ms)

    @computed_field
    @property
    def packet_loss_percent(self) -> float:
        return 100 * (1 - self.packets_received / self.packets_sent) if self.packets_sent else 0

    @property
    def latencies(self) -> list[float]:
        return [t for t in self.response_times_ms if t is not None]

    @computed_field
    @property
    def minimum_ms(self) -> float | None:
        return min(self.latencies, default=None)

    @computed_field
    @property
    def average_ms(self) -> float | None:
        return sum(self.latencies) / len(self.latencies) if self.latencies else None

    @computed_field
    @property
    def maximum_ms(self) -> float | None:
        return max(self.latencies, default=None)

    @computed_field
    @property
    def reachability(self) -> str:
        return 'responding' if self.packets_received else 'no_icmp_response'


class Device(BaseModel):
    ip: str
    mac: str | None = None
    hostname: str | None = None
    vendor: str | None = None
    first_discovered: datetime = Field(default_factory=utcnow)
    last_seen: datetime = Field(default_factory=utcnow)
    reachability: str = 'arp_response'


class DiscoveryResult(BaseModel):
    subnet: str
    devices: list[Device] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class Event(BaseModel):
    timestamp: datetime = Field(default_factory=utcnow)
    target: str
    kind: str
    observation: str


class Recommendation(BaseModel):
    code: str
    severity: str
    observation: str
    reason: str
    recommendation: str


class Performance(BaseModel):
    checks: int
    successful_checks: int
    failed_checks: int
    packets_sent: int
    packets_received: int
    packet_loss_percent: float | None
    availability_percent: float | None
    minimum_ms: float | None
    average_ms: float | None
    maximum_ms: float | None
    trend: str
    classification: str
    period_start: datetime | None = None
    period_end: datetime | None = None


class ReportSnapshot(BaseModel):
    """Portable, serializable collected observations for replay/export without a database."""
    interface: Interface | None = None
    network: NetworkInfo | None = None
    gateways: list[Gateway] = Field(default_factory=list)
    devices: list[Device] = Field(default_factory=list)
    results: list[ConnectivityResult] = Field(default_factory=list)
    performance: Performance | None = None
    events: list[Event] = Field(default_factory=list)
    recommendations: list[Recommendation] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
