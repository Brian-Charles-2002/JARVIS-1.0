"""System information tools backed by psutil. All SAFE, no confirmation needed."""
from __future__ import annotations

import platform

import psutil

from safety.risk import RiskLevel
from tools.base import BaseTool, ToolResult


def _fmt_bytes(value: float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024:
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} PB"


class GetSystemInfo(BaseTool):
    name = "get_system_info"
    description = "Return OS, machine, CPU count, and high-level resource summary."
    risk = RiskLevel.SAFE
    parameters = {"type": "object", "properties": {}}

    def run(self) -> ToolResult:
        mem = psutil.virtual_memory()
        return ToolResult.ok(self.name, {
            "os": f"{platform.system()} {platform.release()}",
            "machine": platform.machine(),
            "processor": platform.processor(),
            "python": platform.python_version(),
            "cpu_count": psutil.cpu_count(logical=True),
            "cpu_percent": psutil.cpu_percent(interval=0.1),
            "memory_total": _fmt_bytes(mem.total),
            "memory_used_percent": mem.percent,
        })


class GetCpuUsage(BaseTool):
    name = "get_cpu_usage"
    description = "Return current CPU usage percentage and core counts."
    risk = RiskLevel.SAFE
    parameters = {"type": "object", "properties": {}}

    def run(self) -> ToolResult:
        return ToolResult.ok(self.name, {
            "cpu_percent": psutil.cpu_percent(interval=0.3),
            "physical_cores": psutil.cpu_count(logical=False),
            "logical_cores": psutil.cpu_count(logical=True),
        })


class GetMemoryUsage(BaseTool):
    name = "get_memory_usage"
    description = "Return RAM usage (total, used, available, percent)."
    risk = RiskLevel.SAFE
    parameters = {"type": "object", "properties": {}}

    def run(self) -> ToolResult:
        m = psutil.virtual_memory()
        return ToolResult.ok(self.name, {
            "total": _fmt_bytes(m.total),
            "used": _fmt_bytes(m.used),
            "available": _fmt_bytes(m.available),
            "percent": m.percent,
        })


class GetDiskUsage(BaseTool):
    name = "get_disk_usage"
    description = "Return disk usage for drives (default: the system drive)."
    risk = RiskLevel.SAFE
    parameters = {"type": "object", "properties": {"path": {"type": "string"}}}

    def run(self, path: str = "C:\\") -> ToolResult:
        try:
            usage = psutil.disk_usage(path)
        except Exception as exc:  # noqa: BLE001
            return ToolResult.fail(self.name, "DISK_ERROR", str(exc))
        return ToolResult.ok(self.name, {
            "path": path,
            "total": _fmt_bytes(usage.total),
            "used": _fmt_bytes(usage.used),
            "free": _fmt_bytes(usage.free),
            "percent": usage.percent,
        })


class GetBatteryStatus(BaseTool):
    name = "get_battery_status"
    description = "Return battery percentage and charging state (laptops)."
    risk = RiskLevel.SAFE
    parameters = {"type": "object", "properties": {}}

    def run(self) -> ToolResult:
        battery = psutil.sensors_battery()
        if battery is None:
            return ToolResult.ok(self.name, {"battery": None, "message": "No battery detected (desktop?)."})
        return ToolResult.ok(self.name, {
            "percent": round(battery.percent, 1),
            "plugged_in": battery.power_plugged,
            "seconds_left": battery.secsleft if battery.secsleft != -1 else None,
        })


class GetNetworkStatus(BaseTool):
    name = "get_network_status"
    description = "Return network interface byte counters and a basic connectivity hint."
    risk = RiskLevel.SAFE
    parameters = {"type": "object", "properties": {}}

    def run(self) -> ToolResult:
        counters = psutil.net_io_counters()
        return ToolResult.ok(self.name, {
            "bytes_sent": counters.bytes_sent,
            "bytes_recv": counters.bytes_recv,
            "interfaces": list(psutil.net_if_addrs().keys()),
        })
