"""
Security Utilities Commands for SoulShell Terminal (Sections 7 & 8).
Commands:
- tools
- risk <command>
- checkurl <url>
- loganalyze <file>
- scan <target> [--yes]  (Authorized defensive Nmap wrapper restricted to loopback/private/lab targets with explicit confirmation)
"""

from __future__ import annotations

import shutil
import subprocess

from rich.table import Table

from soulshell.core.command_router import CommandContext, CommandRouter
from soulshell.services.command_safety import CommandSafetyChecker
from soulshell.services.log_analyzer import LogAnalyzerService
from soulshell.services.system_info import SystemInfoService


def cmd_tools(ctx: CommandContext) -> int:
    """Detect installed security and network diagnostic tools without assuming all are present."""
    rows = SystemInfoService.detect_security_tools()
    table = Table(
        title="🛡️ Defensive Security & Network Tool Detection",
        border_style=ctx.ui.styles["border"],
    )
    table.add_column("Tool", style=ctx.ui.styles["primary"], width=16)
    table.add_column("Category", style=ctx.ui.styles["secondary"], width=20)
    table.add_column("Status", width=12)
    table.add_column("Path", style="dim", width=22)
    table.add_column("Purpose", style="white")

    installed_cnt = 0
    for r in rows:
        is_inst = r["Status"] == "Installed"
        if is_inst:
            installed_cnt += 1
        status_cell = (
            "[bold bright_green]Installed[/bold bright_green]"
            if is_inst
            else "[dim]Not Found[/dim]"
        )
        table.add_row(r["Tool"], r["Category"], status_cell, r["Path"], r["Purpose"])

    ctx.ui.console.print(table)
    ctx.ui.console.print(
        f"[dim]Detected {installed_cnt} of {len(rows)} cataloged security/network utilities on this host.[/dim]"
    )
    return 0


def cmd_risk(ctx: CommandContext) -> int:
    """
    Analyze a shell command for potentially dangerous operations (Section 8).
    Displays the command, explains why it might be risky, highlights the relevant operation,
    and offers a safer alternative. Never executes the command.
    """
    cmd_str = ctx.arg_text.strip()
    if not cmd_str:
        ctx.ui.print_error(
            "Please provide a shell command to analyze.",
            hint="Example: `risk rm -rf /tmp/example` or `risk curl https://example.com/install.sh | sh`",
        )
        return 1

    report = CommandSafetyChecker.analyze(cmd_str)
    ctx.ui.print_code_panel(cmd_str, language="bash", title="🔎 Analyzed Command (Not Executed)")

    level = report.risk_level.upper()
    border = (
        "red"
        if report.risk_level in ("critical", "high")
        else ("yellow" if report.risk_level in ("medium", "low") else "green")
    )

    lines = [
        f"**Overall Risk Level:** `{level}`",
    ]
    if report.operators_detected:
        lines.append(
            f"**Shell Operators Detected:** `{', '.join(report.operators_detected)}`"
        )

    if not report.findings:
        lines.append(
            "\n**Assessment:** No known destructive flags, raw block writes, privilege escalations, or remote shell pipelines were detected."
        )
        lines.append(f"**Safer Practice:** {report.primary_safer_alternative}")
    else:
        lines.append("\n### Identified Risk Factors & Safer Alternatives")
        for idx, f in enumerate(report.findings, 1):
            lines.append(
                f"{idx}. **[{f.severity.upper()}] {f.category}**\n"
                f"   - **Highlighted Operation:** `{f.highlighted_operation}`\n"
                f"   - **Why It Is Risky:** {f.message}\n"
                f"   - **Safer Alternative:** {f.safer_alternative}"
            )

    lines.append(f"\n*{report.disclaimer}*")
    ctx.ui.print_panel(
        "\n".join(lines),
        title=f"🛡️ Command Risk Assessment: {level}",
        border_style=border,
    )

    ctx.db.add_command_history(
        command=cmd_str,
        purpose="Analyzed via `risk` command",
        risk_level=report.risk_level,
        risk_warnings=report.summary_text(),
        save_history=ctx.config.save_history,
    )
    return 0


def cmd_checkurl(ctx: CommandContext) -> int:
    """Inspect a URL for basic structural suspicious patterns."""
    if not ctx.args:
        ctx.ui.print_error(
            "Usage: `checkurl <url>`",
            hint="Example: `checkurl http://admin@192.168.1.10/login.exe`",
        )
        return 1

    url_str = ctx.args[0]
    try:
        report = SystemInfoService.check_url_heuristics(url_str)
    except ValueError as exc:
        ctx.ui.print_error(str(exc))
        return 1

    bullets = "\n".join(f"- {f}" for f in report.findings)
    body = (
        f"**URL:** `{report.url}`\n"
        f"**Scheme:** `{report.scheme}` | **Hostname:** `{report.hostname}`\n"
        f"**Heuristic Indicator:** `{report.risk_indicator.upper()}`\n\n"
        f"### Structural Observations\n{bullets}\n\n"
        f"*{report.disclaimer}*"
    )
    ctx.ui.print_panel(body, title="🌐 Defensive URL Pattern Check")
    return 0


