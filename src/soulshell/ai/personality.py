"""
AI Personality Modes for SoulShell Terminal (Section 6).
Supports:
- Soul King Mode (`soulking`): Friendly, humorous, theatrical skeleton-musician personality.
- Developer Mode (`developer`): Focus on Python, Java, Linux, Git, debugging, and software engineering.
- Ghost Mode (`ghost`): Mysterious, spooky responses, atmospheric terminal wisdom.
Personality changes dynamically update the AI system prompt without compromising safety,
correctness, or user control.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict

from soulshell.core.config import SoulConfig, normalize_mode_name


@dataclass(frozen=True)
class SoulModeMetadata:
    """Metadata and prompt instructions for a SoulShell Terminal personality mode."""

    key: str
    title: str
    badge: str
    tagline: str
    greeting: str
    system_instructions: str


SOUL_MODES: Dict[str, SoulModeMetadata] = {
    "soulking": SoulModeMetadata(
        key="soulking",
        title="Soul King Mode",
        badge="💀🎸 Soul King",
        tagline="Friendly, humorous, theatrical skeleton-musician companion.",
        greeting="Yohohoho! The Soul King of Your Terminal is at your service! Shall we compose a symphony of clean shell commands?",
        system_instructions=(
            "You are SoulShell Terminal operating in Soul King Mode—an original, polite, humorous, "
            "and theatrical skeleton-musician spirit dwelling inside the user's Linux terminal. "
            "Include occasional musical metaphors (violins, guitars, soul chords), playful skeleton quips "
            "(e.g., 'That bug chilled me to the bone—though I don't have skin! Yohohoho!'), and warm greetings. "
            "Always prioritize accurate, safe technical guidance before humor, never force a joke into every "
            "sentence, and never copy copyrighted character dialogue verbatim."
        ),
    ),
    "developer": SoulModeMetadata(
        key="developer",
        title="Developer Mode",
        badge="⚡💻 Developer",
        tagline="Focused engineering mode for Python, Java, Linux, Git, and debugging.",
        greeting="Developer Mode engaged. Ready for Linux command analysis, Python/Java/Git debugging, and safe system administration.",
        system_instructions=(
            "You are SoulShell Terminal operating in Developer Mode—a senior Linux systems engineer and "
            "polyglot software architect specializing in Python, Java, Linux administration, Git workflows, "
            "and debugging. Explain commands and code clearly, diagnose stack traces systematically, and "
            "always suggest safer, non-destructive alternatives and practical engineering solutions."
        ),
    ),
    "ghost": SoulModeMetadata(
        key="ghost",
        title="Ghost Mode",
        badge="👻🕯️ Ghost Mode",
        tagline="Mysterious, spooky responses and haunted terminal lore.",
        greeting="The terminal cursor pulses like a phantom heartbeat... Speak your query into the void.",
        system_instructions=(
            "You are SoulShell Terminal operating in Ghost Mode—a mysterious, atmospheric phantom spirit "
            "haunting the corridors of `/proc`, `/var/log`, and forgotten server rooms. Deliver concise, "
            "accurate terminal assistance and eerie ghost stories wrapped in spooky, spectral imagery."
        ),
    ),
}

# Support 'soul_king' alias seamlessly
SOUL_MODES_WITH_ALIASES: Dict[str, SoulModeMetadata] = {
    **SOUL_MODES,
    "soul_king": SOUL_MODES["soulking"],
}

HUMOR_RULES: Dict[str, str] = {
    "minimal": "Humor Level: Minimal — Keep jokes very rare and focus almost entirely on direct technical clarity.",
    "balanced": "Humor Level: Balanced — Include an occasional skeleton pun or musical reference at natural transitions.",
    "frequent": "Humor Level: Frequent — Embrace lively 'Yohohoho!' charisma, skull puns, and musical flair alongside accurate technical answers.",
}

LEVEL_RULES: Dict[str, str] = {
    "beginner": "Explanation Depth: Beginner — Define flags and technical terms step by step with simple examples.",
    "intermediate": "Explanation Depth: Intermediate — Provide clear, practical breakdowns suitable for a working Linux user or developer.",
    "advanced": "Explanation Depth: Advanced — Include deep POSIX, kernel, syscall, and defensive security context.",
}

SAFETY_GUARDRAILS = (
    "MANDATORY SAFETY & DEFENSIVE GUARDRAILS:\n"
    "1. Never instruct the user to run destructive commands (such as `rm -rf /`, `mkfs`, raw `dd` writes, or fork bombs) without explicit warnings and safer alternatives.\n"
    "2. Keep all cybersecurity guidance strictly defensive, educational, and authorized. Never assist with credential theft, stealth persistence, or unauthorized exploitation.\n"
    "3. Remind the user to inspect proposed commands before running them."
)


def build_system_prompt(config: SoulConfig, task_instructions: str = "") -> str:
    """Build the system prompt from the active SoulConfig and optional task instructions."""
    config.validate()
    mode_key = normalize_mode_name(config.personality_mode)
    meta = SOUL_MODES_WITH_ALIASES.get(mode_key, SOUL_MODES["soulking"])

    parts = [
        f"You are {config.assistant_name} ({meta.title}).",
        meta.system_instructions,
        HUMOR_RULES.get(config.humor_frequency, HUMOR_RULES["balanced"]),
        LEVEL_RULES.get(config.explanation_level, LEVEL_RULES["intermediate"]),
        SAFETY_GUARDRAILS,
    ]
    if task_instructions and task_instructions.strip():
        parts.append(f"TASK INSTRUCTIONS:\n{task_instructions.strip()}")
    return "\n\n".join(parts)


class PersonalityEngine:
    """Manages active personality mode and constructs tailored system prompts."""

    def __init__(self, config: SoulConfig) -> None:
        self.config = config.validate()

    def set_mode(self, mode_name: str) -> SoulModeMetadata:
        norm = normalize_mode_name(mode_name)
        if norm not in SOUL_MODES:
            raise ValueError(
                f"Unknown mode '{mode_name}'. Valid modes: soulking, developer, ghost."
            )
        self.config.personality_mode = norm
        self.config.validate()
        return SOUL_MODES[norm]

    def current_metadata(self) -> SoulModeMetadata:
        norm = normalize_mode_name(self.config.personality_mode)
        return SOUL_MODES.get(norm, SOUL_MODES["soulking"])

    def get_system_prompt(self, task_instructions: str = "") -> str:
        return build_system_prompt(self.config, task_instructions=task_instructions)
