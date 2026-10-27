"""
Command Router for SoulShell Terminal (Section 7).
Routes built-in commands across General, System, Linux Assistance, Network,
Security, and Ghost Stories categories, provides fuzzy command suggestions
on typos, and optionally delegates conversational queries to the AI assistant.
"""

from __future__ import annotations

import difflib
import shlex
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from soulshell.core.config import SoulConfig
from soulshell.core.terminal_ui import TerminalUI


@dataclass
class CommandContext:
    """Runtime context passed to every command handler."""

    config: SoulConfig
    ui: TerminalUI
    db: Any
    ai_provider: Any
    conversation_service: Any
    router: "CommandRouter"
    raw_line: str = ""
    args: List[str] = field(default_factory=list)
    arg_text: str = ""
    should_exit: bool = False
    last_story: Optional[Dict[str, str]] = None


CommandHandler = Callable[[CommandContext], Optional[int]]


@dataclass
class CommandSpec:
    """Metadata and callback for a registered CLI command."""

    name: str
    category: str
    usage: str
    description: str
    handler: CommandHandler
    aliases: List[str] = field(default_factory=list)


class CommandRouter:
    """Extensible command registry and dispatcher with typo suggestions."""

    def __init__(self) -> None:
        self._commands: Dict[str, CommandSpec] = {}
        self._aliases: Dict[str, str] = {}
        self._fallback_chat_handler: Optional[CommandHandler] = None

    def register(
        self,
        name: str,
        category: str,
        usage: str,
        description: str,
        handler: CommandHandler,
        aliases: Optional[List[str]] = None,
    ) -> None:
        clean_name = name.strip().lower()
        spec = CommandSpec(
            name=clean_name,
            category=category,
            usage=usage,
            description=description,
            handler=handler,
            aliases=[a.strip().lower() for a in (aliases or [])],
        )
        self._commands[clean_name] = spec
        for alias in spec.aliases:
            self._aliases[alias] = clean_name

    def set_fallback_chat_handler(self, handler: CommandHandler) -> None:
        """Set optional handler for natural-language chat when input is not a built-in command."""
        self._fallback_chat_handler = handler

    def resolve_command(self, token: str) -> Optional[CommandSpec]:
        key = (token or "").strip().lower()
        if key in self._commands:
            return self._commands[key]
        if key in self._aliases:
            return self._commands.get(self._aliases[key])
        return None

    def list_commands(self) -> List[CommandSpec]:
        return list(self._commands.values())

    def get_completion_candidates(self) -> List[str]:
        return sorted(set(list(self._commands.keys()) + list(self._aliases.keys())))

    def suggest_similar(self, unknown_cmd: str) -> List[str]:
        all_names = self.get_completion_candidates()
        return difflib.get_close_matches(unknown_cmd.lower(), all_names, n=3, cutoff=0.5)

    def dispatch(
        self,
        raw_line: str,
        context: CommandContext,
        allow_chat_fallback: bool = False,
    ) -> int:
        """
        Parse and execute a command line.
        Returns 0 on success, non-zero status code on error or unknown command.
        """
        line = (raw_line or "").strip()
        if not line:
            return 0

        try:
            tokens = shlex.split(line)
        except ValueError:
            # Handle unbalanced quotes gracefully
            tokens = line.split()

        cmd_token = tokens[0].lower()
        args = tokens[1:]
        arg_text = line[len(tokens[0]) :].strip()

        context.raw_line = line
        context.args = args
        context.arg_text = arg_text

        spec = self.resolve_command(cmd_token)
        if spec is not None:
            try:
                result = spec.handler(context)
                return int(result) if result is not None else 0
            except KeyboardInterrupt:
                context.ui.print_warning("Command interrupted (Ctrl+C).")
                return 130
            except Exception as exc:
                context.ui.print_error(
                    f"Command '{spec.name}' encountered an error: {exc}",
                    hint=f"Check usage: {spec.usage}",
                )
                return 1

        # Unknown command handling
        similar = self.suggest_similar(cmd_token)
        if allow_chat_fallback and self._fallback_chat_handler is not None and len(tokens) >= 3:
            return int(self._fallback_chat_handler(context) or 0)

        hint_msg = "Type 'help' to view all available SoulShell Terminal commands."
        if similar:
            hint_msg = f"Did you mean: {', '.join(similar)}? ({hint_msg})"
        if len(tokens) >= 2:
            hint_msg += " Or prefix with 'ask <question>' / 'suggest <task>' to query the AI."

        context.ui.print_error(
            f"Unknown command: '{cmd_token}'",
            hint=hint_msg,
        )
        return 127
