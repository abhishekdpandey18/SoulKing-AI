"""
SQLite Database Manager for SoulShell Terminal (Section 11).
Default location: ~/.local/share/soulshell/soulshell.db
Persists:
- Conversation history, titles, and timestamps
- Messages
- Saved ghost stories and skeleton jokes
- Favorite commands (`favorites`)
- Command history (`history`)
- User preferences, model selection, and personality mode
Uses parameterized SQL queries throughout, creates directories automatically,
respects `save_history = False`, and requires explicit confirmation before deleting user data.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from soulshell.core.config import SoulConfig, get_default_db_path


def utc_now_iso() -> str:
    """Return current UTC timestamp in ISO-8601 format."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


@dataclass
class MessageRecord:
    """Single chat message within a conversation."""

    id: Optional[int]
    conversation_id: int
    role: str
    content: str
    model: str = ""
    soul_mode: str = "soulking"
    created_at: str = field(default_factory=utc_now_iso)


@dataclass
class ConversationRecord:
    """Conversation session metadata and chronological messages."""

    id: Optional[int]
    title: str
    soul_mode: str = "soulking"
    model: str = ""
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)
    messages: List[MessageRecord] = field(default_factory=list)


@dataclass
class CommandHistoryEntry:
    """Saved CLI command or explained command entry."""

    id: Optional[int]
    command: str
    purpose: str = ""
    risk_level: str = "safe"
    risk_warnings: str = ""
    created_at: str = field(default_factory=utc_now_iso)


@dataclass
class FavoriteCommandEntry:
    """User-bookmarked favorite command."""

    id: Optional[int]
    command: str
    note: str = ""
    created_at: str = field(default_factory=utc_now_iso)


@dataclass
class SavedGhostItem:
    """Saved ghost story or skeleton joke."""

    id: Optional[int]
    item_type: str  # 'story' or 'joke'
    title: str
    theme: str
    content: str
    created_at: str = field(default_factory=utc_now_iso)


SCHEMA_SQL = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS user_settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS conversations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    soul_mode TEXT NOT NULL DEFAULT 'soulking',
    model TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id INTEGER NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    model TEXT NOT NULL DEFAULT '',
    soul_mode TEXT NOT NULL DEFAULT 'soulking',
    created_at TEXT NOT NULL,
    FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_messages_conv ON messages(conversation_id);

