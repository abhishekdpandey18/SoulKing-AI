"""
Automated tests for SQLite DatabaseManager initialization, conversation persistence,
history-disabled privacy setting, favorite commands, saved stories, and safe deletion
(Section 11 & 16).
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from soulshell.database.db import DatabaseManager


class TestDatabase(unittest.TestCase):
    """Test suite for SQLite storage and privacy safeguards."""

    def setUp(self) -> None:
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp_dir.name) / "soulshell.db"
        self.db = DatabaseManager(db_path=self.db_path)

    def tearDown(self) -> None:
        self.tmp_dir.cleanup()

    def test_sqlite_initialization_and_health(self) -> None:
        self.assertTrue(self.db_path.exists())
        health = self.db.check_health()
        self.assertTrue(health["healthy"])
        self.assertEqual(health["conversations"], 0)

    def test_save_and_retrieve_conversations(self) -> None:
        conv = self.db.create_conversation(
            title="New Haunted Session",
            soul_mode="soulking",
            model="llama3.2",
            save_history=True,
        )
        self.assertIsNotNone(conv.id)
        assert conv.id is not None

        self.db.add_message(
            conv.id, "user", "Show listening ports", model="llama3.2", save_history=True
        )
        self.db.add_message(
            conv.id, "assistant", "Run `ss -tuln`! Yohohoho!", model="llama3.2", save_history=True
        )

        loaded = self.db.get_conversation(conv.id)
        self.assertIsNotNone(loaded)
        assert loaded is not None
        self.assertEqual(loaded.title, "Show listening ports")
        self.assertEqual(len(loaded.messages), 2)

        # Search conversation
        matches = self.db.list_conversations(search_query="ss -tuln")
        self.assertEqual(len(matches), 1)

    def test_history_disabled_mode_is_respected(self) -> None:
        conv = self.db.create_conversation(
            title="Private Query",
            soul_mode="ghost",
            model="llama3.2",
            save_history=False,
        )
        self.assertIsNone(conv.id)
        msg = self.db.add_message(
            None, "user", "Do not persist this message", save_history=False
        )
        self.assertIsNone(msg.id)
        self.assertEqual(len(self.db.list_conversations()), 0)

    def test_deleting_history_requires_explicit_confirmation(self) -> None:
        conv = self.db.create_conversation(title="To Delete", save_history=True)
        assert conv.id is not None

        with self.assertRaises(PermissionError):
            self.db.delete_conversation(conv.id, confirmed=False)
        with self.assertRaises(PermissionError):
            self.db.clear_all_history(confirmed=False)

        self.assertTrue(self.db.delete_conversation(conv.id, confirmed=True))
        self.assertEqual(len(self.db.list_conversations()), 0)

    def test_favorite_commands_and_saved_stories(self) -> None:
        fav = self.db.add_favorite_command("ss -tuln", note="Check listening sockets")
        self.assertIsNotNone(fav.id)
        self.assertEqual(len(self.db.list_favorite_commands()), 1)

        with self.assertRaises(PermissionError):
            self.db.delete_favorite_command(int(fav.id), confirmed=False)
        self.assertTrue(self.db.delete_favorite_command(int(fav.id), confirmed=True))

        story = self.db.save_ghost_item(
            item_type="story",
            title="The Violin in /dev/null",
            theme="short",
            content="A haunted melody...",
        )
        self.assertIsNotNone(story.id)
        self.assertEqual(len(self.db.list_saved_ghost_items("story")), 1)


if __name__ == "__main__":
    unittest.main()
