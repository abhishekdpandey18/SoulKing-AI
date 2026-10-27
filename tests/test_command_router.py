"""
Automated tests for CommandRouter, command dispatching, aliases,
and unknown command fuzzy suggestions (Section 7 & 16).
"""

from __future__ import annotations

import io
import tempfile
import unittest
from pathlib import Path

from rich.console import Console

from soulshell.cli import SoulShellCLI
from soulshell.core.config import SoulConfig
from soulshell.database.db import DatabaseManager


class TestCommandRouter(unittest.TestCase):
    """Test suite for CommandRouter and CLI command execution."""

    def setUp(self) -> None:
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp_dir.name) / "router_test.db"
        self.db = DatabaseManager(db_path=self.db_path)
        self.output_buf = io.StringIO()
        self.console = Console(file=self.output_buf, force_terminal=False, width=100)
        self.cfg = SoulConfig(animations=False, theme="plain")
        self.cli = SoulShellCLI(config=self.cfg, db=self.db, console=self.console)

    def tearDown(self) -> None:
        self.tmp_dir.cleanup()

    def test_all_required_commands_are_registered(self) -> None:
        required_commands = [
            # General
            "help",
            "about",
            "version",
            "clear",
            "banner",
            "status",
            "config",
            "mode",
            "history",
            "favorites",
            "exit",
            "quit",
            # System Information
            "sysinfo",
            "cpu",
            "memory",
            "disk",
            "uptime",
            "processes",
            "environment",
            # Linux Assistance
            "explain",
            "suggest",
            "permissions",
            "findfile",
            # Network Utilities
            "netinfo",
            "interfaces",
            "connections",
            "dns",
            "ping",
            # Security Utilities
            "tools",
            "risk",
            "checkurl",
            "loganalyze",
            # Ghost Stories
            "story",
        ]
        for cmd in required_commands:
            spec = self.cli.router.resolve_command(cmd)
            self.assertIsNotNone(spec, f"Command '{cmd}' must be registered in router")

    def test_known_commands_execute_cleanly(self) -> None:
        for cmd_line in (
            "help",
            "help risk",
            "about",
            "version",
            "status",
            "sysinfo",
            "cpu",
            "memory",
            "disk /",
            "uptime",
            "processes",
            "environment PATH",
            "netinfo",
            "interfaces",
            "connections",
            "tools",
            "risk rm -rf /tmp/example",
            "checkurl http://admin@192.168.1.1/setup.exe",
            "permissions 755",
        ):
            rc = self.cli.execute_command(cmd_line)
            self.assertEqual(rc, 0, f"Command '{cmd_line}' returned non-zero status {rc}")

    def test_unknown_command_returns_127_and_suggests_similar(self) -> None:
        self.output_buf.seek(0)
        self.output_buf.truncate(0)
        rc = self.cli.execute_command("sysinf")
        self.assertEqual(rc, 127)
        rendered = self.output_buf.getvalue()
        self.assertIn("Unknown command", rendered)
        self.assertIn("sysinfo", rendered)

    def test_exit_command_sets_should_exit_flag(self) -> None:
        self.assertFalse(self.cli.context.should_exit)
        rc = self.cli.execute_command("exit")
        self.assertEqual(rc, 0)
        self.assertTrue(self.cli.context.should_exit)


if __name__ == "__main__":
    unittest.main()
