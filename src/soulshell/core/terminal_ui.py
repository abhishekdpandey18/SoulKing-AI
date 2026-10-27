"""
Rich-powered Terminal UI & Startup Experience for SoulKing (Sections 4 & 13).
Provides:
- Haunted purple (#9B5DE5 / magenta) and ghost cyan (#4CC9F0 / cyan) color themes
- Plain / non-animated / ASCII-safe fallback mode
- Terminal-width-aware startup banner & status dashboard
- Animated startup sequence (skippable / configurable via `animations = false` or `--no-anim`)
- Current username, hostname, OS/Python version, current time, AI status, selected model, and Soul King greeting
- Interactive prompt formatting (`soul@ghost:~ $`)
"""

from __future__ import annotations

import getpass
import platform
import socket
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text
from rich.theme import Theme

from soulshell.core.config import (
    APP_NAME,
    ORIGINAL_PROJECT,
    VERSION,
    SoulConfig,
    get_assets_dir,
)

THEME_STYLES: Dict[str, Dict[str, str]] = {
    "soulking": {
        "primary": "bold bright_magenta",
        "secondary": "bright_cyan",
        "accent": "bold bright_green",
        "warning": "bold yellow",
        "error": "bold bright_red",
        "muted": "dim white",
        "border": "bright_magenta",
        "panel_border": "cyan",
    },
    "cyberpunk": {
        "primary": "bold bright_yellow",
        "secondary": "bright_magenta",
        "accent": "bold bright_cyan",
        "warning": "bold yellow",
        "error": "bold red",
        "muted": "dim cyan",
        "border": "bright_yellow",
        "panel_border": "bright_magenta",
    },
    "phantom": {
        "primary": "bold bright_cyan",
        "secondary": "magenta",
        "accent": "bold green",
        "warning": "bold yellow",
        "error": "bold red",
        "muted": "dim white",
        "border": "bright_cyan",
        "panel_border": "magenta",
    },
    "plain": {
        "primary": "bold",
        "secondary": "default",
        "accent": "bold",
        "warning": "bold",
        "error": "bold",
        "muted": "default",
        "border": "white",
        "panel_border": "white",
    },
}

COMPACT_ASCII_BANNER = r"""
  ____              _ _  ___             
 / ___|  ___  _   _| | |/ (_)_ __   __ _ 
 \___ \ / _ \| | | | | ' /| | '_ \ / _` |
  ___) | (_) | |_| | | . \| | | | | (_| |
 |____/ \___/ \__,_|_|_|\_\_|_| |_|\__, |
                                   |___/ 
       SOULKING'S HAUNTED TERMINAL
         "Yohohoho! Welcome!"
"""

SOUL_KING_GREETINGS = {
    "soulking": "Yohohoho! Welcome to SoulKing's haunted terminal! May I see your shell history? Ah—just a skeleton joke! 💀🎸",
    "developer": "SoulKing Developer Mode active. Ready for Linux diagnostics, code analysis, and safe shell workflows. ⚡",
    "ghost": "The terminal candles flicker... SoulKing's phantom spirit listens between your keystrokes. Speak your command... 👻🕯️",
}


