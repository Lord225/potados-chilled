#!/usr/bin/env python3
"""Run the source-tree cocotb/Verilator POTADOS RTL simulator and debugger."""
from pathlib import Path
import sys

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root.parent / "asm/src"))
sys.path.insert(0, str(root / "potados-emulator/src"))
from potados_emulator.cli import main  # noqa: E402

if __name__ == "__main__":
    main()