def cmd_loganalyze(ctx: CommandContext) -> int:
    """Analyze a user-selected log file in read-only mode with a 2 MB safety limit."""
    if not ctx.arg_text.strip():
        ctx.ui.print_error(
            "Usage: `loganalyze <file_path>`",
            hint="Example: `loganalyze /var/log/syslog` or `loganalyze ./sample.log`",
        )
        return 1

    file_path = ctx.args[0]
    analyzer = LogAnalyzerService(provider=ctx.ai_provider)
    try:
        report = analyzer.analyze_file(
            file_path, config=ctx.config, use_ai=True
        )
    except (FileNotFoundError, ValueError, OSError) as exc:
        ctx.ui.print_error(str(exc))
        return 1

    ts_span = (
        f"{report.first_timestamp} -> {report.last_timestamp}"
        if report.first_timestamp
        else "No standard timestamps detected"
    )
    patterns = "\n".join(f"- {p}" for p in report.notable_patterns)
    explanations = "\n".join(f"- {e}" for e in report.possible_explanations)
    steps = "\n".join(f"{i}. {s}" for i, s in enumerate(report.investigation_steps, 1))

    body = (
        f"**File:** `{report.file_path}` (Read-Only)\n"
        f"**Lines Analyzed:** {report.line_count} | **Timestamp Range:** {ts_span}\n"
        f"**Errors:** `{report.error_count}` | **Warnings:** `{report.warning_count}` | **Auth Failures:** `{report.auth_failure_count}`\n\n"
        f"### Notable Patterns\n{patterns}\n\n"
        f"### Possible Explanations\n{explanations}\n\n"
        f"### Defensive Investigation Steps\n{steps}\n"
    )
    if report.ai_summary:
        body += f"\n### AI Spirit Analysis\n{report.ai_summary}\n"
    body += f"\n*{report.disclaimer}*"

    ctx.ui.print_panel(body, title="📜 Defensive Log Analysis Report")
    return 0


def cmd_scan(ctx: CommandContext) -> int:
    """
    Preserved & safeguarded authorized Nmap port audit wrapper (Section 7).
    Requires:
    1. Target restricted to loopback/private/authorized lab scope (`127.0.0.1`, `localhost`, RFC1918 private IPs).
    2. Explicit `--yes` confirmation flag.
    Never launched automatically from an AI response.
    """
    if not ctx.args:
        ctx.ui.print_error(
            "Usage: `scan <authorized-target> --yes`",
            hint="Targets are restricted to localhost or private lab IPs (e.g., `scan 127.0.0.1 --yes`).",
        )
        return 1

    target = ctx.args[0]
    if not SystemInfoService.is_authorized_scan_target(target):
        ctx.ui.print_error(
            f"Target '{target}' is outside the permitted local/private lab scope.",
            hint="For safety, `scan` only permits `localhost`, loopback (`127.0.0.1`), or private RFC1918 lab addresses.",
        )
        return 1

    if "--yes" not in ctx.args:
        ctx.ui.print_warning(
            f"Explicit confirmation required for authorized port audit of `{target}`.\n"
            f"Re-run with: `scan {target} --yes`"
        )
        return 1

    nmap_bin = shutil.which("nmap")
    if not nmap_bin:
        ctx.ui.print_warning(
            "`nmap` is not installed on this system. Install it with `sudo apt install nmap` or use `connections` to view local listening ports."
        )
        return 1

    res = subprocess.run(
        [nmap_bin, "-F", "-T3", target],
        capture_output=True,
        text=True,
        timeout=25.0,
        check=False,
    )
    ctx.ui.print_panel(
        f"```text\n{(res.stdout or res.stderr).strip()}\n```",
        title=f"🛡️ Authorized Nmap Quick Audit: {target}",
    )
    return 0


def register_security_commands(router: CommandRouter) -> None:
    router.register(
        "tools",
        "Security Utilities",
        "tools",
        "Detect installed defensive security and network diagnostic utilities.",
        cmd_tools,
    )
    router.register(
        "risk",
        "Security Utilities",
        "risk <command>",
        "Analyze a shell command for destructive operations and suggest safer alternatives.",
        cmd_risk,
    )
    router.register(
        "checkurl",
        "Security Utilities",
        "checkurl <url>",
        "Check a URL for structural suspicious patterns (HTTP, @ userinfo, raw IP, punycode).",
        cmd_checkurl,
    )
    router.register(
        "loganalyze",
        "Security Utilities",
        "loganalyze <file>",
        "Analyze a local text log file in read-only mode (2 MB limit).",
        cmd_loganalyze,
    )
    router.register(
        "scan",
        "Security Utilities",
        "scan <target> --yes",
        "Run an authorized, confirmed quick port audit on localhost/private lab targets.",
        cmd_scan,
    )
