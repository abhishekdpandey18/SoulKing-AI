"""
Configuration system for SoulKing (Section 12).
Supports TOML configuration at ~/.config/soulking/config.toml
and local SQLite database at ~/.local/share/soulking/soulking.db.
Validates all settings and never stores passwords or API keys in source code.
"""

from __future__ import annotations

import os
import sqlite3
import tempfile
import tomllib
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional

from dotenv import load_dotenv

load_dotenv()

APP_NAME = "SoulKing"
ORIGINAL_PROJECT = "Dark Impulse — Workspace 1"
TAGLINE = "Your terminal. Your AI. Your phantom."
SECONDARY_TAGLINE = "Even without a body, intelligence lives on. Yohohoho!"
VERSION = "2.0.0"

VALID_THEMES = ("soulking", "cyberpunk", "phantom", "plain")
VALID_MODES = ("soulking", "developer", "ghost")
VALID_LOG_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR")
VALID_HUMOR_FREQUENCIES = ("minimal", "balanced", "frequent")
VALID_EXPLANATION_LEVELS = ("beginner", "intermediate", "advanced")

MAX_LOG_FILE_BYTES = 2 * 1024 * 1024  # 2 MB limit for loganalyze


def normalize_mode_name(mode: str) -> str:
    """Normalize mode aliases (e.g. 'soul_king' -> 'soulking', 'dev' -> 'developer')."""
    cleaned = (mode or "").strip().lower().replace("-", "").replace("_", "")
    if cleaned in ("soulking", "brook", "soul"):
        return "soulking"
    if cleaned in ("developer", "dev", "coder"):
        return "developer"
    if cleaned in ("ghost", "spooky", "phantom"):
        return "ghost"
    return (mode or "").strip().lower()


def get_project_root() -> Path:
    """Return the root directory of the SoulKing repository."""
    return Path(__file__).resolve().parent.parent.parent


def get_assets_dir() -> Path:
    """Return the path to the assets directory."""
    return get_project_root() / "assets"


def _supports_sqlite_locks(directory: Path) -> bool:
    """Check whether a filesystem directory supports SQLite locking (handles 9p/NFS mounts gracefully)."""
    probe = directory / ".soulking_lock_probe.db"
    try:
        directory.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(probe), timeout=2.0)
        conn.execute("CREATE TABLE IF NOT EXISTS _probe (id INTEGER PRIMARY KEY);")
        conn.close()
        if probe.exists():
            probe.unlink()
        return True
    except (sqlite3.Error, OSError):
        try:
            if probe.exists():
                probe.unlink()
        except OSError:
            pass
        return False


def get_default_config_path() -> Path:
    """
    Return the configuration file path (~/.config/soulking/config.toml),
    overridable via SOULKING_CONFIG_PATH, SOULSHELL_CONFIG_PATH, or XDG_CONFIG_HOME.
    """
    env_path = os.environ.get("SOULKING_CONFIG_PATH") or os.environ.get(
        "SOULSHELL_CONFIG_PATH"
    )
    if env_path:
        return Path(env_path).expanduser().resolve()
    xdg_cfg = os.environ.get("XDG_CONFIG_HOME")
    base = Path(xdg_cfg).expanduser().resolve() if xdg_cfg else (Path.home() / ".config")
    return base / "soulking" / "config.toml"


def get_default_data_dir() -> Path:
    """
    Return the local application data directory (~/.local/share/soulking),
    falling back to a user-owned tmp directory only if the home mount blocks SQLite locks.
    """
    env_dir = os.environ.get("SOULKING_DATA_DIR") or os.environ.get("SOULSHELL_DATA_DIR")
    if env_dir:
        p = Path(env_dir).expanduser().resolve()
        p.mkdir(parents=True, exist_ok=True)
        return p

    xdg_data = os.environ.get("XDG_DATA_HOME")
    candidate = (
        Path(xdg_data).expanduser().resolve() / "soulking"
        if xdg_data
        else Path.home() / ".local" / "share" / "soulking"
    )
    if _supports_sqlite_locks(candidate):
        return candidate

    fallback = Path(tempfile.gettempdir()) / f"soulking-{os.getuid()}"
    fallback.mkdir(parents=True, exist_ok=True)
    return fallback


