"""
General Commands for SoulShell Terminal (Sections 6, 7, 11, 12).
Commands:
- help [command]
- about
- version
- clear
- banner
- status
- config [show | set <key> <value> | reset | path]
- mode [soulking | developer | ghost]
- history [list | search <q> | view <id> | export <path> | clear [--yes]]
- favorites [list | add <cmd> | remove <id> [--yes]]
- exit / quit
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List

from rich.table import Table

from soulshell.ai.personality import SOUL_MODES
from soulshell.core.command_router import CommandContext, CommandRouter, CommandSpec
from soulshell.core.config import (
    APP_NAME,
    ORIGINAL_PROJECT,
    SECONDARY_TAGLINE,
    TAGLINE,
    VERSION,
    SoulConfig,
    get_default_config_path,
    normalize_mode_name,
    save_config,
)


def cmd_help(ctx: CommandContext) -> int:
    """Display categorized command reference or detailed help for a specific command."""
    if ctx.args:
        target = ctx.args[0].lower()
        spec = ctx.router.resolve_command(target)
        if spec is None:
            ctx.ui.print_error(f"No help entry found for '{target}'.")
            return 1
        aliases_str = ", ".join(spec.aliases) if spec.aliases else "None"
        body = (
            f"**Command:** `{spec.name}`\n"
            f"**Category:** {spec.category}\n"
            f"**Usage:** `{spec.usage}`\n"
            f"**Aliases:** {aliases_str}\n\n"
            f"{spec.description}"
        )
        ctx.ui.print_panel(body, title=f"📖 Help: {spec.name}")
        return 0

    by_category: Dict[str, List[CommandSpec]] = {}
    for spec in ctx.router.list_commands():
        by_category.setdefault(spec.category, []).append(spec)

    table = Table(
        title=f"💀🎸 {APP_NAME} v{VERSION} — Command Reference",
        border_style=ctx.ui.styles["border"],
        show_lines=False,
    )
    table.add_column("Category", style=ctx.ui.styles["primary"], width=18)
    table.add_column("Command / Usage", style=ctx.ui.styles["secondary"], width=30)
    table.add_column("Description", style="white")

    for category, specs in by_category.items():
        for idx, spec in enumerate(specs):
            cat_label = category if idx == 0 else ""
            table.add_row(cat_label, spec.usage, spec.description)

    ctx.ui.console.print(table)
    ctx.ui.console.print(
        f"[{ctx.ui.styles['muted']}]Tip: Type 'help <command>' for details, or use 'ask <prompt>' / 'suggest <task>' for AI help.[/{ctx.ui.styles['muted']}]"
    )
    return 0


def cmd_about(ctx: CommandContext) -> int:
    """Display project identity, lineage from Dark Impulse, and disclaimers."""
    text = (
        f"# 💀🎸 {APP_NAME} (v{VERSION})\n"
        f"**Original Project Lineage:** Upgraded from *{ORIGINAL_PROJECT}*\n"
        f"**Tagline:** *{TAGLINE}* — *{SECONDARY_TAGLINE}*\n\n"
        "### Overview\n"
        "SoulShell Terminal is a 100% terminal-based Linux AI assistant, system & network "
        "diagnostic suite, defensive cybersecurity toolkit, and haunted storyteller powered "
        "by Rich, SQLite, and local Ollama models.\n\n"
        "### Unofficial Fan-Inspired Disclaimer\n"
        "Inspired by the skeleton-musician spirit of Brook from *One Piece*. This is an "
        "independent open-source CLI project and is not affiliated with or endorsed by "
        "One Piece's rights holders."
    )
    ctx.ui.print_panel(text, title=f"About {APP_NAME}")
    return 0


def cmd_version(ctx: CommandContext) -> int:
    """Print application version."""
    ctx.ui.console.print(
        f"[{ctx.ui.styles['primary']}]{APP_NAME} v{VERSION}[/{ctx.ui.styles['primary']}] "
        f"([dim]Upgraded from {ORIGINAL_PROJECT}[/dim])"
    )
    return 0


def cmd_clear(ctx: CommandContext) -> int:
    """Clear the terminal screen."""
    ctx.ui.console.clear()
    return 0


def cmd_banner(ctx: CommandContext) -> int:
    """Render the SoulShell Terminal startup banner and system status."""
    status = ctx.ai_provider.check_status(selected_model=ctx.config.model)
    db_health = ctx.db.check_health()
    ctx.ui.render_startup_screen(
        ai_online=status.runtime_available,
        selected_model=status.selected_model or ctx.config.model,
        model_ready=status.selected_model_available,
        db_healthy=bool(db_health.get("healthy", True)),
        animate=False,
    )
    return 0


def cmd_status(ctx: CommandContext) -> int:
    """Display live status of AI backend, selected model, configuration, and SQLite database."""
    ai_status = ctx.ai_provider.check_status(selected_model=ctx.config.model)
    db_health = ctx.db.check_health()

    table = Table(
        title="🔮 SoulShell Terminal — Live System & AI Status",
        border_style=ctx.ui.styles["border"],
    )
    table.add_column("Subsystem", style=ctx.ui.styles["secondary"])
    table.add_column("Status / Value", style="white")

    table.add_row("Application", f"{APP_NAME} v{VERSION}")
    table.add_row("Personality Mode", f"{ctx.config.personality_mode.upper()}")
    table.add_row("Theme / Animations", f"{ctx.config.theme} (Animations: {ctx.config.animations})")
    table.add_row("Ollama Endpoint", f"{ai_status.endpoint} (Local: {ai_status.is_local})")
    table.add_row(
        "Ollama Server",
        "[bold green]ONLINE[/bold green]" if ai_status.runtime_available else "[bold red]OFFLINE[/bold red]",
    )
    table.add_row(
        "Selected Model",
        f"{ctx.config.model} ({'Installed' if ai_status.selected_model_available else 'Not Installed'})",
    )
    installed_str = (
        ", ".join(m.name for m in ai_status.models_installed)
        if ai_status.models_installed
        else "None detected"
    )
    table.add_row("Installed Models", installed_str)
    table.add_row(
        "SQLite Memory",
        f"{'Healthy' if db_health.get('healthy') else 'Error'} ({db_health.get('db_path')})",
    )
    table.add_row(
        "History Saving",
        f"{'Enabled' if ctx.config.save_history else 'Disabled (Privacy Mode)'} "
        f"(Conversations: {db_health.get('conversations', 0)}, Favorites: {db_health.get('favorite_commands', 0)})",
    )
    ctx.ui.console.print(table)
    if ai_status.error_message:
        ctx.ui.print_warning(ai_status.error_message)
    if ai_status.setup_instructions and not ai_status.runtime_available:
        ctx.ui.print_panel(ai_status.setup_instructions, title="⚙️ Local AI Setup Guide")
    return 0


def cmd_mode(ctx: CommandContext) -> int:
    """View or switch AI personality mode (`mode`, `mode soulking`, `mode developer`, `mode ghost`)."""
    if not ctx.args:
        current = SOUL_MODES.get(ctx.config.personality_mode, SOUL_MODES["soulking"])
        lines = [
            f"**Current Personality Mode:** {current.badge} (`{current.key}`)",
            f"*{current.tagline}*\n",
            "**Available Modes:**",
            "- `mode soulking` — Friendly, humorous, theatrical skeleton-musician companion",
            "- `mode developer` — Focused engineering mode for Python, Java, Linux, Git, and debugging",
            "- `mode ghost` — Mysterious, spooky responses and haunted terminal lore",
        ]
        ctx.ui.print_panel("\n".join(lines), title="🎭 AI Personality Modes")
        return 0

    requested = normalize_mode_name(ctx.args[0])
    if requested not in SOUL_MODES:
        ctx.ui.print_error(
            f"Unknown personality mode '{ctx.args[0]}'.",
            hint="Valid modes: `mode soulking`, `mode developer`, `mode ghost`.",
        )
        return 1

    meta = ctx.conversation_service.personality.set_mode(requested)
    ctx.config.personality_mode = meta.key
    save_config(ctx.config)
    ctx.db.save_preferences(ctx.config)
    ctx.ui.print_panel(
        f"**Switched to {meta.title} ({meta.badge})**\n\n*{meta.greeting}*",
        title="🎭 Personality Updated",
    )
    return 0


def cmd_config(ctx: CommandContext) -> int:
    """View or update SoulShell Terminal configuration (`~/.config/soulshell/config.toml`)."""
    sub = ctx.args[0].lower() if ctx.args else "show"

    if sub in ("show", "list"):
        table = Table(
            title=f"⚙️ Configuration ({get_default_config_path()})",
            border_style=ctx.ui.styles["border"],
        )
        table.add_column("Setting Key", style=ctx.ui.styles["secondary"])
        table.add_column("Current Value", style="white")
        for k, v in ctx.config.to_dict().items():
            table.add_row(k, str(v))
        ctx.ui.console.print(table)
        ctx.ui.console.print(
            "[dim]Usage: `config set <key> <value>` | `config reset --yes` | `config path`[/dim]"
        )
        return 0

    if sub == "path":
        ctx.ui.console.print(f"Config path: {get_default_config_path()}")
        return 0

    if sub == "reset":
        if "--yes" not in ctx.args:
            ctx.ui.print_warning(
                "To reset configuration to defaults, run: `config reset --yes`"
            )
            return 1
        fresh = SoulConfig().validate()
        for k, v in fresh.to_dict().items():
            setattr(ctx.config, k, v)
        save_config(ctx.config)
        ctx.db.save_preferences(ctx.config)
        ctx.conversation_service.update_config(ctx.config)
        ctx.ui.print_success("Configuration reset to factory defaults.")
        return 0

    if sub == "set":
        if len(ctx.args) < 3:
            ctx.ui.print_error(
                "Missing arguments for `config set`.",
                hint="Usage: `config set <key> <value>` (e.g., `config set model mistral` or `config set animations false`)",
            )
            return 1
        key = ctx.args[1].strip()
        val_str = " ".join(ctx.args[2:]).strip()
        data = ctx.config.to_dict()
        if key not in data:
            ctx.ui.print_error(
                f"Unknown configuration key '{key}'.",
                hint=f"Valid keys: {', '.join(data.keys())}",
            )
            return 1
        data[key] = val_str
        try:
            updated = SoulConfig.from_dict(data)
        except ValueError as exc:
            ctx.ui.print_error(str(exc))
            return 1

        for k, v in updated.to_dict().items():
            setattr(ctx.config, k, v)
        save_config(ctx.config)
        ctx.db.save_preferences(ctx.config)
        ctx.conversation_service.update_config(ctx.config)
        ctx.ui.print_success(f"Updated `{key}` = `{getattr(ctx.config, key)}`.")
        return 0

    ctx.ui.print_error(
        f"Unknown config subcommand '{sub}'.",
        hint="Use `config show`, `config set <key> <value>`, `config path`, or `config reset --yes`.",
    )
    return 1


def cmd_history(ctx: CommandContext) -> int:
    """View, search, export, or delete local SQLite conversation and command history."""
    sub = ctx.args[0].lower() if ctx.args else "list"

    if sub == "list":
        convs = ctx.db.list_conversations(limit=20)
        cmds = ctx.db.list_command_history(limit=15)

        table = Table(
            title="📜 Saved Conversations (`~/.local/share/soulshell/soulshell.db`)",
            border_style=ctx.ui.styles["border"],
        )
        table.add_column("ID", style=ctx.ui.styles["primary"], width=6)
        table.add_column("Title", style="white")
        table.add_column("Mode", style=ctx.ui.styles["secondary"], width=12)
        table.add_column("Model", style="cyan", width=16)
        table.add_column("Messages", width=9)
        table.add_column("Updated At", style="dim", width=22)

        for c in convs:
            table.add_row(
                str(c.id),
                c.title,
                c.soul_mode,
                c.model or "-",
                str(len(c.messages)),
                c.updated_at,
            )
        ctx.ui.console.print(table)

        if cmds:
            cmd_table = Table(
                title="⌨️ Recent Explained / Analyzed Commands",
                border_style=ctx.ui.styles["panel_border"],
            )
            cmd_table.add_column("ID", width=6)
            cmd_table.add_column("Command", style="bright_cyan")
            cmd_table.add_column("Risk", width=10)
            cmd_table.add_column("Purpose", style="white")
            for ch in cmds[:10]:
                cmd_table.add_row(
                    str(ch.id), ch.command, ch.risk_level.upper(), ch.purpose[:70]
                )
            ctx.ui.console.print(cmd_table)

        if not ctx.config.save_history:
            ctx.ui.print_warning(
                "Note: History saving is currently disabled (`save_history = false`)."
            )
        ctx.ui.console.print(
            "[dim]Subcommands: `history list` | `history search <query>` | `history view <id>` | `history export <file.md>` | `history clear --yes`[/dim]"
        )
        return 0

    if sub == "search":
        query = " ".join(ctx.args[1:]).strip()
        if not query:
            ctx.ui.print_error("Usage: `history search <keyword>`")
            return 1
        matches = ctx.db.list_conversations(search_query=query)
        if not matches:
            ctx.ui.print_warning(f"No saved conversations matched '{query}'.")
            return 0
        for c in matches:
            ctx.ui.console.print(
                f"[bold magenta]#{c.id}[/bold magenta] {c.title} ({c.updated_at}) — {len(c.messages)} messages"
            )
        return 0

    if sub == "view":
        if len(ctx.args) < 2 or not ctx.args[1].isdigit():
            ctx.ui.print_error("Usage: `history view <conversation_id>`")
            return 1
        conv = ctx.db.get_conversation(int(ctx.args[1]))
        if not conv:
            ctx.ui.print_error(f"Conversation #{ctx.args[1]} not found.")
            return 1
        lines = [
            f"# {conv.title}",
            f"*Mode: {conv.soul_mode} | Model: {conv.model} | Updated: {conv.updated_at}*\n",
        ]
        for m in conv.messages:
            speaker = "You" if m.role == "user" else "SoulShell"
            lines.append(f"### {speaker} ({m.created_at})\n{m.content}\n")
        ctx.ui.print_panel("\n".join(lines), title=f"📜 Conversation #{conv.id}")
        return 0

    if sub == "export":
        if len(ctx.args) < 2:
            ctx.ui.print_error("Usage: `history export <output_file.md>`")
            return 1
        out_path = Path(ctx.args[1]).expanduser()
        convs = ctx.db.list_conversations(limit=50)
        lines = [f"# {APP_NAME} — History Export\n"]
        for c in convs:
            lines.append(f"## #{c.id}: {c.title} ({c.updated_at})")
            for m in c.messages:
                lines.append(f"- **{m.role.upper()}** ({m.created_at}): {m.content}")
            lines.append("")
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text("\n".join(lines), encoding="utf-8")
        ctx.ui.print_success(f"Exported {len(convs)} conversation(s) to {out_path}")
        return 0

    if sub in ("clear", "delete"):
        if "--yes" not in ctx.args:
            ctx.ui.print_warning(
                "Confirmation required: Run `history clear --yes` to permanently delete stored history."
            )
            return 1
        deleted_count = ctx.db.clear_all_history(confirmed=True)
        ctx.ui.print_success(
            f"Deleted {deleted_count} conversation(s) and cleared command history."
        )
        return 0

    ctx.ui.print_error(
        f"Unknown history subcommand '{sub}'.",
        hint="Use `history list`, `history search <q>`, `history view <id>`, `history export <path>`, or `history clear --yes`.",
    )
    return 1


def cmd_favorites(ctx: CommandContext) -> int:
    """Manage bookmarked favorite shell commands (`favorites list`, `favorites add <cmd>`, `favorites remove <id> --yes`)."""
    sub = ctx.args[0].lower() if ctx.args else "list"

    if sub == "list":
        favs = ctx.db.list_favorite_commands()
        if not favs:
            ctx.ui.print_panel(
                "No favorite commands saved yet.\nAdd one with: `favorites add <command>`",
                title="⭐ Favorite Commands",
            )
            return 0
        table = Table(
            title="⭐ Saved Favorite Commands",
            border_style=ctx.ui.styles["border"],
        )
        table.add_column("ID", style=ctx.ui.styles["primary"], width=6)
        table.add_column("Command", style="bright_cyan")
        table.add_column("Saved At", style="dim", width=22)
        for f in favs:
            table.add_row(str(f.id), f.command, f.created_at)
        ctx.ui.console.print(table)
        return 0

    if sub == "add":
        cmd_str = " ".join(ctx.args[1:]).strip()
        if not cmd_str:
            ctx.ui.print_error("Usage: `favorites add <command>`")
            return 1
        entry = ctx.db.add_favorite_command(cmd_str)
        ctx.ui.print_success(f"Added favorite command #{entry.id}: `{entry.command}`")
        return 0

    if sub in ("remove", "delete", "del"):
        if len(ctx.args) < 2 or not ctx.args[1].isdigit():
            ctx.ui.print_error("Usage: `favorites remove <id> --yes`")
            return 1
        if "--yes" not in ctx.args:
            ctx.ui.print_warning(
                f"Confirmation required: Run `favorites remove {ctx.args[1]} --yes` to delete."
            )
            return 1
        ok = ctx.db.delete_favorite_command(int(ctx.args[1]), confirmed=True)
        if ok:
            ctx.ui.print_success(f"Removed favorite #{ctx.args[1]}.")
            return 0
        ctx.ui.print_error(f"Favorite #{ctx.args[1]} not found.")
        return 1

    ctx.ui.print_error(
        f"Unknown favorites subcommand '{sub}'.",
        hint="Use `favorites list`, `favorites add <command>`, or `favorites remove <id> --yes`.",
    )
    return 1


def cmd_exit(ctx: CommandContext) -> int:
    """Exit SoulShell Terminal gracefully with a Soul King farewell."""
    ctx.should_exit = True
    ctx.ui.print_panel(
        "💀🎸 **The Soul King bids you farewell.**\n"
        "*\"Until our souls meet again in the terminal... YOHOHOHO!\"* ♫",
        title="Farewell from SoulShell Terminal",
    )
    return 0


def register_general_commands(router: CommandRouter) -> None:
    router.register(
        "help",
        "General",
        "help [command]",
        "Display all available commands or detailed help for one command.",
        cmd_help,
        aliases=["?"],
    )
    router.register(
        "about",
        "General",
        "about",
        "Show SoulShell Terminal identity, Dark Impulse lineage, and disclaimer.",
        cmd_about,
    )
    router.register(
        "version",
        "General",
        "version",
        "Show the SoulShell Terminal version.",
        cmd_version,
    )
    router.register(
        "clear",
        "General",
        "clear",
        "Clear the terminal display.",
        cmd_clear,
        aliases=["cls"],
    )
    router.register(
        "banner",
        "General",
        "banner",
        "Display the SoulShell ASCII banner and status header.",
        cmd_banner,
    )
    router.register(
        "status",
        "General",
        "status",
        "Show AI connection status, installed models, and SQLite health.",
        cmd_status,
    )
    router.register(
        "config",
        "General",
        "config [show|set <k> <v>|reset --yes]",
        "View or modify configuration (`~/.config/soulshell/config.toml`).",
        cmd_config,
    )
    router.register(
        "mode",
        "General",
        "mode [soulking|developer|ghost]",
        "View or switch the active AI personality mode.",
        cmd_mode,
    )
    router.register(
        "history",
        "General",
        "history [list|search|view|export|clear]",
        "Manage locally stored conversations and command history.",
        cmd_history,
    )
    router.register(
        "favorites",
        "General",
        "favorites [list|add <cmd>|remove <id> --yes]",
        "View, add, or remove bookmarked favorite commands.",
        cmd_favorites,
        aliases=["fav"],
    )
    router.register(
        "exit",
        "General",
        "exit",
        "Exit SoulShell Terminal.",
        cmd_exit,
    )
    router.register(
        "quit",
        "General",
        "quit",
        "Exit SoulShell Terminal.",
        cmd_exit,
        aliases=["q"],
    )