class TerminalUI:
    """Rich terminal renderer with width awareness, theme support, and graceful ASCII fallbacks."""

    def __init__(
        self,
        config: SoulConfig,
        console: Optional[Console] = None,
    ) -> None:
        self.config = config
        self.console = console or Console(
            theme=Theme(self.styles),
            highlight=False,
        )

    @property
    def styles(self) -> Dict[str, str]:
        return THEME_STYLES.get(self.config.theme, THEME_STYLES["soulking"])

    @property
    def unicode_supported(self) -> bool:
        if self.config.theme == "plain":
            return False
        encoding = (getattr(sys.stdout, "encoding", "") or "utf-8").lower()
        return "utf" in encoding

    def load_banner_art(self) -> str:
        """Load SOULKING ASCII banner from assets/banner.txt or fall back to compact banner on narrow terminals."""
        width = self.console.size.width or 80
        banner_path = get_assets_dir() / "banner.txt"
        if width >= 72 and self.unicode_supported and banner_path.exists():
            try:
                return banner_path.read_text(encoding="utf-8").rstrip("\n")
            except OSError:
                pass
        return COMPACT_ASCII_BANNER.strip("\n")

    def run_startup_animation(self) -> None:
        """Play a brief, non-blocking startup sequence if animations are enabled."""
        if not self.config.animations or self.config.theme == "plain":
            return
        steps = [
            " Tuning SoulKing's violin strings...",
            " Awakening local SQLite phantom memory...",
            " Probing local Ollama spirit nexus...",
        ]
        try:
            with Progress(
                SpinnerColumn(style=self.styles["secondary"]),
                TextColumn("[bright_magenta]{task.description}[/bright_magenta]"),
                console=self.console,
                transient=True,
            ) as progress:
                task = progress.add_task(steps[0], total=len(steps))
                for step in steps:
                    progress.update(task, description=step)
                    time.sleep(0.08)
                    progress.advance(task)
        except Exception:
            pass

    def render_startup_screen(
        self,
        ai_online: bool,
        selected_model: str,
        model_ready: bool,
        db_healthy: bool,
        animate: bool = True,
    ) -> None:
        """Render the complete Section 4 Haunted Terminal Startup Screen."""
        if animate and self.config.animations:
            self.run_startup_animation()

        banner_art = self.load_banner_art()
        self.console.print(
            Text(banner_art, style=self.styles["primary"]),
        )

        try:
            username = getpass.getuser()
        except Exception:
            username = "soul"
        try:
            hostname = socket.gethostname()
        except Exception:
            hostname = "ghost"

        os_info = f"{platform.system()} {platform.release()} ({platform.machine()})"
        py_ver = sys.version.split()[0]
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        mode_name = self.config.personality_mode.upper()

        if ai_online and model_ready:
            ai_status_str = f"[bold bright_green]ONLINE[/bold bright_green] ({self.config.ollama_url})"
            model_str = f"[bright_cyan]{selected_model}[/bright_cyan] (Ready)"
        elif ai_online:
            ai_status_str = f"[bold yellow]ONLINE (Model Missing)[/bold yellow] ({self.config.ollama_url})"
            model_str = f"[yellow]{selected_model} (Run `ollama pull {selected_model}`)[/yellow]"
        else:
            ai_status_str = f"[bold bright_red]OFFLINE[/bold bright_red] ({self.config.ollama_url} unreachable)"
            model_str = f"[dim]{selected_model} (Start `ollama serve` for AI)[/dim]"

        db_str = (
            "[bold bright_green]Local SQLite memory initialized[/bold bright_green]"
            if db_healthy
            else "[bold bright_red]Database fallback active[/bold bright_red]"
        )

        grid = Table.grid(padding=(0, 2))
        grid.add_column(style=self.styles["secondary"], justify="right")
        grid.add_column(style="white")

        grid.add_row("[USER]", f"{username}@{hostname}")
        grid.add_row("[SYS]", f"{os_info} | Python {py_ver}")
        grid.add_row("[TIME]", now_str)
        grid.add_row("[MODE]", f"{mode_name} | Theme: {self.config.theme}")
        grid.add_row("[AI]", f"{ai_status_str} | Model: {model_str}")
        grid.add_row("[DB]", db_str)

        greeting = SOUL_KING_GREETINGS.get(
            self.config.personality_mode, SOUL_KING_GREETINGS["soulking"]
        )

        self.console.print(
            Panel(
                grid,
                title=f"[{self.styles['primary']}]💀 {APP_NAME} v{VERSION} (Upgraded from {ORIGINAL_PROJECT})[/{self.styles['primary']}]",
                subtitle=f"[{self.styles['secondary']}]Type 'help' for commands or chat naturally[/{self.styles['secondary']}]",
                border_style=self.styles["border"],
                expand=False,
            )
        )
        self.console.print(
            Panel(
                f"[italic {self.styles['secondary']}]{greeting}[/italic {self.styles['secondary']}]",
                border_style=self.styles["panel_border"],
                expand=False,
            )
        )

    def get_prompt_string(self, cwd: Optional[Path] = None) -> str:
        """Return the haunted terminal prompt string (e.g., `soul@ghost:~ $ `)."""
        current = cwd or Path.cwd()
        try:
            home = Path.home()
            if current == home:
                short_dir = "~"
            elif home in current.parents:
                short_dir = "~/" + str(current.relative_to(home))
            else:
                short_dir = current.name or "/"
        except Exception:
            short_dir = "~"

        mode_tag = self.config.personality_mode
        if self.config.theme == "plain":
            return f"soul@ghost ({mode_tag}):{short_dir} $ "
        return f"\x1b[1;35msoul\x1b[0m@\x1b[1;36mghost\x1b[0m[\x1b[32m{mode_tag}\x1b[0m]:\x1b[1;34m{short_dir}\x1b[0m $ "

    def print_panel(
        self,
        content: Any,
        title: str = "",
        subtitle: str = "",
        border_style: Optional[str] = None,
    ) -> None:
        """Render a styled Rich panel."""
        style = border_style or self.styles["panel_border"]
        if isinstance(content, str) and (
            "```" in content or "#" in content or "**" in content
        ):
            renderable: Any = Markdown(content)
        else:
            renderable = content
        self.console.print(
            Panel(
                renderable,
                title=f"[{self.styles['primary']}]{title}[/{self.styles['primary']}]" if title else None,
                subtitle=subtitle or None,
                border_style=style,
            )
        )

    def print_code_panel(
        self,
        code: str,
        language: str = "bash",
        title: str = "Proposed Command",
    ) -> None:
        """Render a syntax-highlighted command or code snippet inside a Rich panel."""
        syntax = Syntax(
            code.strip(),
            language,
            theme="monokai",
            word_wrap=True,
            background_color="default",
        )
        self.console.print(
            Panel(
                syntax,
                title=f"[{self.styles['primary']}]{title}[/{self.styles['primary']}]",
                border_style=self.styles["border"],
            )
        )

    def print_error(self, message: str, hint: str = "") -> None:
        """Render a friendly, actionable error panel without raw Python tracebacks."""
        body = f"[{self.styles['error']}]Error:[/{self.styles['error']}] {message}"
        if hint:
            body += f"\n[{self.styles['secondary']}]Hint:[/{self.styles['secondary']}] {hint}"
        self.console.print(
            Panel(body, title="⚠️ SoulKing Terminal Alert", border_style="red")
        )

    def print_success(self, message: str) -> None:
        self.console.print(f"[{self.styles['accent']}]✔ {message}[/{self.styles['accent']}]")

    def print_warning(self, message: str) -> None:
        self.console.print(f"[{self.styles['warning']}]▲ {message}[/{self.styles['warning']}]")
