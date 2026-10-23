#!/usr/bin/env python3
"""Build the pinned LLVM tools and the out-of-tree POTADOS target module."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = ROOT.parent


def run(command: list[str]) -> None:
    print("+ " + " ".join(command), flush=True)
    subprocess.run(command, check=True)


def build_llvm(build: Path, jobs: int, build_type: str) -> None:
    source = ROOT / "llvm-project" / "llvm"
    if not (source / "CMakeLists.txt").is_file():
        run(["git", "-C", str(PROJECT_ROOT), "submodule", "update", "--init", "llvm/llvm-project"])
    run(["cmake", "-S", str(source), "-B", str(build), "-G", "Ninja",
         f"-DCMAKE_BUILD_TYPE={build_type}", "-DLLVM_ENABLE_ASSERTIONS=ON",
         "-DLLVM_ENABLE_PROJECTS=", "-DLLVM_INCLUDE_TESTS=OFF",
         "-DLLVM_INCLUDE_BENCHMARKS=OFF", "-DLLVM_INCLUDE_EXAMPLES=OFF",
         "-DLLVM_TARGETS_TO_BUILD=" + os.environ.get("LLVM_TARGETS", "MSP430")])
    run(["cmake", "--build", str(build), "--target", "llvm-config", "opt", "llc",
         "llvm-tblgen", "llvm-link", "--parallel", str(jobs)])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("component", choices=["llvm", "backend", "all"], nargs="?", default="all")
    parser.add_argument("--llvm-build", type=Path, default=Path(os.environ.get("LLVM_BUILD", ROOT / "build/llvm")))
    parser.add_argument("--backend-build", type=Path, default=Path(os.environ.get("POTADOS_BUILD", ROOT / "build/potados-backend")))
    parser.add_argument("--jobs", type=int, default=int(os.environ.get("JOBS", "2")))
    parser.add_argument("--build-type", default=os.environ.get("BUILD_TYPE", "Release"))
    args = parser.parse_args(argv)
    if args.jobs < 1:
        parser.error("--jobs must be positive")
    try:
        llvm_build = args.llvm_build.resolve()
        if args.component in {"llvm", "all"} or not (llvm_build / "lib/cmake/llvm/LLVMConfig.cmake").is_file():
            build_llvm(llvm_build, args.jobs, args.build_type)
        if args.component in {"backend", "all"}:
            run(["cmake", "-S", str(ROOT / "potados-backend"), "-B", str(args.backend_build.resolve()),
                 "-G", "Ninja", f"-DCMAKE_BUILD_TYPE={args.build_type}",
                 "-DLLVM_DIR=" + str(llvm_build / "lib/cmake/llvm")])
            run(["cmake", "--build", str(args.backend_build.resolve()), "--parallel", str(args.jobs)])
        return 0
    except (OSError, subprocess.CalledProcessError) as error:
        print(f"build failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
