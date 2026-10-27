"""
Linux Assistance & Local AI Commands for SoulShell Terminal (Sections 5, 7, 9).
Commands:
- explain <command>
- suggest <natural-language-task>
- permissions <path>
- findfile <filename>
- models
- model [name]
- ask <prompt>
Provides deterministic offline fallbacks when Ollama is unavailable while clearly stating
that the local AI server is offline (never faking AI responses).
"""

from __future__ import annotations

import json
import re
from typing import Dict, Tuple

from rich.table import Table

from soulshell.ai.ollama_provider import AIProviderError
from soulshell.ai.personality import build_system_prompt
from soulshell.core.command_router import CommandContext, CommandRouter
from soulshell.core.config import save_config
from soulshell.services.command_safety import CommandSafetyChecker
from soulshell.services.system_info import SystemInfoService

# Built-in offline command reference for common commands when Ollama is disconnected
OFFLINE_COMMAND_REFERENCE: Dict[str, Tuple[str, str, str]] = {
    "ls": (
        "Lists directory contents.",
        "`-l` (long listing with permissions/owners), `-a` (include hidden dotfiles), `-h` (human-readable sizes).",
        "ls -lah",
    ),
    "find": (
        "Searches directory trees for files or directories matching criteria.",
        "`-type f` (files), `-type d` (directories), `-name <pattern>`, `-size +100M`, `-mtime -7`.",
        "find ~ -type f -name '*.py' -mtime -7",
    ),
    "grep": (
        "Searches file contents for lines matching a regular expression.",
        "`-r` (recursive), `-n` (line numbers), `-i` (case-insensitive), `-l` (file names only).",
        "grep -rn 'TODO' ./src",
    ),
    "chmod": (
        "Changes file or directory access permissions.",
        "`755` (rwxr-xr-x for scripts/dirs), `644` (rw-r--r-- for files), `600` (rw------- for private keys).",
        "chmod 755 script.sh",
    ),
    "ps": (
        "Reports a snapshot of current processes.",
        "`aux` or `-ef` (all processes with user/CPU/memory details).",
        "ps aux --sort=-%mem | head -n 15",
    ),
    "df": (
        "Reports filesystem disk space usage.",
        "`-h` (human-readable GB/MB), `-T` (include filesystem type).",
        "df -hT",
    ),
    "du": (
        "Estimates file and directory space usage.",
        "`-s` (summary), `-h` (human-readable), `--max-depth=1`.",
        "du -sh * | sort -hr | head -n 10",
    ),
    "ss": (
        "Inspects socket statistics and listening network ports.",
        "`-t` (TCP), `-u` (UDP), `-l` (listening), `-n` (numeric ports), `-p` (processes).",
        "ss -tuln",
    ),
    "ip": (
        "Shows or manipulates routing, network devices, and interfaces.",
        "`addr show` (IP addresses), `route show` (routing table), `-brief` (compact table).",
        "ip -brief addr show",
    ),
    "journalctl": (
        "Queries the systemd journal logs.",
        "`-u <unit>` (specific service), `-xe` (recent errors with explanations), `-n 50` (last 50 lines).",
        "journalctl -xe -n 50 --no-pager",
    ),
}

