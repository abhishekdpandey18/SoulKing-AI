"""
Application Entry Point for SoulKing (Sections 4, 7, 18).
100% terminal-based CLI application (zero GUI dependencies).
Supports:
- Interactive REPL (`soulking` or `python main.py`)
- Direct single-command execution (`python main.py help`, `python main.py -c "risk rm -rf /tmp/x"`)
- Flags: `--version`, `--no-anim`, `--plain`, `--mode <soulking|developer|ghost>`, `--model <name>`, `--config <path>`
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List, Optional

from soulshell.cli import SoulShellCLI
from soulshell.core.config import (
    APP_NAME,
    ORIGINAL_PROJECT,
    VERSION,
    load_config,
    normalize_mode_name,
)
from soulshell.utils.logging_config import setup_logging


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="soulking",
        description=(
            f"{APP_NAME} v{VERSION} (Upgraded from {ORIGINAL_PROJECT}) — "
            "Haunted AI-Powered Linux Terminal Assistant."
        ),
    )
    parser.add_argument(
        "-v",
        "--version",
        action="version",
        version=f"{APP_NAME} v{VERSION}",
    )
    parser.add_argument(
        "--config",
        metavar="PATH",
        help="Path to a custom TOML configuration file (default: ~/.config/soulking/config.toml).",
    )
    parser.add_argument(
        "--mode",
        choices=["soulking", "developer", "ghost"],
        help="Override starting AI personality mode.",
    )
    parser.add_argument(
        "--model",
        metavar="MODEL",
        help="Override selected local Ollama model name.",
    )
    parser.add_argument(
        "--ollama-url",
        metavar="URL",
        help="Override local Ollama base URL (default: http://127.0.0.1:11434).",
    )
    parser.add_argument(
        "--no-anim",
        action="store_true",
        help="Disable startup animations for this session.",
    )
    parser.add_argument(
        "--plain",
        action="store_true",
        help="Use plain, non-animated terminal theme without Unicode decorations.",
    )
    parser.add_argument(
        "-c",
        "--command",
        metavar="CMD",
        help="Execute a single SoulKing command and exit (e.g. -c 'risk rm -rf /tmp/test').",
    )
    parser.add_argument(
        "inline_command",
        nargs="*",
        help="Optional inline command to execute immediately (e.g. `python main.py status`).",
    )
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args_list = list(sys.argv[1:] if argv is None else argv)
    parser = build_arg_parser()
    parsed = parser.parse_args(args_list)

    cfg_path = Path(parsed.config).expanduser() if parsed.config else None
    try:
        config = load_config(cfg_path)
    except Exception:
        from soulshell.core.config import SoulConfig

        config = SoulConfig()

    if parsed.mode:
        config.personality_mode = normalize_mode_name(parsed.mode)
    if parsed.model:
        config.model = parsed.model.strip()
    if parsed.ollama_url:
        config.ollama_url = parsed.ollama_url.strip()
    if parsed.no_anim:
        config.animations = False
    if parsed.plain:
        config.theme = "plain"
        config.animations = False

    config.validate()
    setup_logging(log_level=config.log_level)

    cli = SoulShellCLI(config=config)

    if parsed.command:
        return cli.execute_command(parsed.command)
    if parsed.inline_command:
        cmd_line = " ".join(parsed.inline_command)
        return cli.execute_command(cmd_line)

    return cli.run_interactive_loop(show_banner=True)


if __name__ == "__main__":
    sys.exit(main())
