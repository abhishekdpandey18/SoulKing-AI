"""
Defensive Log File Analyzer for SoulShell Terminal (Section 7 `loganalyze <file>`).
Inspects local log files in read-only mode with a 2 MB safety limit,
protecting against binary files, missing files, and oversized inputs.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from soulshell.ai.ollama_provider import AIProvider, AIProviderError
from soulshell.ai.personality import build_system_prompt
from soulshell.core.config import MAX_LOG_FILE_BYTES, SoulConfig

DEFENSIVE_LOG_DISCLAIMER = (
    "Log anomalies often reflect routine misconfigurations, expired credentials, or network timeouts. "
    "Uncertain entries should never be treated as confirmed attacks without corroborating evidence."
)


@dataclass
class LogAnalysisReport:
    """Structured defensive analysis of a log file."""

    file_path: str
    line_count: int
    error_count: int
    warning_count: int
    auth_failure_count: int
    first_timestamp: Optional[str]
    last_timestamp: Optional[str]
    notable_patterns: List[str] = field(default_factory=list)
    possible_explanations: List[str] = field(default_factory=list)
    investigation_steps: List[str] = field(default_factory=list)
    ai_summary: str = ""
    disclaimer: str = DEFENSIVE_LOG_DISCLAIMER


class LogAnalyzerService:
    """Read-only log file inspector with size limits and defensive triage."""

    TIMESTAMP_REGEX = re.compile(
        r"(\d{4}-\d{2}-\d{2}[T\s]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?|"
        r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2}\s+\d{2}:\d{2}:\d{2})"
    )
    ERROR_REGEX = re.compile(
        r"\b(ERROR|CRITICAL|FATAL|PANIC|SEGFAULT|ERR)\b", re.IGNORECASE
    )
    WARNING_REGEX = re.compile(r"\b(WARN|WARNING)\b", re.IGNORECASE)
    AUTH_FAIL_REGEX = re.compile(
        r"(Failed password|authentication failure|Invalid user|Connection closed by authenticating user|sudo:.*authentication failure)",
        re.IGNORECASE,
    )

    def __init__(self, provider: Optional[AIProvider] = None) -> None:
        self.provider = provider

    @classmethod
    def read_log_file_safely(
        cls, file_path: str | Path, max_bytes: int = MAX_LOG_FILE_BYTES
    ) -> str:
        path = Path(file_path).expanduser()
        if not path.exists():
            raise FileNotFoundError(f"Log file does not exist: {path}")
        if not path.is_file():
            raise ValueError(f"Path is not a regular file: {path}")

        size = path.stat().st_size
        if size > max_bytes:
            raise ValueError(
                f"Log file size ({size:,} bytes) exceeds the {max_bytes:,} byte safety limit. "
                "Use `tail -n 500` to inspect a smaller excerpt."
            )

        raw = path.read_bytes()
        if b"\x00" in raw[:4096]:
            raise ValueError("File appears to be a binary file rather than a text log.")
        return raw.decode("utf-8", errors="replace")

    def analyze_file(
        self,
        file_path: str | Path,
        config: Optional[SoulConfig] = None,
        use_ai: bool = True,
        max_bytes: int = MAX_LOG_FILE_BYTES,
    ) -> LogAnalysisReport:
        text = self.read_log_file_safely(file_path, max_bytes=max_bytes)
        return self.analyze_text(
            text,
            source_name=str(file_path),
            config=config,
            use_ai=use_ai,
            max_bytes=max_bytes,
        )

    def analyze_text(
        self,
        log_text: str,
        source_name: str = "<inline>",
        config: Optional[SoulConfig] = None,
        use_ai: bool = True,
        max_bytes: int = MAX_LOG_FILE_BYTES,
    ) -> LogAnalysisReport:
        if log_text is None or not log_text.strip():
            raise ValueError("Log content is empty.")

        encoded_len = len(log_text.encode("utf-8"))
        if encoded_len > max_bytes:
            raise ValueError(
                f"Log text ({encoded_len:,} bytes) exceeds maximum limit of {max_bytes:,} bytes."
            )

        lines = [ln for ln in log_text.splitlines() if ln.strip()]
        err_cnt = 0
        warn_cnt = 0
        auth_cnt = 0
        timestamps: List[str] = []

        for ln in lines:
            ts = self.TIMESTAMP_REGEX.search(ln)
            if ts:
                timestamps.append(ts.group(1))
            if self.ERROR_REGEX.search(ln):
                err_cnt += 1
            if self.WARNING_REGEX.search(ln):
                warn_cnt += 1
            if self.AUTH_FAIL_REGEX.search(ln):
                auth_cnt += 1

        notable: List[str] = []
        explanations: List[str] = []
        steps: List[str] = []

        if auth_cnt > 0:
            notable.append(f"Found {auth_cnt} authentication failure event(s).")
            explanations.append(
                "Authentication failures can result from mistyped user passwords, stale automation keys, or automated SSH login probes."
            )
            steps.append(
                "Review source IPs and usernames in `/var/log/auth.log` or `journalctl -u ssh`, and ensure key-based SSH authentication is enforced."
            )
        if err_cnt > 0:
            notable.append(f"Found {err_cnt} error/critical event line(s).")
            explanations.append(
                "Error events typically indicate service configuration issues, permission denials, disk capacity exhaustion, or network timeouts."
            )
            steps.append(
                "Check unit status via `systemctl status <service>` and verify disk space with `df -h`."
            )
        if warn_cnt > 0:
            notable.append(f"Found {warn_cnt} warning event line(s).")

        if not notable:
            notable.append("No high-severity error or authentication failure patterns matched.")
            explanations.append("Log excerpt appears to reflect routine operational messages.")
            steps.append("Continue normal log monitoring and rotation.")

        ai_summary = ""
        if use_ai and self.provider is not None and config is not None and config.model:
            try:
                excerpt = "\n".join(lines[:60])
                sys_prompt = build_system_prompt(
                    config,
                    task_instructions=(
                        "Summarize this log excerpt defensively for a Linux administrator. "
                        "Highlight notable patterns, likely benign causes vs. security concerns, and read-only verification steps. "
                        "Do not claim uncertain findings are confirmed attacks."
                    ),
                )
                resp = self.provider.generate_chat(
                    messages=[{"role": "user", "content": f"Analyze log:\n{excerpt}"}],
                    model=config.model,
                    system_prompt=sys_prompt,
                    temperature=0.3,
                )
                ai_summary = resp.content.strip()
            except AIProviderError:
                ai_summary = ""

        return LogAnalysisReport(
            file_path=source_name,
            line_count=len(lines),
            error_count=err_cnt,
            warning_count=warn_cnt,
            auth_failure_count=auth_cnt,
            first_timestamp=timestamps[0] if timestamps else None,
            last_timestamp=timestamps[-1] if timestamps else None,
            notable_patterns=notable,
            possible_explanations=explanations,
            investigation_steps=steps,
            ai_summary=ai_summary,
        )