# Built-in deterministic natural-language task heuristics for offline guidance
OFFLINE_SUGGEST_RULES: list[Tuple[re.Pattern, str, str, str]] = [
    (
        re.compile(r"(largest|biggest|large)\s+files", re.IGNORECASE),
        "find ~ -type f -size +100M -exec ls -lh {} + 2>/dev/null | sort -k5 -hr | head -n 20",
        "Finds regular files larger than 100 MB in your home directory and sorts them by size.",
        "du -ah ~ 2>/dev/null | sort -hr | head -n 20",
    ),
    (
        re.compile(r"python\s+files.*(modified|last|days|recent)", re.IGNORECASE),
        "find . -type f -name '*.py' -mtime -7",
        "Finds Python (`.py`) files under the current directory modified within the last 7 days.",
        "find . -maxdepth 3 -type f -name '*.py' -mtime -7 -ls",
    ),
    (
        re.compile(r"(listening|open)\s+(network\s+)?ports", re.IGNORECASE),
        "ss -tuln",
        "Displays all listening TCP (`-t`) and UDP (`-u`) ports using numeric addresses (`-n`).",
        "ss -tulnp",
    ),
    (
        re.compile(r"files\s+larger\s+than\s+(\d+)\s*mb", re.IGNORECASE),
        "find . -type f -size +100M -print",
        "Searches for regular files larger than the specified megabyte threshold in read-only mode.",
        "find . -maxdepth 3 -type f -size +100M -ls",
    ),
    (
        re.compile(r"pdf\s+files", re.IGNORECASE),
        "find ~/Downloads -type f -iname '*.pdf'",
        "Searches `~/Downloads` case-insensitively for PDF documents.",
        "ls -lh ~/Downloads/*.pdf",
    ),
]


def cmd_explain(ctx: CommandContext) -> int:
    """Explain what a Linux command does, its flags, risk assessment, and safer alternatives."""
    cmd_str = ctx.arg_text.strip()
    if not cmd_str:
        ctx.ui.print_error(
            "Usage: `explain <command>`",
            hint="Example: `explain ls -la` or `explain find /var/log -name '*.log'`",
        )
        return 1

    safety = CommandSafetyChecker.analyze(cmd_str)
    ctx.ui.print_code_panel(cmd_str, language="bash", title="⌨️ Command Under Inspection")

    sys_prompt = build_system_prompt(
        ctx.config,
        task_instructions=(
            "Explain the Linux command clearly. Include:\n"
            "1. What the command does overall\n"
            "2. Breakdown of important flags and arguments\n"
            "3. Potential risks or caveats\n"
            "4. A safer or cleaner alternative when appropriate."
        ),
    )

    try:
        resp = ctx.ai_provider.generate_chat(
            messages=[{"role": "user", "content": f"Explain this Linux command: `{cmd_str}`"}],
            model=ctx.config.model,
            system_prompt=sys_prompt,
            temperature=0.3,
        )
        ai_text = resp.content.strip()
        body = (
            f"{ai_text}\n\n---\n"
            f"**Deterministic Safety Check:** `{safety.risk_level.upper()}`\n"
            f"- {safety.summary_text()}\n"
            f"- **Safer Alternative:** {safety.primary_safer_alternative}"
        )
        ctx.ui.print_panel(body, title=f"📖 AI Command Explanation ({ctx.config.model})")
    except AIProviderError as exc:
        # Honest offline fallback: never pretend AI is connected
        base_bin = safety.tokens[0].split("/")[-1] if safety.tokens else ""
        ref = OFFLINE_COMMAND_REFERENCE.get(base_bin)
        ref_block = ""
        if ref:
            ref_block = (
                f"### Offline Built-In Reference for `{base_bin}`\n"
                f"- **Purpose:** {ref[0]}\n"
                f"- **Common Flags:** {ref[1]}\n"
                f"- **Example:** `{ref[2]}`\n\n"
            )
        body = (
            f"**[AI Status: Offline]** {exc.message.splitlines()[0]}\n\n"
            f"{ref_block}"
            f"### Deterministic Static Risk Analysis\n"
            f"- **Parsed Tokens:** `{', '.join(safety.tokens)}`\n"
            f"- **Risk Level:** `{safety.risk_level.upper()}`\n"
            f"- **Assessment:** {safety.summary_text()}\n"
            f"- **Safer Alternative:** {safety.primary_safer_alternative}"
        )
        ctx.ui.print_panel(body, title="📖 Offline Command Analysis (Ollama Disconnected)")

    ctx.db.add_command_history(
        command=cmd_str,
        purpose="Explained via `explain` command",
        risk_level=safety.risk_level,
        risk_warnings=safety.summary_text(),
        save_history=ctx.config.save_history,
    )
    return 0


