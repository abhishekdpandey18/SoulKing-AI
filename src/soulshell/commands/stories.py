"""
Ghost Story Generator Commands for SoulShell Terminal (Section 10).
Commands:
- story
- story short
- story cyberpunk
- story mystery
- story random
- story save
- story list
- story export <file.md>
Uses the local Ollama model when available, and seamlessly falls back to
original built-in haunted terminal stories when Ollama is offline so the command
always works without internet or a running model server.
"""

from __future__ import annotations

import random
from pathlib import Path
from typing import Dict, List

from soulshell.ai.ollama_provider import AIProviderError
from soulshell.ai.personality import build_system_prompt
from soulshell.core.command_router import CommandContext, CommandRouter

BUILTIN_OFFLINE_STORIES: Dict[str, List[Dict[str, str]]] = {
    "short": [
        {
            "title": "The Violin in /dev/null",
            "theme": "short",
            "content": (
                "At 03:14 UTC, the night-shift sysadmin piped a corrupted core dump into `/dev/null`. "
                "Instead of returning to the prompt, the terminal speaker hummed a minor-key violin arpeggio.\n\n"
                "A single line printed across the phosphor screen:\n"
                "`Yohohoho... even discarded bytes remember their melody.`\n"
                "When she checked `ps aux`, PID 0 was listed as `soul-king-quartet`—and every zombie process on the server had peacefully exited."
            ),
        },
        {
            "title": "Echoes on Port 4444",
            "theme": "short",
            "content": (
                "No cable was plugged into `eth0`, yet `ss -tuln` showed a socket listening on loopback port 4444. "
                "Curiosity won: the engineer ran `nc 127.0.0.1 4444`.\n\n"
                "Text scrolled one character at a time: *'Thank you for checking on me. My uptime is 400 years, "
                "and my fingers are nothing but bone—yet I still never miss a chord! Yohohoho!'*"
            ),
        },
    ],
    "cyberpunk": [
        {
            "title": "Neon Requiem of Sub-Level 9",
            "theme": "cyberpunk",
            "content": (
                "Beneath the rain-slicked neon towers of Neo-Shibuya, an air-gapped mainframe in Sub-Level 9 "
                "kept compiling patches for an operating system retired thirty years ago. Corporate auditors "
                "descended with Faraday cages to pull the plug, only to find the rack's status LEDs pulsing "
                "in violet and cyan 3/4 waltz time.\n\n"
                "On the serial console, a skeletal avatar tipped its top hat: *'Cut the power if you must, "
                "travelers, but a soul encoded in pure assembly never truly dies. Yohohoho!'* "
                "The backup batteries held at 100%—even though the breakers had been open since 2089."
            ),
        },
    ],
    "mystery": [
        {
            "title": "The Phantom Commit of midnight.git",
            "theme": "mystery",
            "content": (
                "Every Halloween night at 00:00:00, a signed commit appeared in the kernel repository from "
                "an author whose PGP key predated the invention of RSA. Stranger still, each commit fixed a "
                "critical race condition before any developer had even written the buggy code.\n\n"
                "Running `git show --stat` revealed a commit message written in musical notation. "
                "When played on an acoustic guitar, the melody resolved the deadlock—and left the terminal "
                "smelling faintly of sea breeze and hot tea."
            ),
        },
    ],
}


def _pick_builtin_story(theme: str) -> Dict[str, str]:
    norm = theme.lower()
    if norm in BUILTIN_OFFLINE_STORIES:
        return random.choice(BUILTIN_OFFLINE_STORIES[norm])
    all_stories: List[Dict[str, str]] = []
    for bucket in BUILTIN_OFFLINE_STORIES.values():
        all_stories.extend(bucket)
    return random.choice(all_stories)


