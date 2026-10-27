"""
Deterministic Command Risk Analyzer for SoulShell Terminal (Section 8).
Parses commands conservatively using shlex and structural inspection to flag:
- Recursive deletion (`rm -rf`, `find -delete`)
- Disk formatting & raw block writes (`mkfs`, `dd`, `fdisk`, `parted`, `wipefs`, `shred`)
- Destructive file overwrites (`> /etc/...`, `> /dev/...`)
- Privilege escalation (`sudo`, `su`, `pkexec`, `doas`, `chmod +s`)
- Piping remote scripts directly into a shell (`curl ... | sh`, `wget ... | bash`)
- Dangerous permission changes (`chmod 777`, `chmod 666`, `chmod -R`)
- Commands that could expose or exfiltrate secrets (`/etc/shadow`, `id_rsa`, `.env`)
- Shell operators (`;`, `&&`, `||`, `|`, `$()`, backticks) that chain multiple operations
Provides a concrete safer alternative for every flagged operation and never executes commands.
"""

from __future__ import annotations

import re
import shlex
from dataclasses import dataclass, field
from typing import List, Tuple

STATIC_DISCLAIMER = (
    "Static analysis cannot guarantee that any command is completely safe. "
    "Always inspect target paths, variables, and wildcards before executing."
)


@dataclass(frozen=True)
class SafetyFinding:
    """Single risk finding with explanation, highlighted segment, and safer alternative."""

    category: str
    severity: str  # 'critical', 'high', 'medium', 'low'
    message: str
    highlighted_operation: str
    safer_alternative: str


@dataclass
class SafetyReport:
    """Comprehensive deterministic risk report for a shell command."""

    command: str
    risk_level: str  # 'critical', 'high', 'medium', 'low', 'safe'
    findings: List[SafetyFinding] = field(default_factory=list)
    operators_detected: List[str] = field(default_factory=list)
    tokens: List[str] = field(default_factory=list)
    disclaimer: str = STATIC_DISCLAIMER

    @property
    def is_risky(self) -> bool:
        return self.risk_level in ("critical", "high", "medium", "low") and bool(
            self.findings
        )

    @property
    def is_dangerous(self) -> bool:
        return self.risk_level in ("critical", "high", "medium")

    @property
    def primary_safer_alternative(self) -> str:
        for f in self.findings:
            if f.safer_alternative:
                return f.safer_alternative
        return "Inspect target paths with `ls -la` or `--dry-run` before executing."

    def summary_text(self) -> str:
        if not self.findings:
            return f"Risk Level: SAFE — No known destructive patterns detected. ({self.disclaimer})"
        items = "; ".join(
            f"[{f.severity.upper()} - {f.category}] {f.message} (Safer: {f.safer_alternative})"
            for f in self.findings
        )
        return f"Risk Level: {self.risk_level.upper()} — {items} ({self.disclaimer})"


