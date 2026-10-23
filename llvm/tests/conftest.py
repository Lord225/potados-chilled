"""Optional LLVM fixtures; raw RTL simulator tests require no LLVM build."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Callable

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
LLVM_ROOT = PROJECT_ROOT / "llvm"


@pytest.fixture(scope="session")
def compile_program() -> Callable[..., Path]:
    """Compile a temporary freestanding C program using the maintained driver.

    A normal source checkout can run the hardware and RTL simulator tests without
    building LLVM. Set POTADOS_REQUIRE_BACKEND=1 in compiler CI to turn a missing
    toolchain into a failure rather than a skip.
    """
    build = Path(os.environ.get("LLVM_BUILD", LLVM_ROOT / "build" / "llvm"))
    module = Path(os.environ.get("POTADOS_MODULE", LLVM_ROOT / "build" / "potados-backend" / ("Potados.dylib" if sys.platform == "darwin" else "Potados.so")))
    missing = [str(path) for path in (build / "bin" / "llc", build / "bin" / "opt", module) if not path.is_file()]
    clang = os.environ.get("CLANG", "clang")
    if not shutil.which(clang):
        missing.append(clang)
    if missing:
        message = "POTADOS LLVM toolchain is not built; run python3 llvm/scripts/build.py backend (missing: " + ", ".join(missing) + ")"
        if os.environ.get("POTADOS_REQUIRE_BACKEND") == "1":
            pytest.fail(message)
        pytest.skip(message)

    def compile_source(source: str, directory: Path, *, opt: str = "O2", runtime: bool = False, name: str = "program") -> Path:
        directory.mkdir(parents=True, exist_ok=True)
        input_path = directory / f"{name}.c"
        output_path = directory / f"{name}.asm"
        input_path.write_text(source, encoding="utf-8")
        command = [sys.executable, str(LLVM_ROOT / "scripts" / "compile.py"), str(input_path), "-o", str(output_path), "-" + opt]
        if not runtime:
            command.append("--no-runtime")
        result = subprocess.run(command, cwd=PROJECT_ROOT, text=True, capture_output=True, timeout=180)
        assert result.returncode == 0, (
            f"Compilation failed for {name} at -{opt}\n"
            f"Command: {' '.join(command)}\n{result.stdout[-5000:]}\n{result.stderr[-12000:]}"
        )
        return output_path

    return compile_source
