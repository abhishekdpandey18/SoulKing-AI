"""CLI command modules for SoulShell Terminal."""
from soulshell.commands.ai import register_ai_commands
from soulshell.commands.general import register_general_commands
from soulshell.commands.network import register_network_commands
from soulshell.commands.security import register_security_commands
from soulshell.commands.stories import register_story_commands
from soulshell.commands.system import register_system_commands
from soulshell.core.command_router import CommandRouter


def register_all_commands(router: CommandRouter) -> None:
    """Register all 6 command categories onto the CommandRouter."""
    register_general_commands(router)
    register_system_commands(router)
    register_ai_commands(router)
    register_network_commands(router)
    register_security_commands(router)
    register_story_commands(router)


__all__ = [
    "register_all_commands",
    "register_general_commands",
    "register_system_commands",
    "register_ai_commands",
    "register_network_commands",
    "register_security_commands",
    "register_story_commands",
]
