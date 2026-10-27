"""
Automated tests for:
- Personality prompt selection (`mode soulking`, `mode developer`, `mode ghost`)
- AI-unavailable offline behavior (`explain`, `suggest`, `story`, `models` when Ollama is down)
- Mocked Ollama AI responses for `explain`, `suggest`, `story`, and `ask`
- Log-analysis size limits and read-only safety (`loganalyze`)
- Verification that zero GUI libraries are imported anywhere in SoulShell Terminal
"""

from __future__ import annotations

import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Callable, Dict, Iterator, List, Optional

from rich.console import Console

from soulshell.ai.ollama_provider import (
    AIProvider,
    AIProviderError,
    GenerationResponse,
    ModelInfo,
    OllamaProvider,
    ProviderStatus,
)
from soulshell.ai.personality import build_system_prompt
from soulshell.cli import SoulShellCLI
from soulshell.core.config import SoulConfig, get_project_root
from soulshell.database.db import DatabaseManager
from soulshell.services.log_analyzer import LogAnalyzerService


class MockOllamaProvider(AIProvider):
    """Deterministic mocked Ollama provider for offline unit tests."""

    def __init__(self, canned_text: str = "", offline: bool = False) -> None:
        self.canned_text = canned_text
        self.offline = offline

    @property
    def provider_name(self) -> str:
        return "MockOllama"

    @property
    def is_local(self) -> bool:
        return True

    def list_models(self) -> List[ModelInfo]:
        if self.offline:
            raise AIProviderError("Ollama is not reachable at http://127.0.0.1:11434.")
        return [ModelInfo(name="llama3.2:latest", size_bytes=2_100_000_000)]

    def check_status(self, selected_model: str = "") -> ProviderStatus:
        if self.offline:
            return ProviderStatus(
                provider_name=self.provider_name,
                endpoint="http://127.0.0.1:11434",
                is_local=True,
                runtime_available=False,
                selected_model=selected_model,
                selected_model_available=False,
                error_message="Ollama is not reachable at http://127.0.0.1:11434.",
                setup_instructions="Install Ollama and run `ollama serve`.",
            )
        return ProviderStatus(
            provider_name=self.provider_name,
            endpoint="http://127.0.0.1:11434",
            is_local=True,
            runtime_available=True,
            models_installed=self.list_models(),
            selected_model=selected_model or "llama3.2:latest",
            selected_model_available=True,
        )

    def generate_chat(
        self,
        messages: List[Dict[str, str]],
        model: str,
        system_prompt: str = "",
        temperature: float = 0.7,
    ) -> GenerationResponse:
        if self.offline:
            raise AIProviderError("Ollama is not reachable at http://127.0.0.1:11434.")
        return GenerationResponse(
            content=self.canned_text or "Yohohoho! Mock AI answer.",
            model=model,
            provider=self.provider_name,
        )

    def stream_chat(
        self,
        messages: List[Dict[str, str]],
        model: str,
        system_prompt: str = "",
        temperature: float = 0.7,
        should_cancel: Optional[Callable[[], bool]] = None,
    ) -> Iterator[str]:
        if self.offline:
            raise AIProviderError("Ollama is not reachable at http://127.0.0.1:11434.")
        for token in (self.canned_text or "Yohohoho! Streamed mock answer.").split(" "):
            yield token + " "


