#!/usr/bin/env python3
"""Compile freestanding C or LLVM IR to POTADOS assembly or a flat ROM image."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = ROOT.parent
DATA_LAYOUT = "e-m:e-p:16:16-i32:16-i64:16-f32:16-f64:16-a:8-n8:16-S16"
sys.path.insert(0, str(PROJECT_ROOT / "asm/src"))
from potados_asm import AssemblerError, assemble  # noqa: E402


def tool(name: str, build: Path, override: str | None = None) -> str:
    if override:
        result = shutil.which(override) or (override if Path(override).is_file() else None)
    else:
        result = str(build / "bin" / name) if (build / "bin" / name).is_file() else shutil.which(name)
    if not result:
        raise RuntimeError(f"cannot find {name}; run llvm/scripts/build.py llvm or set {name.upper().replace('-', '_')}")
    return str(result)


def run(command: list[str], verbose: bool) -> None:
    if verbose:
        print("+ " + shlex.join(command), file=sys.stderr, flush=True)
    subprocess.run(command, check=True)


def tool_version(executable: str) -> int:
    result = subprocess.run([executable, "--version"], capture_output=True,
                            text=True, check=True, timeout=10)
    match = re.search(r"(?:clang |LLVM )?version\s+(\d+)(?:\.|\s)", result.stdout + result.stderr)
    if not match:
        raise RuntimeError(f"cannot determine LLVM version of {executable}")
    return int(match.group(1))


def check_entry(ir: Path, flags: list[str]) -> None:
    """Give a useful error before code generation of a non-runnable module."""
    entry = "main"
    startup = True
    for index, flag in enumerate(flags):
        option = flag.lstrip("-")
        if option.startswith("potados-entry="):
            entry = option.split("=", 1)[1]
        elif option == "potados-entry" and index + 1 < len(flags):
            entry = flags[index + 1]
        elif option.startswith("potados-no-startup"):
            startup = option.partition("=")[2].lower() in {"false", "0"}
    if not startup:
        return
    definitions = re.findall(r'^\s*define\b[^@\n]*@(?:"([^"]+)"|([-\w.$]+))\s*\(',
                             ir.read_text(encoding="utf-8"), re.MULTILINE)
    if entry not in {quoted or bare for quoted, bare in definitions}:
        raise RuntimeError(f"program has no definition of entry function '{entry}'; "
                           "define it, select --llc-flag=-potados-entry=NAME, "
                           "or emit library assembly with --llc-flag=-potados-no-startup")


def check_data_layout(text: str) -> None:
    # Inspect only the top-level metadata declaration. LLVM itself supplies
    # the accepted layout below, before optimization, without editing IR text.
    match = re.search(r'^\s*target\s+datalayout\s*=\s*"([^"]*)"', text, re.MULTILINE)
    if match and match[1] and match[1] != DATA_LAYOUT:
        raise RuntimeError("incompatible LLVM data layout: POTADOS requires the MSP430 "
                           "16-bit pointer/data layout; regenerate IR with "
                           "Clang -target msp430-unknown-none (expected '" + DATA_LAYOUT + "')")


def compile_source(source: Path, output: Path, *, optimization: str = "O2",
                   llvm_build: Path | None = None, module: Path | None = None,
                   clang: str | None = None, runtime: bool = True,
                   output_format: str = "asm", verbose: bool = False,
                   extra_llc_flags: list[str] | None = None) -> Path:
    source = source.resolve()
    output = output.resolve()
    llvm_build = (llvm_build or Path(os.environ.get("LLVM_BUILD", ROOT / "build/llvm"))).resolve()
    module = module or Path(os.environ.get("POTADOS_MODULE", ROOT / "build/potados-backend" / ("Potados.dylib" if sys.platform == "darwin" else "Potados.so")))
    if not source.is_file():
        raise RuntimeError(f"source does not exist: {source}")
    if not module.is_file():
        raise RuntimeError(f"backend module is missing: {module}; run llvm/scripts/build.py backend")
    if source.suffix.lower() not in {".c", ".ll", ".bc"}:
        raise RuntimeError("input must be freestanding C (.c) or LLVM IR (.ll/.bc)")
    if source == output:
        raise RuntimeError("input and output must be different files")
    frontend = output.with_suffix(".frontend.bc" if source.suffix.lower() == ".bc" else ".frontend.ll")
    optimized = output.with_suffix(".optimized.ll")
    assembly = output if output_format == "asm" else output.with_suffix(".asm")
    if source in {optimized, assembly}:
        raise RuntimeError("an intermediate output would overwrite the input; choose a different output basename")
    opt = tool("opt", llvm_build, os.environ.get("OPT"))
    llc = tool("llc", llvm_build, os.environ.get("LLC"))
    for name, executable in (("opt", opt), ("llc", llc)):
        major = tool_version(executable)
        if major != 23:
            raise RuntimeError(f"{name} is LLVM {major}; the POTADOS module requires the pinned LLVM 23 tools")
    clang = tool("clang", llvm_build, clang or os.environ.get("CLANG")) if source.suffix.lower() == ".c" or runtime else None
    if clang and tool_version(clang) > 23:
        raise RuntimeError("the Clang frontend is newer than LLVM 23 and may emit incompatible IR")
    llvm_link = tool("llvm-link", llvm_build, os.environ.get("LLVM_LINK")) if runtime else None
    flags = extra_llc_flags or []
    output.parent.mkdir(parents=True, exist_ok=True)
    frontend_flags = ["-target", "msp430-unknown-none", "-S", "-emit-llvm", "-" + optimization,
                      "-ffreestanding", "-fno-builtin", "-fno-stack-protector", "-fno-pic",
                      "-Xclang", "-disable-llvm-passes", "-Xclang", "-disable-O0-optnone",
                      "-I", str(ROOT / "runtime")]
    if source.suffix.lower() == ".c":
        run([clang, *frontend_flags, "-o", str(frontend), str(source)], verbose)
        ir_source = frontend
    else:
        if source != frontend:
            shutil.copyfile(source, frontend)
        ir_source = frontend
    with tempfile.TemporaryDirectory(prefix="potados-compile-") as temporary:
        work = Path(temporary)
        # Decode bitcode without replacing an explicit layout, so a 64-bit
        # input cannot silently acquire the target's 16-bit pointer model.
        textual_input = ir_source
        if source.suffix.lower() == ".bc":
            textual_input = work / "input.ll"
            run([opt, "-S", "-mtriple=unknown-unknown-none", "-passes=verify",
                 str(ir_source), "-o", str(textual_input)], verbose)
        check_data_layout(textual_input.read_text(encoding="utf-8"))
        if runtime:
            runtime_ir = work / "runtime.ll"
            run([clang, *frontend_flags, "-o", str(runtime_ir), str(ROOT / "runtime/potados-runtime.c")], verbose)
            linked = work / "linked.ll"
            run([llvm_link, "-S", str(ir_source), str(runtime_ir), "-o", str(linked)], verbose)
            ir_source = linked
        # LLVM 23 removed the Os/Oz pipeline spellings. Its supported form is
        # the O2 pipeline with function size attributes, including for IR input.
        size_flags = ["-force-attribute=optsize"] if optimization in {"Os", "Oz"} else []
        if optimization == "Oz":
            size_flags.append("-force-attribute=minsize")
        pipeline = "forceattrs,default<O2>" if size_flags else f"default<{optimization}>"
        run([opt, "-S", "-mtriple=unknown-unknown-none", "-data-layout=" + DATA_LAYOUT, *size_flags,
             f"-passes={pipeline}", str(ir_source), "-o", str(optimized)], verbose)
        check_entry(optimized, flags)
        generated = work / "program.asm"
        run([llc, "-load=" + str(module.resolve()), "-march=potados_chilled", "-mcpu=generic",
             "-filetype=asm", "-verify-machineinstrs", *flags, str(optimized), "-o", str(generated)], verbose)
        text = generated.read_text(encoding="utf-8")
        if runtime:
            text += "\n" + (ROOT / "runtime/potados-mmio.asm").read_text(encoding="utf-8")
        # Assemble even for textual output: reject unresolved runtime references
        # and unsupported assembly before reporting a successful compilation.
        result = assemble(text, filename=str(assembly))
        assembly.write_text(text, encoding="utf-8")
        if output_format != "asm":
            rendered = result.render(output_format)
            if isinstance(rendered, bytes):
                output.write_bytes(rendered)
            else:
                output.write_text(rendered, encoding="utf-8")
    return output


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("-o", "--output", type=Path, required=True)
    optimization = parser.add_mutually_exclusive_group()
    for level in ("O0", "O1", "O2", "O3", "Os", "Oz"):
        optimization.add_argument("-" + level, dest="optimization", action="store_const", const=level)
    parser.set_defaults(optimization="O2")
    parser.add_argument("--format", choices=["asm", "hex", "annotated-hex", "binary"])
    parser.add_argument("--llvm-build", type=Path)
    parser.add_argument("--module", type=Path)
    parser.add_argument("--clang")
    parser.add_argument("--no-runtime", action="store_true")
    parser.add_argument("--llc-flag", action="append", default=[])
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)
    output_format = args.format or ("hex" if args.output.suffix == ".hex" else "binary" if args.output.suffix == ".bin" else "asm")
    try:
        compile_source(args.source, args.output, optimization=args.optimization,
                       llvm_build=args.llvm_build, module=args.module, clang=args.clang,
                       runtime=not args.no_runtime, output_format=output_format,
                       verbose=args.verbose, extra_llc_flags=args.llc_flag + shlex.split(os.environ.get("POTADOS_EXTRA_FLAGS", "")))
        return 0
    except (OSError, RuntimeError, AssemblerError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
        print(f"compilation failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
