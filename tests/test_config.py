"""
Automated tests for SoulConfig defaults, TOML loading/saving,
and validation of invalid settings (Section 12 & 16).
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from soulshell.core.config import SoulConfig, load_config, save_config


class TestConfig(unittest.TestCase):
    """Test suite for TOML configuration management and validation."""

    def test_config_defaults_and_validation(self) -> None:
        cfg = SoulConfig().validate()
        self.assertEqual(cfg.theme, "soulking")
        self.assertEqual(cfg.personality_mode, "soulking")
        self.assertEqual(cfg.ollama_url, "http://127.0.0.1:11434")
        self.assertTrue(cfg.save_history)
        self.assertTrue(cfg.animations)

    def test_toml_roundtrip_persistence(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            cfg_file = Path(tmpdir) / "config.toml"
            custom = SoulConfig(
                theme="cyberpunk",
                personality_mode="developer",
                model="qwen2.5-coder:7b",
                ollama_url="http://127.0.0.1:11434",
                animations=False,
                save_history=False,
                request_timeout=90,
                log_level="DEBUG",
            )
            save_config(custom, cfg_file)
            self.assertTrue(cfg_file.exists())

            loaded = load_config(cfg_file)
            self.assertEqual(loaded.theme, "cyberpunk")
            self.assertEqual(loaded.personality_mode, "developer")
            self.assertEqual(loaded.model, "qwen2.5-coder:7b")
            self.assertFalse(loaded.animations)
            self.assertFalse(loaded.save_history)
            self.assertEqual(loaded.request_timeout, 90)
            self.assertEqual(loaded.log_level, "DEBUG")

    def test_invalid_configuration_values_raise_value_error(self) -> None:
        with self.assertRaises(ValueError):
            SoulConfig(theme="neon_invalid").validate()
        with self.assertRaises(ValueError):
            SoulConfig(personality_mode="pirate_invalid").validate()
        with self.assertRaises(ValueError):
            SoulConfig(ollama_url="ftp://localhost:11434").validate()
        with self.assertRaises(ValueError):
            SoulConfig(request_timeout=2).validate()
        with self.assertRaises(ValueError):
            SoulConfig(log_level="VERBOSE_INVALID").validate()
        with self.assertRaises(ValueError):
            SoulConfig(temperature=5.0).validate()


if __name__ == "__main__":
    unittest.main()