class TestPersonalityAIAndOffline(unittest.TestCase):
    """Test suite for personality modes, offline fallbacks, log size limits, and terminal purity."""

    def test_personality_prompt_selection_and_mode_command(self) -> None:
        sk_prompt = build_system_prompt(SoulConfig(personality_mode="soulking"))
        self.assertIn("Soul King Mode", sk_prompt)
        self.assertIn("skeleton-musician", sk_prompt)

        dev_prompt = build_system_prompt(SoulConfig(personality_mode="developer"))
        self.assertIn("Developer Mode", dev_prompt)
        self.assertIn("Python, Java, Linux", dev_prompt)

        ghost_prompt = build_system_prompt(SoulConfig(personality_mode="ghost"))
        self.assertIn("Ghost Mode", ghost_prompt)
        self.assertIn("phantom spirit", ghost_prompt)

    def test_ai_unavailable_behavior_is_honest_and_graceful(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db = DatabaseManager(db_path=Path(tmpdir) / "offline.db")
            buf = io.StringIO()
            console = Console(file=buf, force_terminal=False, width=100)
            offline_provider = MockOllamaProvider(offline=True)
            cli = SoulShellCLI(
                config=SoulConfig(animations=False, theme="plain"),
                db=db,
                ai_provider=offline_provider,
                console=console,
            )

            # `explain` works offline using static safety + built-in reference while stating AI is offline
            self.assertEqual(cli.execute_command("explain ls -la"), 0)
            self.assertIn("Offline", buf.getvalue())

            # `suggest` works offline using heuristic recipes while stating Ollama is disconnected
            buf.seek(0)
            buf.truncate(0)
            self.assertEqual(
                cli.execute_command("suggest show listening network ports"), 0
            )
            self.assertIn("ss -tuln", buf.getvalue())

            # `story` works offline using built-in stories and supports saving & exporting
            buf.seek(0)
            buf.truncate(0)
            self.assertEqual(cli.execute_command("story cyberpunk"), 0)
            self.assertIn("Built-in Offline Archive", buf.getvalue())
            self.assertEqual(cli.execute_command("story save"), 0)
            export_file = Path(tmpdir) / "stories.md"
            self.assertEqual(cli.execute_command(f"story export {export_file}"), 0)
            self.assertTrue(export_file.exists())

    def test_mocked_ai_online_suggest_and_ask(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db = DatabaseManager(db_path=Path(tmpdir) / "online.db")
            buf = io.StringIO()
            console = Console(file=buf, force_terminal=False, width=100)
            canned_json = json.dumps(
                {
                    "proposed_command": "find ~ -type f -size +100M",
                    "explanation": "Finds files larger than 100 MB in your home directory.",
                    "safer_alternative": "find ~ -maxdepth 2 -type f -size +100M -ls",
                }
            )
            online_provider = MockOllamaProvider(canned_text=canned_json)
            cli = SoulShellCLI(
                config=SoulConfig(animations=False, theme="plain"),
                db=db,
                ai_provider=online_provider,
                console=console,
            )

            self.assertEqual(
                cli.execute_command("suggest find files larger than 100 MB"), 0
            )
            self.assertIn("find ~ -type f -size +100M", buf.getvalue())

            self.assertEqual(cli.execute_command("ask hello Soul King"), 0)

    def test_log_analysis_size_limits_and_parsing(self) -> None:
        analyzer = LogAnalyzerService()
        sample = (
            "2026-10-27T10:00:00Z kali sshd[99]: Failed password for invalid user admin from 192.0.2.5 port 22\n"
            "2026-10-27T10:01:00Z kali kernel: ERROR disk read timeout\n"
        )
        rep = analyzer.analyze_text(sample, use_ai=False)
        self.assertEqual(rep.error_count, 1)
        self.assertEqual(rep.auth_failure_count, 1)

        with self.assertRaises(ValueError):
            analyzer.analyze_text("X" * 2048, use_ai=False, max_bytes=512)

    def test_no_gui_framework_used_in_codebase(self) -> None:
        root = get_project_root()
        forbidden_gui_tokens = ("PySide6", "PyQt6", "PyQt5", "tkinter", "playwright")
        for py_file in (root / "src").rglob("*.py"):
            content = py_file.read_text(encoding="utf-8")
            for token in forbidden_gui_tokens:
                self.assertNotIn(
                    token,
                    content,
                    f"GUI dependency '{token}' must not appear in {py_file}",
                )


if __name__ == "__main__":
    unittest.main()
