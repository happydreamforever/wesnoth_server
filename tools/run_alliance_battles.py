#!/usr/bin/env python3
"""Isolated entry point for the installed local shared battle service."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from alliance.battle_daemon import main
if __name__ == '__main__':
    raise SystemExit(main())