def cmd_suggest(ctx: CommandContext) -> int:
    """
    Section 9: Natural-Language Linux Assistant (`suggest <task>`).
    Returns:
    1. A proposed command (syntax-highlighted in a Rich panel)
    2. An explanation
    3. A risk assessment
    4. A safer alternative when appropriate
    Never executes AI-generated shell commands automatically.
    """
    task_desc = ctx.arg_text.strip()
    if not task_desc:
        ctx.ui.print_error(
            "Usage: `suggest <natural-language-task>`",
            hint="Example: `suggest show the largest files in my home directory`",
        )
        return 1

    task_prompt = (
        "Convert the user's natural-language Linux task into a proposed shell command. "
        "Respond with a valid JSON object containing these keys:\n"
        '{\n'
        '  "proposed_command": "exact shell command",\n'
        '  "explanation": "clear explanation of flags and behavior",\n'
        '  "safer_alternative": "read-only or bounded alternative command"\n'
        '}'
    )
    sys_prompt = build_system_prompt(ctx.config, task_instructions=task_prompt)

    proposed_cmd = ""
    explanation = ""
    safer_alt = ""
    source_label = f"AI Model: {ctx.config.model}"

    try:
        resp = ctx.ai_provider.generate_chat(
            messages=[{"role": "user", "content": f"Task: {task_desc}"}],
            model=ctx.config.model,
            system_prompt=sys_prompt,
            temperature=0.2,
        )
        raw = resp.content.strip()
        match = re.search(r"\{.*\}", raw, flags=re.DOTALL)
        if match:
            try:
                parsed = json.loads(match.group(0))
                proposed_cmd = str(parsed.get("proposed_command") or parsed.get("command") or "").strip()
                explanation = str(parsed.get("explanation") or "").strip()
                safer_alt = str(parsed.get("safer_alternative") or "").strip()
            except (json.JSONDecodeError, TypeError):
                pass
        if not proposed_cmd:
            code_m = re.search(r"```(?:bash|sh)?\s*\n([^\n`]+)\n```", raw) or re.search(
                r"`([^`\n]+)`", raw
            )
            proposed_cmd = code_m.group(1).strip() if code_m else "find . -maxdepth 2 -ls"
            explanation = raw
    except AIProviderError as exc:
        source_label = "Offline Heuristic Catalog (Ollama Disconnected)"
        for pattern, cmd_template, expl_text, alt_cmd in OFFLINE_SUGGEST_RULES:
            m = pattern.search(task_desc)
            if m:
                proposed_cmd = cmd_template
                if m.groups() and m.group(1) and m.group(1).isdigit():
                    proposed_cmd = f"find . -type f -size +{m.group(1)}M -print"
                explanation = (
                    f"*[Note: Local Ollama server is unreachable ({exc.message.splitlines()[0]}). "
                    f"Showing built-in offline Linux recipe.]*\n\n{expl_text}"
                )
                safer_alt = alt_cmd
                break
        if not proposed_cmd:
            proposed_cmd = "find . -maxdepth 2 -type f"
            explanation = (
                f"*[Note: Local Ollama server is unreachable ({exc.message.splitlines()[0]}).]*\n"
                "Start `ollama serve` and pull a model (`ollama pull llama3.2`) for full natural-language generation."
            )
            safer_alt = "ls -la"

    safety = CommandSafetyChecker.analyze(proposed_cmd)
    if not safer_alt:
        safer_alt = safety.primary_safer_alternative

    # 1. Proposed command in syntax-highlighted Rich panel
    ctx.ui.print_code_panel(
        proposed_cmd,
        language="bash",
        title=f"✨ 1. Proposed Command ({source_label}) — Never Auto-Executed",
    )

    # 2, 3, 4: Explanation, Risk Assessment, Safer Alternative
    details_md = (
        f"### 2. Explanation\n{explanation}\n\n"
        f"### 3. Risk Assessment (`{safety.risk_level.upper()}`)\n"
        f"{safety.summary_text()}\n\n"
        f"### 4. Safer Alternative\n`{safer_alt}`"
    )
    ctx.ui.print_panel(details_md, title="🧭 Command Intelligence & Safety Review")

    ctx.db.add_command_history(
        command=proposed_cmd,
        purpose=f"[Suggest: {task_desc}] {explanation[:120]}",
        risk_level=safety.risk_level,
        risk_warnings=safety.summary_text(),
        save_history=ctx.config.save_history,
    )
    return 0


