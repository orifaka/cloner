from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Optional

import psutil


@dataclass
class HostMetrics:
    cpu_percent: float
    ram_percent: float
    ram_used_mb: float
    ram_total_mb: float
    disk_percent: float
    disk_used_gb: float
    disk_total_gb: float


class MonitoringService:
    def host_metrics(self) -> HostMetrics:
        vm = psutil.virtual_memory()
        disk = psutil.disk_usage("/")
        return HostMetrics(
            cpu_percent=float(psutil.cpu_percent(interval=0.2)),
            ram_percent=float(vm.percent),
            ram_used_mb=round(vm.used / (1024 * 1024), 1),
            ram_total_mb=round(vm.total / (1024 * 1024), 1),
            disk_percent=float(disk.percent),
            disk_used_gb=round(disk.used / (1024 * 1024 * 1024), 2),
            disk_total_gb=round(disk.total / (1024 * 1024 * 1024), 2),
        )

    def host_metrics_dict(self) -> dict[str, Any]:
        return asdict(self.host_metrics())

    def process_alive(self, pid: Optional[int]) -> bool:
        if not pid:
            return False
        return psutil.pid_exists(pid)