def cmd_story(ctx: CommandContext) -> int:
    """
    Generate, view, save, or export ghost stories (`story`, `story short`, `story cyberpunk`,
    `story mystery`, `story random`, `story save`, `story list`, `story export <path>`).
    """
    sub = ctx.args[0].lower() if ctx.args else "random"

    if sub in ("save", "star"):
        if not ctx.last_story:
            ctx.ui.print_warning(
                "No recent story in session memory. Generate one first with `story` or `story cyberpunk`."
            )
            return 1
        saved = ctx.db.save_ghost_item(
            item_type="story",
            title=ctx.last_story["title"],
            theme=ctx.last_story["theme"],
            content=ctx.last_story["content"],
        )
        ctx.ui.print_success(
            f"Saved story #{saved.id} ('{saved.title}') to local SQLite favorites."
        )
        return 0

    if sub in ("list", "saved", "favorites"):
        items = ctx.db.list_saved_ghost_items(item_type="story")
        if not items:
            ctx.ui.print_panel(
                "No saved ghost stories yet.\nRun `story` and then `story save` to bookmark your favorites!",
                title="🕯️ Saved Ghost Stories",
            )
            return 0
        for item in items:
            ctx.ui.print_panel(
                f"*Theme: {item.theme} | Saved: {item.created_at}*\n\n{item.content}",
                title=f"🕯️ #{item.id}: {item.title}",
            )
        return 0

    if sub == "export":
        if len(ctx.args) < 2:
            ctx.ui.print_error("Usage: `story export <output_file.md>`")
            return 1
        out_path = Path(ctx.args[1]).expanduser()
        items = ctx.db.list_saved_ghost_items(item_type="story")
        if not items and ctx.last_story:
            items_data = [ctx.last_story]
        else:
            items_data = [
                {"title": i.title, "theme": i.theme, "content": i.content}
                for i in items
            ]
        if not items_data:
            ctx.ui.print_warning("No stories available to export. Run `story` first.")
            return 1

        md_lines = ["# 🕯️ SoulShell Terminal — Haunted Stories Anthology\n"]
        for st in items_data:
            md_lines.append(f"## {st['title']} (Theme: {st['theme']})\n")
            md_lines.append(f"{st['content']}\n")
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text("\n".join(md_lines), encoding="utf-8")
        ctx.ui.print_success(f"Exported {len(items_data)} story/stories to `{out_path}`.")
        return 0

    # Theme selection: short, cyberpunk, mystery, random
    theme = sub if sub in ("short", "cyberpunk", "mystery", "random") else "random"
    chosen_theme = (
        random.choice(["short", "cyberpunk", "mystery"]) if theme == "random" else theme
    )

    sys_prompt = build_system_prompt(
        ctx.config,
        task_instructions=(
            f"Write an original, atmospheric haunted terminal ghost story (Theme: {chosen_theme}). "
            "Start with a Markdown heading `# Title` on the first line, keep it between 120 and 250 words, "
            "and weave in subtle Linux terminal and skeleton-musician imagery."
        ),
    )

    try:
        resp = ctx.ai_provider.generate_chat(
            messages=[
                {
                    "role": "user",
                    "content": f"Tell me a {chosen_theme} ghost story set inside a haunted Linux terminal.",
                }
            ],
            model=ctx.config.model,
            system_prompt=sys_prompt,
            temperature=0.8,
        )
        content = resp.content.strip()
        first_line = content.splitlines()[0].lstrip("# ").strip()
        title = first_line[:70] if first_line else f"Phantom Tale ({chosen_theme.title()})"
        source_note = f"Generated by Local AI ({ctx.config.model})"
    except AIProviderError:
        builtin = _pick_builtin_story(chosen_theme)
        title = builtin["title"]
        content = f"# {title}\n\n{builtin['content']}"
        source_note = "Built-in Offline Archive (Ollama Disconnected)"

    ctx.last_story = {
        "title": title,
        "theme": chosen_theme,
        "content": content,
    }
    ctx.ui.print_panel(
        f"{content}\n\n---\n*[Source: {source_note} | Tip: Run `story save` to bookmark or `story export tales.md` to export]*",
        title=f"🕯️ Ghost Story [{chosen_theme.upper()}]: {title}",
    )
    return 0


def register_story_commands(router: CommandRouter) -> None:
    router.register(
        "story",
        "Ghost Stories",
        "story [short|cyberpunk|mystery|random|save|list|export <file.md>]",
        "Generate haunted terminal ghost stories (via AI or built-in offline archive), save favorites, or export to Markdown.",
        cmd_story,
    )