def cmd_permissions(ctx: CommandContext) -> int:
    """Inspect Unix permissions for a path (`permissions ~/Documents`) or octal mode (`permissions 755`)."""
    if not ctx.arg_text.strip():
        ctx.ui.print_error(
            "Usage: `permissions <path_or_octal>`",
            hint="Example: `permissions ~/Documents` or `permissions 755`",
        )
        return 1

    target = ctx.args[0]
    try:
        rep = SystemInfoService.inspect_permissions(target)
    except (FileNotFoundError, ValueError, OSError) as exc:
        ctx.ui.print_error(str(exc))
        return 1

    owner_s = ", ".join(rep.owner_perms) or "none (---)"
    group_s = ", ".join(rep.group_perms) or "none (---)"
    other_s = ", ".join(rep.other_perms) or "none (---)"
    special_s = ", ".join(rep.special_bits) if rep.special_bits else "None"
    notes_s = "\n".join(f"- {n}" for n in rep.security_notes)
    uid_gid_line = (
        f"**UID / GID:** `{rep.owner_uid}:{rep.group_gid}` | "
        if rep.owner_uid is not None
        else ""
    )

    body = (
        f"**Target:** `{rep.target}` ({rep.file_type})\n"
        f"{uid_gid_line}**Octal Mode:** `{rep.octal_mode}` | **Symbolic:** `{rep.symbolic_mode}`\n\n"
        f"- **Owner (User):** {owner_s}\n"
        f"- **Group:** {group_s}\n"
        f"- **Others (World):** {other_s}\n"
        f"- **Special Bits:** {special_s}\n\n"
        f"### Security Notes\n{notes_s}"
    )
    ctx.ui.print_panel(body, title="🔐 Unix Permission Analysis (Read-Only)")
    return 0


def cmd_findfile(ctx: CommandContext) -> int:
    """Search for files matching a filename or pattern (`findfile report.pdf`)."""
    if not ctx.args:
        ctx.ui.print_error(
            "Usage: `findfile <filename> [search_dir]`",
            hint="Example: `findfile report.pdf` or `findfile .py ./src`",
        )
        return 1

    pattern = ctx.args[0]
    root = ctx.args[1] if len(ctx.args) > 1 else None
    from pathlib import Path

    try:
        matches = SystemInfoService.find_files(
            pattern, search_root=Path(root) if root else None
        )
    except (ValueError, OSError) as exc:
        ctx.ui.print_error(str(exc))
        return 1

    if not matches:
        ctx.ui.print_warning(f"No files matching '{pattern}' found.")
        return 0

    lines = "\n".join(f"- `{p}`" for p in matches)
    ctx.ui.print_panel(
        lines,
        title=f"📂 Found {len(matches)} File(s) Matching '{pattern}'",
    )
    return 0


