#!/usr/bin/env python3
"""
Main entry point for SoulShell Terminal.
Upgraded from Dark Impulse — Workspace 1.
100% Terminal-based CLI application powered by Rich, SQLite, and local Ollama.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure src/ is on sys.path when invoked directly as `python main.py` from repo root
SRC_DIR = Path(__file__).resolve().parent / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from soulshell.app import main

if __name__ == "__main__":
    sys.exit(main())
