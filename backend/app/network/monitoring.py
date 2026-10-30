"""Fixed worker pool, bounded history, explicit lifecycle and evidence-based events."""
import asyncio
from collections import defaultdict, deque
from collections.abc import Awaitable, Callable
from app.analysis.performance import Thresholds
from app.models.network import ConnectivityResult, Event
from app.network.connectivity import ping


class Monitor:
    def __init__(self, targets: list[str], *, interval: float = 10, concurrency: int = 8,
                 count: int = 4, timeout_ms: int = 1000, history_limit: int = 1000,
                 thresholds: Thresholds | None = None,
                 probe: Callable[..., Awaitable[ConnectivityResult]] = ping):
        from ipaddress import ip_address
        self.targets = list(dict.fromkeys(str(ip_address(t)) for t in targets))
        if not self.targets or len(self.targets) > 4096:
            raise ValueError('Select 1..4096 targets')
        if interval < 0.1 or not 1 <= concurrency <= 64 or history_limit < 1:
            raise ValueError('Invalid monitoring interval, concurrency or history limit')
        if not 1 <= count <= 100 or not 100 <= timeout_ms <= 60000:
            raise ValueError('Invalid ping count or timeout')
        self.interval, self.concurrency = interval, concurrency
        self.count, self.timeout_ms, self.probe = count, timeout_ms, probe
        self.thresholds = thresholds or Thresholds()
        self.history = {t: deque(maxlen=history_limit) for t in self.targets}
        self.events: deque[Event] = deque(maxlen=history_limit)
        self._previous: dict[str, bool] = {}
        self._streaks = defaultdict(lambda: {'latency': 0, 'loss': 0, 'failure': 0})
        self._task: asyncio.Task | None = None

    @property
    def running(self) -> bool:
        return self._task is not None and not self._task.done()

    def record(self, result: ConnectivityResult) -> None:
        target = str(result.target)
        if target not in self.history:
            raise ValueError('Result target is not monitored')
        self.history[target].append(result)
        responding = result.packets_received > 0
        previous = self._previous.get(target)
        if previous is not None and previous != responding:
            self.events.append(Event(target=target, kind='recovery' if responding else 'icmp_interruption',
                                     observation=f'ICMP responses changed from {previous} to {responding}'))
        self._previous[target] = responding
        flags = {'latency': result.average_ms is not None and result.average_ms >= self.thresholds.high_latency_ms,
                 'loss': result.packet_loss_percent >= self.thresholds.loss_percent,
                 'failure': not responding}
        for key, active in flags.items():
            self._streaks[target][key] = self._streaks[target][key] + 1 if active else 0
            if self._streaks[target][key] == self.thresholds.consecutive_checks:
                self.events.append(Event(target=target, kind='sustained_' + key,
                                         observation=f'{self.thresholds.consecutive_checks} consecutive checks: '
                                         f'{key}; last mean={result.average_ms} ms, loss={result.packet_loss_percent:.1f}%'))

    def start(self) -> None:
        if self.running:
            raise RuntimeError('Monitoring is already running')
        self._task = asyncio.create_task(self._run(), name='tether-monitor')

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            finally:
                self._task = None

    async def _run(self) -> None:
        while True:
            queue = asyncio.Queue()
            for target in self.targets:
                queue.put_nowait(target)

            async def worker() -> None:
                while not queue.empty():
                    target = queue.get_nowait()
                    try:
                        result = await self.probe(target, count=self.count, timeout_ms=self.timeout_ms)
                        self.record(result)
                    except Exception as exc:
                        self.events.append(Event(target=target, kind='probe_error', observation=str(exc)))
                    finally:
                        queue.task_done()

            workers = [asyncio.create_task(worker()) for _ in range(min(self.concurrency, len(self.targets)))]
            try:
                await asyncio.gather(*workers)
            finally:
                for task in workers:
                    task.cancel()
                await asyncio.gather(*workers, return_exceptions=True)
            # Interval is a pause AFTER a completed cycle; cycles never overlap.
            await asyncio.sleep(self.interval)
