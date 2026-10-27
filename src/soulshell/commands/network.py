"""
Network Utilities Commands for SoulShell Terminal (Section 7).
Commands:
- netinfo
- interfaces
- connections
- dns <domain>
- ping <host>
"""

from __future__ import annotations

from rich.table import Table

from soulshell.core.command_router import CommandContext, CommandRouter
from soulshell.services.system_info import SystemInfoService


def cmd_netinfo(ctx: CommandContext) -> int:
    info = SystemInfoService.get_netinfo()
    table = Table(title="🌐 Network Overview", border_style=ctx.ui.styles["border"])
    table.add_column("Property", style=ctx.ui.styles["secondary"])
    table.add_column("Value", style="white")
    for k, v in info.items():
        table.add_row(k, v)
    ctx.ui.console.print(table)
    return 0


def cmd_interfaces(ctx: CommandContext) -> int:
    ifaces = SystemInfoService.get_interfaces()
    table = Table(
        title="🔌 Network Interfaces", border_style=ctx.ui.styles["border"]
    )
    table.add_column("Interface", style=ctx.ui.styles["primary"])
    table.add_column("State", style=ctx.ui.styles["secondary"])
    table.add_column("Addresses / Info", style="white")
    for row in ifaces:
        table.add_row(row["Interface"], row["State"], row["Addresses"])
    ctx.ui.console.print(table)
    return 0


def cmd_connections(ctx: CommandContext) -> int:
    conns = SystemInfoService.get_connections(limit=25)
    if not conns:
        ctx.ui.print_panel(
            "No active/listening sockets returned by local inspection.",
            title="🔗 Network Connections",
        )
        return 0
    table = Table(
        title="🔗 Listening & Active Network Sockets (Read-Only)",
        border_style=ctx.ui.styles["border"],
    )
    table.add_column("Protocol", style=ctx.ui.styles["primary"], width=10)
    table.add_column("State", style=ctx.ui.styles["secondary"], width=12)
    table.add_column("Local Address:Port", style="white")
    table.add_column("Peer Address:Port", style="dim")
    for c in conns:
        table.add_row(
            c["Netid"],
            c["State"],
            c["Local Address:Port"],
            c["Peer Address:Port"],
        )
    ctx.ui.console.print(table)
    return 0


def cmd_dns(ctx: CommandContext) -> int:
    if not ctx.args:
        ctx.ui.print_error("Usage: `dns <domain>` (e.g., `dns localhost` or `dns example.com`)")
        return 1
    domain = ctx.args[0]
    try:
        records = SystemInfoService.resolve_dns(domain)
    except ValueError as exc:
        ctx.ui.print_error(str(exc))
        return 1
    except Exception as exc:
        ctx.ui.print_error(
            f"Could not resolve '{domain}': {exc}",
            hint="Verify network connectivity or `/etc/resolv.conf`.",
        )
        return 1

    body = "\n".join(f"- `{r}`" for r in records)
    ctx.ui.print_panel(body, title=f"🔎 DNS Resolution: {domain}")
    return 0


def cmd_ping(ctx: CommandContext) -> int:
    if not ctx.args:
        ctx.ui.print_error("Usage: `ping <host>` (e.g., `ping 127.0.0.1`)")
        return 1
    host = ctx.args[0]
    try:
        res = SystemInfoService.ping_host(host, count=2, timeout_sec=3)
    except ValueError as exc:
        ctx.ui.print_error(str(exc))
        return 1

    status_badge = (
        "[bold bright_green]REACHABLE[/bold bright_green]"
        if res["reachable"]
        else "[bold bright_red]UNREACHABLE[/bold bright_red]"
    )
    body = (
        f"**Host:** `{res['host']}`\n"
        f"**Method:** {res['method']}\n"
        f"**Status:** {status_badge}\n\n"
        f"```text\n{res['output']}\n```"
    )
    ctx.ui.print_panel(body, title=f"📡 Connectivity Check: {host}")
    return 0 if res["reachable"] else 1


def register_network_commands(router: CommandRouter) -> None:
    router.register(
        "netinfo",
        "Network Utilities",
        "netinfo",
        "Display hostname, FQDN, and detected network interfaces.",
        cmd_netinfo,
    )
    router.register(
        "interfaces",
        "Network Utilities",
        "interfaces",
        "List network interfaces, operational state, and assigned addresses.",
        cmd_interfaces,
        aliases=["ifaces"],
    )
    router.register(
        "connections",
        "Network Utilities",
        "connections",
        "Display listening and active TCP/UDP sockets.",
        cmd_connections,
        aliases=["ports"],
    )
    router.register(
        "dns",
        "Network Utilities",
        "dns <domain>",
        "Resolve IPv4/IPv6 records for a domain or hostname.",
        cmd_dns,
    )
    router.register(
        "ping",
        "Network Utilities",
        "ping <host>",
        "Test reachability of a host with safe timeouts and input validation.",
        cmd_ping,
    )