class CommandSafetyChecker:
    """Conservative shell parser and risk analyzer for Linux commands."""

    SEVERITY_RANK = {"safe": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}

    CRITICAL_PATHS = (
        "/",
        "/*",
        "/etc",
        "/boot",
        "/usr",
        "/var",
        "/bin",
        "/sbin",
        "/lib",
        "/lib64",
        "/dev",
        "/proc",
        "/sys",
        "/home",
        "~",
        "~/*",
    )

    SECRET_PATTERNS = (
        "/etc/shadow",
        "/etc/gshadow",
        "/etc/sudoers",
        "id_rsa",
        "id_ed25519",
        ".ssh/",
        ".aws/credentials",
        ".env",
        "API_KEY",
        "SECRET",
        "PASSWORD",
    )

    DISK_TOOLS = {
        "mkfs",
        "fdisk",
        "sfdisk",
        "cfdisk",
        "parted",
        "wipefs",
        "shred",
        "badblocks",
        "blkdiscard",
    }

    NETWORK_TOOLS = {"curl", "wget", "nc", "ncat", "netcat", "scp", "rsync"}
    SHELL_INTERPRETERS = {
        "sh",
        "bash",
        "zsh",
        "dash",
        "ksh",
        "python",
        "python3",
        "perl",
        "ruby",
    }

    @classmethod
    def analyze(cls, command: str) -> SafetyReport:
        """Analyze a command string without ever executing it."""
        raw = (command or "").strip()
        if not raw:
            return SafetyReport(command="", risk_level="safe")

        findings: List[SafetyFinding] = []
        tokens = cls._tokenize_safely(raw)
        operators = cls._detect_shell_operators(raw, tokens)

        # 1. Fork bomb detection
        if re.search(r":\s*\(\s*\)\s*\{.*:\s*\|\s*:.*&\s*\}\s*;\s*:", raw):
            findings.append(
                SafetyFinding(
                    category="Fork Bomb / Resource Exhaustion",
                    severity="critical",
                    message="Recursive shell function fork bomb will exhaust system PIDs and freeze the OS.",
                    highlighted_operation=raw,
                    safer_alternative="Never run fork bombs; inspect process limits with `ulimit -u`.",
                )
            )

        # 2. Shell operator complexity warning
        if any(op in operators for op in (";", "&&", "||", "$()", "`")):
            findings.append(
                SafetyFinding(
                    category="Compound Shell Operators",
                    severity="low",
                    message=(
                        f"Command chains multiple operations or command substitutions ({', '.join(operators)}), "
                        "which can hide secondary side effects."
                    ),
                    highlighted_operation=" ".join(operators),
                    safer_alternative="Run and verify each command step individually before chaining with `;`, `&&`, or `$()`.",
                )
            )

        subcommands = cls._split_subcommands(tokens)
        for sub_raw, sub_tokens in subcommands:
            if sub_tokens:
                cls._inspect_subcommand(sub_raw, sub_tokens, findings)

        # 3. Dangerous pipelines (e.g. curl ... | sh)
        cls._check_pipelines(raw, subcommands, findings)

        # 4. Destructive file overwrites (> /etc/..., > /dev/...)
        cls._check_redirections(raw, findings)

        # 5. Secret exposure / exfiltration
        cls._check_secrets(raw, subcommands, findings)

        highest = "safe"
        for f in findings:
            if cls.SEVERITY_RANK.get(f.severity, 0) > cls.SEVERITY_RANK.get(highest, 0):
                highest = f.severity

        return SafetyReport(
            command=raw,
            risk_level=highest,
            findings=findings,
            operators_detected=operators,
            tokens=tokens,
        )

    @staticmethod
    def _tokenize_safely(command: str) -> List[str]:
        try:
            lexer = shlex.shlex(command, posix=True, punctuation_chars="|&;<>")
            lexer.whitespace_split = True
            return list(lexer)
        except ValueError:
            return command.split()

    @staticmethod
    def _detect_shell_operators(raw: str, tokens: List[str]) -> List[str]:
        found: List[str] = []
        for op in ("|", "||", "&&", ";", "&", ">", ">>"):
            if op in tokens and op not in found:
                found.append(op)
        if "$(" in raw and "$()" not in found:
            found.append("$()")
        if "`" in raw and "`" not in found:
            found.append("`")
        return found

    @classmethod
    def _split_subcommands(cls, tokens: List[str]) -> List[Tuple[str, List[str]]]:
        separators = {"|", "||", "&&", ";", "&"}
        segments: List[Tuple[str, List[str]]] = []
        current: List[str] = []
        for tok in tokens:
            if tok in separators:
                if current:
                    segments.append((" ".join(current), current))
                    current = []
            else:
                current.append(tok)
        if current:
            segments.append((" ".join(current), current))
        return segments

    @staticmethod
    def _strip_wrappers(tokens: List[str]) -> Tuple[List[str], List[str]]:
        wrappers: List[str] = []
        idx = 0
        while idx < len(tokens):
            tok = tokens[idx]
            if "=" in tok and not tok.startswith("-"):
                wrappers.append(tok)
                idx += 1
            elif tok in ("sudo", "doas", "pkexec", "time", "nohup"):
                wrappers.append(tok)
                idx += 1
                while idx < len(tokens) and tokens[idx].startswith("-"):
                    flag = tokens[idx]
                    wrappers.append(flag)
                    idx += 1
                    if flag in ("-u", "-g", "-C") and idx < len(tokens):
                        wrappers.append(tokens[idx])
                        idx += 1
            else:
                break
        return wrappers, tokens[idx:]

    @classmethod
    def _inspect_subcommand(
        cls,
        sub_raw: str,
        sub_tokens: List[str],
        findings: List[SafetyFinding],
    ) -> None:
        wrappers, core = cls._strip_wrappers(sub_tokens)

        if any(w in ("sudo", "doas", "pkexec") for w in wrappers) or (
            core and core[0] in ("sudo", "su", "pkexec", "doas")
        ):
            findings.append(
                SafetyFinding(
                    category="Privilege Escalation",
                    severity="medium",
                    message="Command runs with superuser (root) privileges, bypassing normal user permission boundaries.",
                    highlighted_operation=sub_raw,
                    safer_alternative="Run read-only checks as a standard user first, or use `sudo -l` / `--dry-run` before elevating.",
                )
            )

        if not core:
            return

        exe = core[0].split("/")[-1]
        args = core[1:]

        # Recursive deletion (rm, find -delete)
        if exe == "rm":
            has_r = False
            has_f = False
            targets: List[str] = []
            for a in args:
                if a.startswith("--"):
                    if a == "--recursive":
                        has_r = True
                    elif a == "--force":
                        has_f = True
                    elif a == "--no-preserve-root":
                        findings.append(
                            SafetyFinding(
                                category="Recursive Deletion",
                                severity="critical",
                                message="`--no-preserve-root` disables root protection and can destroy the entire OS.",
                                highlighted_operation=sub_raw,
                                safer_alternative="Never use `--no-preserve-root`. Specify an exact subdirectory and use `rm -ri`.",
                            )
                        )
                elif a.startswith("-") and len(a) > 1:
                    flags = a[1:].lower()
                    if "r" in flags:
                        has_r = True
                    if "f" in flags:
                        has_f = True
                else:
                    targets.append(a)

            target_str = " ".join(targets) or "<target>"
            is_crit = any(
                t in cls.CRITICAL_PATHS or t.startswith("/etc/") or t.startswith("/boot")
                for t in targets
            )
            if has_r and is_crit:
                findings.append(
                    SafetyFinding(
                        category="Recursive Deletion",
                        severity="critical",
                        message=f"Recursive deletion targeting critical system/user path ({target_str}).",
                        highlighted_operation=sub_raw,
                        safer_alternative=f"Preview matching files first with `ls -la {target_str}` or `find {target_str} -maxdepth 2`.",
                    )
                )
            elif has_r or has_f:
                findings.append(
                    SafetyFinding(
                        category="Recursive Deletion",
                        severity="high",
                        message="Recursive or forced deletion (`rm -rf`) permanently removes files without confirmation or trash recovery.",
                        highlighted_operation=sub_raw,
                        safer_alternative=f"List contents first (`ls -la {target_str}`) or use interactive confirmation (`rm -ri {target_str}`).",
                    )
                )

        if exe == "find" and ("-delete" in args or "rm" in args):
            findings.append(
                SafetyFinding(
                    category="Recursive Deletion",
                    severity="high",
                    message="`find` with `-delete` or `-exec rm` bulk-deletes all matching files across subdirectories.",
                    highlighted_operation=sub_raw,
                    safer_alternative="Run the exact same `find` command without `-delete` (using `-print`) first to verify every matching file.",
                )
            )

        # Disk formatting & raw block writes
        if exe == "dd":
            has_dev = any(a.startswith("of=/dev/") or a.startswith("of=/") for a in args)
            findings.append(
                SafetyFinding(
                    category="Disk Formatting / Raw Write",
                    severity="critical" if has_dev else "high",
                    message="`dd` writes raw blocks directly and can irreversibly overwrite partition tables or filesystems.",
                    highlighted_operation=sub_raw,
                    safer_alternative="Verify block device names with `lsblk -f` before running `dd`, and double-check the `of=` target.",
                )
            )
        elif exe in cls.DISK_TOOLS or exe.startswith("mkfs."):
            findings.append(
                SafetyFinding(
                    category="Disk Formatting / Partitioning",
                    severity="critical",
                    message=f"`{exe}` formats or repartitions storage devices, permanently erasing existing data.",
                    highlighted_operation=sub_raw,
                    safer_alternative="Inspect mounted partitions with `lsblk -f` and `df -h` and back up data before formatting.",
                )
            )

        # Dangerous permission changes
        if exe == "chmod":
            is_recursive = "-R" in args or "--recursive" in args
            for a in args:
                if a in ("777", "0777", "666", "a+rwx", "o+w"):
                    findings.append(
                        SafetyFinding(
                            category="Dangerous Permission Change",
                            severity="high",
                            message=f"`chmod {a}` makes files or directories world-writable by any local user or process.",
                            highlighted_operation=sub_raw,
                            safer_alternative="Use `chmod 755` for executable scripts/directories or `chmod 644` (`600` for secrets) for files.",
                        )
                    )
                elif "+s" in a or (
                    len(a) == 4 and a.isdigit() and a[0] in ("4", "2", "6")
                ):
                    findings.append(
                        SafetyFinding(
                            category="Dangerous Permission Change (SUID/SGID)",
                            severity="high",
                            message=f"`chmod {a}` sets SUID/SGID bits, allowing binaries to execute with elevated owner/group privileges.",
                            highlighted_operation=sub_raw,
                            safer_alternative="Avoid SUID/SGID on custom scripts; use scoped `sudoers` rules instead.",
                        )
                    )
            if is_recursive and not any(
                f.category.startswith("Dangerous Permission") for f in findings
            ):
                findings.append(
                    SafetyFinding(
                        category="Recursive Permission Change",
                        severity="medium",
                        message="`chmod -R` modifies permissions across all nested files and directories.",
                        highlighted_operation=sub_raw,
                        safer_alternative="Use `find <dir> -type d -exec chmod 755 {} +` and `find <dir> -type f -exec chmod 644 {} +`.",
                    )
                )

    @classmethod
    def _check_pipelines(
        cls,
        raw: str,
        subcommands: List[Tuple[str, List[str]]],
        findings: List[SafetyFinding],
    ) -> None:
        if len(subcommands) < 2 or "|" not in raw:
            return
        for i in range(len(subcommands) - 1):
            _, left_toks = subcommands[i]
            _, right_toks = subcommands[i + 1]
            _, left_core = cls._strip_wrappers(left_toks)
            _, right_core = cls._strip_wrappers(right_toks)
            if not left_core or not right_core:
                continue
            l_exe = left_core[0].split("/")[-1]
            r_exe = right_core[0].split("/")[-1]

            if l_exe in ("curl", "wget") and r_exe in cls.SHELL_INTERPRETERS:
                findings.append(
                    SafetyFinding(
                        category="Remote Script Execution Pipeline",
                        severity="critical",
                        message=f"Piping downloaded output from `{l_exe}` directly into `{r_exe}` executes unverified remote code.",
                        highlighted_operation=f"{l_exe} ... | {r_exe}",
                        safer_alternative=f"Download the script to a file first (`{l_exe} -o install.sh <url>`), inspect it with `less install.sh`, then run it.",
                    )
                )

    @classmethod
    def _check_redirections(cls, raw: str, findings: List[SafetyFinding]) -> None:
        matches = re.findall(r"(?:^|\s)(>{1,2})\s*([^\s;|&]+)", raw)
        for op, target in matches:
            clean_target = target.strip("'\"")
            if clean_target.startswith(
                ("/etc/", "/boot/", "/dev/sd", "/dev/nvme", "/dev/vd", "/proc/", "/sys/")
            ):
                findings.append(
                    SafetyFinding(
                        category="Destructive File Overwrite",
                        severity="critical",
                        message=f"Redirection `{op} {clean_target}` overwrites or modifies a critical system file or block device.",
                        highlighted_operation=f"{op} {clean_target}",
                        safer_alternative=f"Back up `{clean_target}` first (`cp {clean_target} {clean_target}.bak`) and edit safely with `sudoedit`.",
                    )
                )
            elif op == ">" and clean_target.startswith(("/", "~")):
                findings.append(
                    SafetyFinding(
                        category="Destructive File Overwrite",
                        severity="medium",
                        message=f"Single `> {clean_target}` truncates and overwrites existing file contents immediately.",
                        highlighted_operation=f"{op} {clean_target}",
                        safer_alternative=f"Check if `{clean_target}` exists with `ls -l {clean_target}` or use `>>` to append.",
                    )
                )

    @classmethod
    def _check_secrets(
        cls,
        raw: str,
        subcommands: List[Tuple[str, List[str]]],
        findings: List[SafetyFinding],
    ) -> None:
        has_net = False
        for _, sub_toks in subcommands:
            _, core = cls._strip_wrappers(sub_toks)
            if core and core[0].split("/")[-1] in cls.NETWORK_TOOLS:
                has_net = True
                break

        matched = [pat for pat in cls.SECRET_PATTERNS if pat in raw]
        if matched and has_net:
            findings.append(
                SafetyFinding(
                    category="Secret Exposure / Exfiltration Risk",
                    severity="critical",
                    message=f"Command combines a network transfer tool with sensitive credential/secret indicator ({', '.join(matched)}).",
                    highlighted_operation=", ".join(matched),
                    safer_alternative="Never transmit `/etc/shadow`, private SSH keys, or `.env` secrets over unverified network endpoints.",
                )
            )
        elif matched:
            findings.append(
                SafetyFinding(
                    category="Sensitive Credential / Secret Access",
                    severity="medium",
                    message=f"Command references sensitive credential or security data ({', '.join(matched)}).",
                    highlighted_operation=", ".join(matched),
                    safer_alternative="Avoid printing raw secrets to shared terminals or logs; redact sensitive fields with `grep -v`.",
                )
            )