def cmd_models(ctx: CommandContext) -> int:
    """List locally installed Ollama models or show setup instructions if disconnected."""
    status = ctx.ai_provider.check_status(selected_model=ctx.config.model)
    if not status.runtime_available:
        ctx.ui.print_error(status.error_message)
        ctx.ui.print_panel(status.setup_instructions, title="⚙️ Ollama Setup Instructions")
        return 1

    if not status.models_installed:
        ctx.ui.print_warning(
            "Ollama is online, but no models are installed yet.\n"
            "Run `ollama pull llama3.2` or `ollama pull mistral` in your shell."
        )
        return 0

    table = Table(
        title=f"🔮 Installed Local Ollama Models ({status.endpoint})",
        border_style=ctx.ui.styles["border"],
    )
    table.add_column("Model Name", style=ctx.ui.styles["primary"])
    table.add_column("Size", style=ctx.ui.styles["secondary"])
    table.add_column("Family / Params", style="white")
    table.add_column("Active", width=10)

    for m in status.models_installed:
        is_sel = m.name == ctx.config.model or m.name.split(":")[0] == ctx.config.model.split(":")[0]
        fam = f"{m.family} {m.parameter_size}".strip() or "-"
        table.add_row(
            m.name,
            m.size_human,
            fam,
            "[bold green]✔ Active[/bold green]" if is_sel else "",
        )
    ctx.ui.console.print(table)
    return 0


def cmd_model(ctx: CommandContext) -> int:
    """View or switch the active local Ollama model (`model llama3.2`)."""
    if not ctx.args:
        ctx.ui.print_panel(
            f"**Current Selected Model:** `{ctx.config.model}`\n"
            "Use `models` to list installed models, or `model <name>` to switch.",
            title="🔮 Active AI Model",
        )
        return 0

    new_model = ctx.args[0].strip()
    ctx.config.model = new_model
    save_config(ctx.config)
    ctx.db.save_preferences(ctx.config)
    ctx.conversation_service.update_config(ctx.config)
    ctx.ui.print_success(f"Selected model updated to `{new_model}`.")
    return 0


def cmd_ask(ctx: CommandContext) -> int:
    """Send a conversational prompt to the local Ollama AI model with streaming output."""
    prompt = ctx.arg_text.strip() if ctx.args else ctx.raw_line.strip()
    if not prompt:
        ctx.ui.print_error("Usage: `ask <question>` (e.g., `ask how do I debug a segfault in C?`)")
        return 1

    chunks: list[str] = []
    try:
        ctx.ui.console.print(
            f"[{ctx.ui.styles['primary']}]💀🎸 {ctx.config.assistant_name} ({ctx.config.personality_mode}):[/{ctx.ui.styles['primary']}] ",
            end="",
        )

        def _on_token(tok: str) -> None:
            chunks.append(tok)
            ctx.ui.console.print(tok, end="")

        ctx.conversation_service.chat(prompt, stream_callback=_on_token)
        ctx.ui.console.print()
        return 0
    except AIProviderError as exc:
        ctx.ui.console.print()
        ctx.ui.print_error(
            exc.message.splitlines()[0],
            hint="Ensure `ollama serve` is running and your selected model (`"
            + ctx.config.model
            + "`) is pulled.",
        )
        return 1


def register_ai_commands(router: CommandRouter) -> None:
    router.register(
        "explain",
        "Linux Assistance",
        "explain <command>",
        "Explain what a command does, its flags, risks, and safer alternatives.",
        cmd_explain,
    )
    router.register(
        "suggest",
        "Linux Assistance",
        "suggest <natural-language-task>",
        "Propose a Linux command for a task with explanation, risk check, and safer alternative.",
        cmd_suggest,
    )
    router.register(
        "permissions",
        "Linux Assistance",
        "permissions <path_or_octal>",
        "Inspect Unix permissions for a file/directory path or octal mode.",
        cmd_permissions,
        aliases=["perms"],
    )
    router.register(
        "findfile",
        "Linux Assistance",
        "findfile <filename>",
        "Find files matching a filename or pattern under the current directory.",
        cmd_findfile,
    )
    router.register(
        "models",
        "Linux Assistance",
        "models",
        "List locally installed Ollama AI models.",
        cmd_models,
    )
    router.register(
        "model",
        "Linux Assistance",
        "model [model_name]",
        "View or change the selected local AI model.",
        cmd_model,
    )
    router.register(
        "ask",
        "Linux Assistance",
        "ask <question>",
        "Chat with the local AI assistant using the active personality mode.",
        cmd_ask,
        aliases=["chat"],
    )