CREATE TABLE IF NOT EXISTS command_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    command TEXT NOT NULL,
    purpose TEXT NOT NULL DEFAULT '',
    risk_level TEXT NOT NULL DEFAULT 'safe',
    risk_warnings TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS favorite_commands (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    command TEXT NOT NULL,
    note TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS saved_ghost_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    item_type TEXT NOT NULL,
    title TEXT NOT NULL,
    theme TEXT NOT NULL DEFAULT '',
    content TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""


class DatabaseManager:
    """Resilient SQLite manager for SoulShell Terminal."""

    def __init__(self, db_path: Optional[Path] = None) -> None:
        self.db_path = Path(db_path) if db_path else get_default_db_path()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.schema_version = 0
        self._healthy = False
        self._last_error = ""
        self.initialize()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=10.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        return conn

    def initialize(self) -> bool:
        """Create tables and apply schema initialization safely."""
        try:
            with self._connect() as conn:
                with conn:
                    conn.executescript(SCHEMA_SQL)
                    conn.execute(
                        "INSERT OR REPLACE INTO schema_migrations (version, applied_at) VALUES (?, ?);",
                        (3, utc_now_iso()),
                    )
            self.schema_version = 3
            self._healthy = True
            return True
        except sqlite3.Error as exc:
            self._healthy = False
            self._last_error = str(exc)
            return False

    def check_health(self) -> Dict[str, Any]:
        """Return health status and record counts of the local SQLite database."""
        try:
            with self._connect() as conn:
                conv_cnt = int(conn.execute("SELECT COUNT(*) FROM conversations;").fetchone()[0])
                msg_cnt = int(conn.execute("SELECT COUNT(*) FROM messages;").fetchone()[0])
                cmd_cnt = int(conn.execute("SELECT COUNT(*) FROM command_history;").fetchone()[0])
                fav_cnt = int(conn.execute("SELECT COUNT(*) FROM favorite_commands;").fetchone()[0])
                story_cnt = int(conn.execute("SELECT COUNT(*) FROM saved_ghost_items;").fetchone()[0])
            return {
                "healthy": True,
                "db_path": str(self.db_path),
                "schema_version": self.schema_version,
                "conversations": conv_cnt,
                "messages": msg_cnt,
                "command_history": cmd_cnt,
                "favorite_commands": fav_cnt,
                "saved_stories": story_cnt,
            }
        except sqlite3.Error as exc:
            return {
                "healthy": False,
                "db_path": str(self.db_path),
                "error": str(exc),
            }

    # -------------------------------------------------------------------------
    # User Preferences / Config Synchronization
    # -------------------------------------------------------------------------

    def save_preferences(self, config: SoulConfig) -> SoulConfig:
        """Persist validated SoulConfig preferences in SQLite."""
        config.validate()
        now = utc_now_iso()
        try:
            with self._connect() as conn:
                with conn:
                    for k, v in config.to_dict().items():
                        conn.execute(
                            """
                            INSERT INTO user_settings (key, value, updated_at)
                            VALUES (?, ?, ?)
                            ON CONFLICT(key) DO UPDATE SET
                                value = excluded.value,
                                updated_at = excluded.updated_at;
                            """,
                            (k, json.dumps(v), now),
                        )
        except sqlite3.Error as exc:
            self._last_error = str(exc)
        return config

    def load_preferences(self, base_config: Optional[SoulConfig] = None) -> SoulConfig:
        """Load stored preferences from SQLite, merging onto base_config if provided."""
        cfg_dict = (base_config or SoulConfig()).to_dict()
        try:
            with self._connect() as conn:
                rows = conn.execute("SELECT key, value FROM user_settings;").fetchall()
            for r in rows:
                try:
                    cfg_dict[r["key"]] = json.loads(r["value"])
                except json.JSONDecodeError:
                    cfg_dict[r["key"]] = r["value"]
            return SoulConfig.from_dict(cfg_dict)
        except (sqlite3.Error, ValueError):
            return (base_config or SoulConfig()).validate()

    # -------------------------------------------------------------------------
    # Conversations & Messages (Respects save_history setting)
    # -------------------------------------------------------------------------

    def create_conversation(
        self,
        title: str = "New Haunted Session",
        soul_mode: str = "soulking",
        model: str = "",
        save_history: bool = True,
    ) -> ConversationRecord:
        now = utc_now_iso()
        clean_title = (title or "New Haunted Session").strip()[:120]
        if not save_history:
            return ConversationRecord(
                id=None,
                title=clean_title,
                soul_mode=soul_mode,
                model=model,
                created_at=now,
                updated_at=now,
                messages=[],
            )
        try:
            with self._connect() as conn:
                with conn:
                    cur = conn.execute(
                        """
                        INSERT INTO conversations (title, soul_mode, model, created_at, updated_at)
                        VALUES (?, ?, ?, ?, ?);
                        """,
                        (clean_title, soul_mode, model, now, now),
                    )
                    conv_id = int(cur.lastrowid)
            return ConversationRecord(
                id=conv_id,
                title=clean_title,
                soul_mode=soul_mode,
                model=model,
                created_at=now,
                updated_at=now,
                messages=[],
            )
        except sqlite3.Error:
            return ConversationRecord(
                id=None,
                title=clean_title,
                soul_mode=soul_mode,
                model=model,
                created_at=now,
                updated_at=now,
                messages=[],
            )

    def add_message(
        self,
        conversation_id: Optional[int],
        role: str,
        content: str,
        model: str = "",
        soul_mode: str = "soulking",
        save_history: bool = True,
    ) -> MessageRecord:
        now = utc_now_iso()
        if not save_history or conversation_id is None:
            return MessageRecord(
                id=None,
                conversation_id=conversation_id or -1,
                role=role,
                content=content,
                model=model,
                soul_mode=soul_mode,
                created_at=now,
            )
        try:
            with self._connect() as conn:
                with conn:
                    cur = conn.execute(
                        """
                        INSERT INTO messages (conversation_id, role, content, model, soul_mode, created_at)
                        VALUES (?, ?, ?, ?, ?, ?);
                        """,
                        (conversation_id, role, content, model, soul_mode, now),
                    )
                    msg_id = int(cur.lastrowid)
                    if role == "user":
                        row = conn.execute(
                            "SELECT title FROM conversations WHERE id = ?;",
                            (conversation_id,),
                        ).fetchone()
                        if row and row["title"] in ("New Haunted Session", "New Soul Session"):
                            first_line = content.strip().splitlines()[0][:65]
                            if first_line:
                                conn.execute(
                                    "UPDATE conversations SET title = ?, updated_at = ? WHERE id = ?;",
                                    (first_line, now, conversation_id),
                                )
                        else:
                            conn.execute(
                                "UPDATE conversations SET updated_at = ? WHERE id = ?;",
                                (now, conversation_id),
                            )
                    else:
                        conn.execute(
                            "UPDATE conversations SET updated_at = ?, model = COALESCE(NULLIF(?, ''), model) WHERE id = ?;",
                            (now, model, conversation_id),
                        )
            return MessageRecord(
                id=msg_id,
                conversation_id=conversation_id,
                role=role,
                content=content,
                model=model,
                soul_mode=soul_mode,
                created_at=now,
            )
        except sqlite3.Error:
            return MessageRecord(
                id=None,
                conversation_id=conversation_id,
                role=role,
                content=content,
                model=model,
                soul_mode=soul_mode,
                created_at=now,
            )

    def get_conversation(self, conversation_id: int) -> Optional[ConversationRecord]:
        try:
            with self._connect() as conn:
                row = conn.execute(
                    "SELECT * FROM conversations WHERE id = ?;", (conversation_id,)
                ).fetchone()
                if not row:
                    return None
                msg_rows = conn.execute(
                    "SELECT * FROM messages WHERE conversation_id = ? ORDER BY id ASC;",
                    (conversation_id,),
                ).fetchall()
            messages = [
                MessageRecord(
                    id=int(m["id"]),
                    conversation_id=int(m["conversation_id"]),
                    role=m["role"],
                    content=m["content"],
                    model=m["model"],
                    soul_mode=m["soul_mode"],
                    created_at=m["created_at"],
                )
                for m in msg_rows
            ]
            return ConversationRecord(
                id=int(row["id"]),
                title=row["title"],
                soul_mode=row["soul_mode"],
                model=row["model"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
                messages=messages,
            )
        except sqlite3.Error:
            return None

    def list_conversations(
        self, search_query: str = "", limit: int = 50
    ) -> List[ConversationRecord]:
        query = (search_query or "").strip()
        try:
            with self._connect() as conn:
                if query:
                    like = f"%{query}%"
                    rows = conn.execute(
                        """
                        SELECT DISTINCT c.*
                        FROM conversations c
                        LEFT JOIN messages m ON c.id = m.conversation_id
                        WHERE c.title LIKE ? OR m.content LIKE ?
                        ORDER BY c.updated_at DESC, c.id DESC
                        LIMIT ?;
                        """,
                        (like, like, limit),
                    ).fetchall()
                else:
                    rows = conn.execute(
                        "SELECT * FROM conversations ORDER BY updated_at DESC, id DESC LIMIT ?;",
                        (limit,),
                    ).fetchall()
            out: List[ConversationRecord] = []
            for r in rows:
                conv = self.get_conversation(int(r["id"]))
                if conv:
                    out.append(conv)
            return out
        except sqlite3.Error:
            return []

    def delete_conversation(self, conversation_id: int, confirmed: bool = False) -> bool:
        if not confirmed:
            raise PermissionError(
                "Explicit confirmation (confirmed=True) is required before deleting user conversation data."
            )
        with self._connect() as conn:
            with conn:
                cur = conn.execute(
                    "DELETE FROM conversations WHERE id = ?;", (conversation_id,)
                )
                return cur.rowcount > 0

    def clear_all_history(self, confirmed: bool = False) -> int:
        """Delete all saved conversations and command history only when confirmed=True."""
        if not confirmed:
            raise PermissionError(
                "Explicit confirmation (confirmed=True) is required before clearing history."
            )
        with self._connect() as conn:
            with conn:
                cur = conn.execute("DELETE FROM conversations;")
                conn.execute("DELETE FROM messages;")
                conn.execute("DELETE FROM command_history;")
                return cur.rowcount

    # -------------------------------------------------------------------------
    # Command History
    # -------------------------------------------------------------------------

    def add_command_history(
        self,
        command: str,
        purpose: str = "",
        risk_level: str = "safe",
        risk_warnings: str = "",
        save_history: bool = True,
    ) -> CommandHistoryEntry:
        now = utc_now_iso()
        if not save_history:
            return CommandHistoryEntry(
                id=None,
                command=command,
                purpose=purpose,
                risk_level=risk_level,
                risk_warnings=risk_warnings,
                created_at=now,
            )
        try:
            with self._connect() as conn:
                with conn:
                    cur = conn.execute(
                        """
                        INSERT INTO command_history (command, purpose, risk_level, risk_warnings, created_at)
                        VALUES (?, ?, ?, ?, ?);
                        """,
                        (command, purpose, risk_level, risk_warnings, now),
                    )
                    entry_id = int(cur.lastrowid)
            return CommandHistoryEntry(
                id=entry_id,
                command=command,
                purpose=purpose,
                risk_level=risk_level,
                risk_warnings=risk_warnings,
                created_at=now,
            )
        except sqlite3.Error:
            return CommandHistoryEntry(
                id=None,
                command=command,
                purpose=purpose,
                risk_level=risk_level,
                risk_warnings=risk_warnings,
                created_at=now,
            )

    def list_command_history(
        self, search_query: str = "", limit: int = 50
    ) -> List[CommandHistoryEntry]:
        q = (search_query or "").strip()
        try:
            with self._connect() as conn:
                if q:
                    like = f"%{q}%"
                    rows = conn.execute(
                        """
                        SELECT * FROM command_history
                        WHERE command LIKE ? OR purpose LIKE ?
                        ORDER BY id DESC LIMIT ?;
                        """,
                        (like, like, limit),
                    ).fetchall()
                else:
                    rows = conn.execute(
                        "SELECT * FROM command_history ORDER BY id DESC LIMIT ?;",
                        (limit,),
                    ).fetchall()
            return [
                CommandHistoryEntry(
                    id=int(r["id"]),
                    command=r["command"],
                    purpose=r["purpose"],
                    risk_level=r["risk_level"],
                    risk_warnings=r["risk_warnings"],
                    created_at=r["created_at"],
                )
                for r in rows
            ]
        except sqlite3.Error:
            return []

    # -------------------------------------------------------------------------
    # Favorite Commands (`favorites`)
    # -------------------------------------------------------------------------

    def add_favorite_command(self, command: str, note: str = "") -> FavoriteCommandEntry:
        now = utc_now_iso()
        clean_cmd = (command or "").strip()
        if not clean_cmd:
            raise ValueError("Favorite command cannot be empty.")
        with self._connect() as conn:
            with conn:
                cur = conn.execute(
                    """
                    INSERT INTO favorite_commands (command, note, created_at)
                    VALUES (?, ?, ?);
                    """,
                    (clean_cmd, note.strip(), now),
                )
                fav_id = int(cur.lastrowid)
        return FavoriteCommandEntry(
            id=fav_id, command=clean_cmd, note=note.strip(), created_at=now
        )

    def list_favorite_commands(self) -> List[FavoriteCommandEntry]:
        try:
            with self._connect() as conn:
                rows = conn.execute(
                    "SELECT * FROM favorite_commands ORDER BY id DESC;"
                ).fetchall()
            return [
                FavoriteCommandEntry(
                    id=int(r["id"]),
                    command=r["command"],
                    note=r["note"],
                    created_at=r["created_at"],
                )
                for r in rows
            ]
        except sqlite3.Error:
            return []

    def delete_favorite_command(self, fav_id: int, confirmed: bool = False) -> bool:
        if not confirmed:
            raise PermissionError("Confirmation is required to delete a favorite command.")
        with self._connect() as conn:
            with conn:
                cur = conn.execute(
                    "DELETE FROM favorite_commands WHERE id = ?;", (fav_id,)
                )
                return cur.rowcount > 0

    # -------------------------------------------------------------------------
    # Saved Ghost Stories & Jokes
    # -------------------------------------------------------------------------

    def save_ghost_item(
        self,
        item_type: str,
        title: str,
        content: str,
        theme: str = "random",
    ) -> SavedGhostItem:
        now = utc_now_iso()
        with self._connect() as conn:
            with conn:
                cur = conn.execute(
                    """
                    INSERT INTO saved_ghost_items (item_type, title, theme, content, created_at)
                    VALUES (?, ?, ?, ?, ?);
                    """,
                    (item_type, title.strip(), theme.strip(), content, now),
                )
                item_id = int(cur.lastrowid)
        return SavedGhostItem(
            id=item_id,
            item_type=item_type,
            title=title.strip(),
            theme=theme.strip(),
            content=content,
            created_at=now,
        )

    def list_saved_ghost_items(
        self, item_type: Optional[str] = None
    ) -> List[SavedGhostItem]:
        try:
            with self._connect() as conn:
                if item_type:
                    rows = conn.execute(
                        "SELECT * FROM saved_ghost_items WHERE item_type = ? ORDER BY id DESC;",
                        (item_type,),
                    ).fetchall()
                else:
                    rows = conn.execute(
                        "SELECT * FROM saved_ghost_items ORDER BY id DESC;"
                    ).fetchall()
            return [
                SavedGhostItem(
                    id=int(r["id"]),
                    item_type=r["item_type"],
                    title=r["title"],
                    theme=r["theme"],
                    content=r["content"],
                    created_at=r["created_at"],
                )
                for r in rows
            ]
        except sqlite3.Error:
            return []
