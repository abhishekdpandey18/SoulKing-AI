"""Core terminal infrastructure for SoulShell Terminal."""
from soulshell.core.command_router import CommandContext, CommandRouter, CommandSpec
from soulshell.core.config import (
    APP_NAME,
    ORIGINAL_PROJECT,
    VERSION,
    SoulConfig,
    get_default_config_path,
    get_default_db_path,
    load_config,
    save_config,
)
from soulshell.core.terminal_ui import TerminalUI

__all__ = [
    "APP_NAME",
    "ORIGINAL_PROJECT",
    "VERSION",
    "SoulConfig",
    "get_default_config_path",
    "get_default_db_path",
    "load_config",
    "save_config",
    "CommandContext",
    "CommandRouter",
    "CommandSpec",
    "TerminalUI",
]