def get_default_db_path() -> Path:
    """Return default SQLite database path (~/.local/share/soulking/soulking.db)."""
    return get_default_data_dir() / "soulking.db"


@dataclass
class SoulConfig:
    """Validated configuration for SoulKing."""

    theme: str = "soulking"
    model: str = field(
        default_factory=lambda: os.environ.get("SOULKING_MODEL")
        or os.environ.get("SOULSHELL_MODEL", "llama3.2")
    )
    ollama_url: str = field(
        default_factory=lambda: os.environ.get("SOULKING_OLLAMA_HOST")
        or os.environ.get("SOULSHELL_OLLAMA_HOST", "http://127.0.0.1:11434")
    )
    personality_mode: str = "soulking"
    animations: bool = True
    save_history: bool = True
    request_timeout: int = field(
        default_factory=lambda: int(
            os.environ.get("SOULKING_REQUEST_TIMEOUT")
            or os.environ.get("SOULSHELL_REQUEST_TIMEOUT", "60")
        )
    )
    log_level: str = field(
        default_factory=lambda: os.environ.get("SOULKING_LOG_LEVEL")
        or os.environ.get("SOULSHELL_LOG_LEVEL", "INFO")
    )
    humor_frequency: str = "balanced"
    explanation_level: str = "intermediate"
    temperature: float = 0.7
    assistant_name: str = "SoulKing"

    def validate(self) -> "SoulConfig":
        """Validate configuration fields and raise ValueError on invalid settings."""
        self.theme = (self.theme or "soulking").strip().lower()
        if self.theme not in VALID_THEMES:
            raise ValueError(
                f"Invalid theme '{self.theme}'. Valid options: {', '.join(VALID_THEMES)}"
            )

        self.personality_mode = normalize_mode_name(self.personality_mode)
        if self.personality_mode not in VALID_MODES:
            raise ValueError(
                f"Invalid personality_mode '{self.personality_mode}'. Valid options: {', '.join(VALID_MODES)}"
            )

        self.ollama_url = (self.ollama_url or "").strip().rstrip("/")
        if not (
            self.ollama_url.startswith("http://")
            or self.ollama_url.startswith("https://")
        ):
            raise ValueError(
                f"Invalid ollama_url '{self.ollama_url}'. Must start with http:// or https://"
            )

        self.model = (self.model or "").strip()
        if not self.model:
            self.model = "llama3.2"

        self.animations = bool(self.animations)
        if self.theme == "plain":
            self.animations = False

        self.save_history = bool(self.save_history)

        self.request_timeout = int(self.request_timeout)
        if not (5 <= self.request_timeout <= 600):
            raise ValueError("request_timeout must be between 5 and 600 seconds.")

        self.log_level = (self.log_level or "INFO").strip().upper()
        if self.log_level not in VALID_LOG_LEVELS:
            raise ValueError(
                f"Invalid log_level '{self.log_level}'. Valid options: {', '.join(VALID_LOG_LEVELS)}"
            )

        self.humor_frequency = (self.humor_frequency or "balanced").strip().lower()
        if self.humor_frequency not in VALID_HUMOR_FREQUENCIES:
            raise ValueError(
                f"Invalid humor_frequency '{self.humor_frequency}'. Valid options: {', '.join(VALID_HUMOR_FREQUENCIES)}"
            )

        self.explanation_level = (
            self.explanation_level or "intermediate"
        ).strip().lower()
        if self.explanation_level not in VALID_EXPLANATION_LEVELS:
            raise ValueError(
                f"Invalid explanation_level '{self.explanation_level}'. Valid options: {', '.join(VALID_EXPLANATION_LEVELS)}"
            )

        self.temperature = float(self.temperature)
        if not (0.0 <= self.temperature <= 2.0):
            raise ValueError("temperature must be between 0.0 and 2.0.")

        self.assistant_name = (self.assistant_name or "SoulKing").strip()
        if not self.assistant_name or len(self.assistant_name) > 60:
            raise ValueError("assistant_name must be 1 to 60 characters.")

        return self

    def to_dict(self) -> Dict[str, Any]:
        self.validate()
        return asdict(self)

    def to_toml(self) -> str:
        """Serialize configuration to a clean, commented TOML string."""
        self.validate()
        return (
            "# SoulKing Configuration (~/.config/soulking/config.toml)\n"
            "# Do not store passwords or cloud API keys in this file.\n\n"
            f'assistant_name = "{self.assistant_name}"\n'
            f'theme = "{self.theme}"  # Options: soulking, cyberpunk, phantom, plain\n'
            f'personality_mode = "{self.personality_mode}"  # Options: soulking, developer, ghost\n'
            f'model = "{self.model}"\n'
            f'ollama_url = "{self.ollama_url}"\n'
            f"animations = {'true' if self.animations else 'false'}\n"
            f"save_history = {'true' if self.save_history else 'false'}\n"
            f"request_timeout = {self.request_timeout}\n"
            f'log_level = "{self.log_level}"  # Options: DEBUG, INFO, WARNING, ERROR\n'
            f'humor_frequency = "{self.humor_frequency}"  # Options: minimal, balanced, frequent\n'
            f'explanation_level = "{self.explanation_level}"  # Options: beginner, intermediate, advanced\n'
            f"temperature = {self.temperature}\n"
        )

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SoulConfig":
        valid_keys = {f.name for f in cls.__dataclass_fields__.values()}
        filtered: Dict[str, Any] = {}
        if "soul_mode" in data and "personality_mode" not in data:
            filtered["personality_mode"] = normalize_mode_name(str(data["soul_mode"]))
        if "history_enabled" in data and "save_history" not in data:
            filtered["save_history"] = data["history_enabled"]
        if "ollama_host" in data and "ollama_url" not in data:
            filtered["ollama_url"] = data["ollama_host"]
        if "selected_model" in data and "model" not in data and data["selected_model"]:
            filtered["model"] = data["selected_model"]
        if "animations_enabled" in data and "animations" not in data:
            filtered["animations"] = data["animations_enabled"]

        for k, v in data.items():
            if k in valid_keys:
                filtered[k] = v

        for bool_key in ("animations", "save_history"):
            if bool_key in filtered and isinstance(filtered[bool_key], str):
                filtered[bool_key] = filtered[bool_key].strip().lower() in (
                    "true",
                    "1",
                    "yes",
                    "on",
                )
        if "request_timeout" in filtered:
            filtered["request_timeout"] = int(filtered["request_timeout"])
        if "temperature" in filtered:
            filtered["temperature"] = float(filtered["temperature"])

        return cls(**filtered).validate()


def load_config(config_path: Optional[Path] = None) -> SoulConfig:
    """
    Load configuration from `~/.config/soulking/config.toml`.
    Creates a default config file if none exists.
    """
    path = Path(config_path) if config_path else get_default_config_path()
    if not path.exists():
        cfg = SoulConfig().validate()
        try:
            save_config(cfg, path)
        except OSError:
            pass
        return cfg

    raw_bytes = path.read_bytes()
    parsed = tomllib.loads(raw_bytes.decode("utf-8"))
    return SoulConfig.from_dict(parsed)


def save_config(config: SoulConfig, config_path: Optional[Path] = None) -> Path:
    """Validate and write configuration to `~/.config/soulking/config.toml`."""
    config.validate()
    path = Path(config_path) if config_path else get_default_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(config.to_toml(), encoding="utf-8")
    return path


UserSettings = SoulConfig
