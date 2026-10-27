"""
System Information Commands for SoulShell Terminal (Section 7).
Commands:
- sysinfo
- cpu
- memory
- disk [path]
- uptime
- processes
- environment
Redacts all secret environment variables automatically.
"""

from __future__ import annotations

from rich.table import Table

from soulshell.core.command_router import CommandContext, CommandRouter
from soulshell.services.system_info import SystemInfoService


def _render_kv_table(ctx: CommandContext, title: str, data: dict[str, str]) -> None:
    table = Table(title=title, border_style=ctx.ui.styles["border"])
    table.add_column("Metric", style=ctx.ui.styles["secondary"])
    table.add_column("Value", style="white")
    for k, v in data.items():
        table.add_row(k, v)
    ctx.ui.console.print(table)


def cmd_sysinfo(ctx: CommandContext) -> int:
    _render_kv_table(
        ctx, "🖥️ Linux System Information", SystemInfoService.get_sysinfo()
    )
    return 0


def cmd_cpu(ctx: CommandContext) -> int:
    _render_kv_table(ctx, "⚡ Processor (CPU) Details", SystemInfoService.get_cpu_info())
    return 0


def cmd_memory(ctx: CommandContext) -> int:
    _render_kv_table(ctx, "🧠 System Memory (RAM & Swap)", SystemInfoService.get_memory_info())
    return 0


def cmd_disk(ctx: CommandContext) -> int:
    target = ctx.args[0] if ctx.args else "/"
    try:
        info = SystemInfoService.get_disk_info(target)
    except OSError as exc:
        ctx.ui.print_error(f"Could not inspect disk path '{target}': {exc}")
        return 1
    _render_kv_table(ctx, f"💾 Disk Space Usage ({target})", info)
    return 0


def cmd_uptime(ctx: CommandContext) -> int:
    up_str = SystemInfoService.get_uptime_info()
    ctx.ui.print_panel(f"**System Uptime:** {up_str}", title="⏱️ Uptime")
    return 0


def cmd_processes(ctx: CommandContext) -> int:
    procs = SystemInfoService.get_processes(limit=15)
    table = Table(
        title="⚙️ Top Running Processes (Read-Only Snapshot)",
        border_style=ctx.ui.styles["border"],
    )
    table.add_column("PID", style=ctx.ui.styles["primary"], width=8)
    table.add_column("USER", style=ctx.ui.styles["secondary"], width=12)
    table.add_column("CPU%", width=8)
    table.add_column("MEM%", width=8)
    table.add_column("COMMAND", style="white")
    for p in procs:
        table.add_row(p["PID"], p["USER"], p["CPU%"], p["MEM%"], p["COMMAND"])
    ctx.ui.console.print(table)
    return 0


def cmd_environment(ctx: CommandContext) -> int:
    env_map = SystemInfoService.get_sanitized_environment()
    filter_prefix = ctx.args[0].upper() if ctx.args else ""
    table = Table(
        title="🔐 Sanitized Environment Variables (Secrets Automatically Redacted)",
        border_style=ctx.ui.styles["border"],
    )
    table.add_column("Variable", style=ctx.ui.styles["secondary"])
    table.add_column("Value", style="white")
    count = 0
    for k, v in env_map.items():
        if filter_prefix and filter_prefix not in k.upper():
            continue
        table.add_row(k, v)
        count += 1
        if count >= 35 and not filter_prefix:
            break
    ctx.ui.console.print(table)
    if not filter_prefix and len(env_map) > 35:
        ctx.ui.console.print(
            f"[dim]Showing 35 of {len(env_map)} variables. Use `environment <filter>` to filter.[/dim]"
        )
    return 0


def register_system_commands(router: CommandRouter) -> None:
    router.register(
        "sysinfo",
        "System Information",
        "sysinfo",
        "Display Linux distribution, kernel, architecture, and Python version.",
        cmd_sysinfo,
    )
    router.register(
        "cpu",
        "System Information",
        "cpu",
        "Display CPU model, core count, and system load averages.",
        cmd_cpu,
    )
    router.register(
        "memory",
        "System Information",
        "memory",
        "Display total, used, and available RAM and swap memory.",
        cmd_memory,
        aliases=["mem"],
    )
    router.register(
        "disk",
        "System Information",
        "disk [path]",
        "Display filesystem disk capacity, used space, and free space.",
        cmd_disk,
    )
    router.register(
        "uptime",
        "System Information",
        "uptime",
        "Show how long the system has been running.",
        cmd_uptime,
    )
    router.register(
        "processes",
        "System Information",
        "processes",
        "List top running processes sorted by memory usage.",
        cmd_processes,
        aliases=["ps"],
    )
    router.register(
        "environment",
        "System Information",
        "environment [filter]",
        "Display environment variables with passwords/tokens/keys redacted.",
        cmd_environment,
        aliases=["env"],
    )
