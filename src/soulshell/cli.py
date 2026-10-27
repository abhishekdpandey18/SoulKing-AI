"""
Interactive Terminal Session & CLI Controller for SoulShell Terminal (Sections 4, 7, 13, 15).
Features:
- Persistent readline command history & tab completion
- Graceful handling of Ctrl+C (KeyboardInterrupt) and Ctrl+D (EOFError)
- Non-animated / plain terminal mode support (`--no-anim` / `--plain`)
- Single-command execution mode (`soulshell -c "sysinfo"` or `python main.py help`)
- Interactive haunted REPL loop (`soul@ghost:~ $`)
"""

from __future__ import annotations

import atexit
from pathlib import Path
from typing import List, Optional

from rich.console import Console

from soulshell.ai.ollama_provider import (
    AIProvider,
    ConversationService,
    OllamaProvider,
)
from soulshell.commands import register_all_commands
from soulshell.commands.ai import cmd_ask
from soulshell.core.command_router import CommandContext, CommandRouter
from soulshell.core.config import (
    SoulConfig,
    get_default_data_dir,
    load_config,
)
from soulshell.core.terminal_ui import TerminalUI
from soulshell.database.db import DatabaseManager


class SoulShellCLI:
    """Main terminal controller and interactive REPL for SoulShell Terminal."""

    def __init__(
        self,
        config: Optional[SoulConfig] = None,
        db: Optional[DatabaseManager] = None,
        ai_provider: Optional[AIProvider] = None,
        console: Optional[Console] = None,
    ) -> None:
        base_cfg = config or load_config()
        self.db = db or DatabaseManager()
        # Synchronize saved preferences from SQLite if present, while honoring explicit config overrides
        if config is None:
            self.config = self.db.load_preferences(base_cfg)
        else:
            self.config = base_cfg.validate()

        self.ui = TerminalUI(config=self.config, console=console)
        self.ai_provider = ai_provider or OllamaProvider(
            base_url=self.config.ollama_url,
            timeout=self.config.request_timeout,
        )
        self.conversation_service = ConversationService(
            db=self.db,
            provider=self.ai_provider,
            config=self.config,
        )
        self.router = CommandRouter()
        register_all_commands(self.router)
        self.router.set_fallback_chat_handler(cmd_ask)

        self.context = CommandContext(
            config=self.config,
            ui=self.ui,
            db=self.db,
            ai_provider=self.ai_provider,
            conversation_service=self.conversation_service,
            router=self.router,
        )

    def _setup_readline(self) -> None:
        """Configure readline tab completion and persistent command history if supported."""
        try:
            import readline

            candidates = self.router.get_completion_candidates()

            def _completer(text: str, state: int) -> Optional[str]:
                matches = [c for c in candidates if c.startswith(text.lower())]
                return matches[state] if state < len(matches) else None

            readline.set_completer(_completer)
            readline.parse_and_bind("tab: complete")

            if self.config.save_history:
                hist_file = get_default_data_dir() / "readline_history.txt"
                if hist_file.exists():
                    try:
                        readline.read_history_file(str(hist_file))
                    except OSError:
                        pass
                readline.set_history_length(500)
                atexit.register(self._save_readline_history, readline, hist_file)
        except Exception:
            pass

    @staticmethod
    def _save_readline_history(readline_mod: object, hist_file: Path) -> None:
        try:
            hist_file.parent.mkdir(parents=True, exist_ok=True)
            getattr(readline_mod, "write_history_file")(str(hist_file))
        except Exception:
            pass

    def show_startup(self, animate: bool = True) -> None:
        """Render the haunted terminal startup screen."""
        status = self.ai_provider.check_status(selected_model=self.config.model)
        db_health = self.db.check_health()
        self.ui.render_startup_screen(
            ai_online=status.runtime_available,
            selected_model=status.selected_model or self.config.model,
            model_ready=status.selected_model_available,
            db_healthy=bool(db_health.get("healthy", True)),
            animate=animate,
        )

    def execute_command(
        self, line: str, allow_chat_fallback: bool = False
    ) -> int:
        """Execute a single command string through the CommandRouter."""
        return self.router.dispatch(
            line, self.context, allow_chat_fallback=allow_chat_fallback
        )

    def run_interactive_loop(self, show_banner: bool = True) -> int:
        """Run the interactive SoulShell Terminal REPL loop."""
        self._setup_readline()
        if show_banner:
            self.show_startup(animate=self.config.animations)

        while not self.context.should_exit:
            try:
                prompt = self.ui.get_prompt_string()
                line = input(prompt)
            except KeyboardInterrupt:
                # Ctrl+C: cancel current input line without crashing
                self.ui.console.print(
                    "\n[dim]^C (Interrupted — type 'exit' or press Ctrl+D to quit)[/dim]"
                )
                continue
            except EOFError:
                # Ctrl+D: graceful exit
                self.ui.console.print()
                self.execute_command("exit")
                break

            if not line.strip():
                continue

            self.execute_command(line, allow_chat_fallback=False)

        return 0
