"""Compiler-driver contracts, independent of an LLVM build.

Fake executables exercise orchestration and diagnostics. Actual code generation
and execution are covered separately by test_backend.py and test_rtl.py.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("potados_compile_driver", ROOT / "scripts/compile.py")
assert spec and spec.loader
driver = importlib.util.module_from_spec(spec)
spec.loader.exec_module(driver)

IR = "define i16 @main() { ret i16 42 }\n"


@pytest.fixture
def fake_tools(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    binary = tmp_path / "tools"
    binary.mkdir()
    log = tmp_path / "calls.jsonl"
    config = tmp_path / "versions.json"
    config.write_text(json.dumps({"opt": 23, "llc": 23, "clang": 21, "llvm-link": 23}))
    program = "#!" + sys.executable + "\n" + r'''
import json
from pathlib import Path
import sys
name = Path(__file__).name
args = sys.argv[1:]
config = Path(__file__).parent.parent / "versions.json"
versions = json.loads(config.read_text())
major = versions[name]
if args == ["--version"]:
    print(("clang version " if name == "clang" else "LLVM version ") + str(major) + ".0.0")
    raise SystemExit(0)
with (config.parent / "calls.jsonl").open("a") as stream:
    stream.write(json.dumps([name, args]) + "\n")
out = Path(args[args.index("-o") + 1])
if name == "clang":
    function = "runtime_helper" if Path(args[-1]).name == "potados-runtime.c" else "main"
    out.write_text("define i16 @" + function + "() { ret i16 42 }\n")
elif name == "llc":
    out.write_text("LLI R2, 42\nHALT\n")
else:
    inputs = [Path(arg) for index, arg in enumerate(args) if not arg.startswith("-") and (index == 0 or args[index - 1] != "-o")]
    data = inputs[0].read_bytes()
    out.write_bytes(data if not data.startswith(b"BC") else versions.get("decoded_ir", "define i16 @main() { ret i16 42 }\n").encode())
'''
    for name in ("opt", "llc", "clang", "llvm-link"):
        executable = binary / name
        executable.write_text(program)
        executable.chmod(0o755)
        monkeypatch.setenv(name.upper().replace("-", "_"), str(executable))
    module = tmp_path / "Potados.so"
    module.write_bytes(b"fake test module")
    source = tmp_path / "input.c"
    source.write_text("unsigned short main(void) { return 42; }\n")
    return {"bin": binary, "log": log, "config": config, "module": module,
            "source": source, "out": tmp_path / "output/program.asm"}


def compile_fake(files: dict[str, Any], **kwargs: Any) -> Path:
    return driver.compile_source(files["source"], files["out"], module=files["module"], **kwargs)


def calls(files: dict[str, Any]) -> list[tuple[str, list[str]]]:
    return [tuple(json.loads(line)) for line in files["log"].read_text().splitlines()]


def test_frontend_contract_and_runtime_linking(fake_tools: dict[str, Any]) -> None:
    output = compile_fake(fake_tools)
    invocations = calls(fake_tools)
    frontend = [args for name, args in invocations if name == "clang"]
    assert len(frontend) == 2
    for args in frontend:
        assert args[args.index("-target") + 1] == "msp430-unknown-none"
        assert {"-ffreestanding", "-fno-builtin", "-fno-stack-protector", "-fno-pic", "-disable-llvm-passes", "-disable-O0-optnone"} <= set(args)
    assert any(name == "llvm-link" for name, _ in invocations)
    assert "potados_mmio_write:" in output.read_text()
    assert output.with_suffix(".frontend.ll").is_file()
    assert output.with_suffix(".optimized.ll").is_file()
    llc = next(args for name, args in invocations if name == "llc")
    assert "-verify-machineinstrs" in llc
    assert "-march=potados_chilled" in llc


@pytest.mark.parametrize("name", ["llc", "opt"])
def test_wrong_llvm_version_is_rejected_before_loading_module(fake_tools: dict[str, Any], name: str) -> None:
    versions = json.loads(fake_tools["config"].read_text())
    versions[name] = 21
    fake_tools["config"].write_text(json.dumps(versions))
    with pytest.raises(RuntimeError, match=rf"{name} is LLVM 21.*requires.*LLVM 23"):
        compile_fake(fake_tools, runtime=False)
    assert not fake_tools["log"].exists()
    assert not fake_tools["out"].parent.exists()


def test_missing_tool_has_an_actionable_error(fake_tools: dict[str, Any], monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPT", str(fake_tools["bin"] / "does-not-exist"))
    with pytest.raises(RuntimeError, match="cannot find opt.*build.py llvm"):
        compile_fake(fake_tools, runtime=False)
    assert not fake_tools["out"].parent.exists()


def test_newer_frontend_is_rejected_before_generating_ir(fake_tools: dict[str, Any]) -> None:
    versions = json.loads(fake_tools["config"].read_text())
    versions["clang"] = 25
    fake_tools["config"].write_text(json.dumps(versions))
    with pytest.raises(RuntimeError, match="frontend is newer than LLVM 23"):
        compile_fake(fake_tools, runtime=False)
    assert not fake_tools["log"].exists()


@pytest.mark.parametrize(("suffix", "contents"), [(".ll", IR.encode()), (".bc", b"BC\xC0\xDEtest bitcode")])
def test_ir_and_bitcode_inputs_are_retained_without_running_a_frontend(fake_tools: dict[str, Any], monkeypatch: pytest.MonkeyPatch, suffix: str, contents: bytes) -> None:
    source = fake_tools["source"].with_suffix(suffix)
    source.write_bytes(contents)
    fake_tools["source"] = source
    monkeypatch.setenv("CLANG", "a-frontend-that-is-not-installed")
    output = compile_fake(fake_tools, runtime=False)
    assert source.read_bytes() == contents
    assert output.with_suffix(".frontend" + suffix).read_bytes() == contents
    assert output.with_suffix(".optimized.ll").read_text() == IR
    assert all(name not in {"clang", "llvm-link"} for name, _ in calls(fake_tools))


def test_missing_entry_is_diagnosed_before_code_generation(fake_tools: dict[str, Any]) -> None:
    fake_tools["source"] = fake_tools["source"].with_suffix(".ll")
    fake_tools["source"].write_text("define i16 @helper() { ret i16 42 }\n")
    with pytest.raises(RuntimeError, match="no definition of entry function 'main'"):
        compile_fake(fake_tools, runtime=False)
    assert all(name != "llc" for name, _ in calls(fake_tools))
    assert fake_tools["out"].with_suffix(".optimized.ll").is_file()


@pytest.mark.parametrize("flags", [["-potados-entry=start"], ["-potados-no-startup"]])
def test_custom_entry_and_library_modules_are_allowed(fake_tools: dict[str, Any], flags: list[str]) -> None:
    fake_tools["source"] = fake_tools["source"].with_suffix(".ll")
    fake_tools["source"].write_text("define i16 @start() { ret i16 42 }\n")
    compile_fake(fake_tools, runtime=False, extra_llc_flags=flags)


@pytest.mark.parametrize(("level", "attributes"), [("Os", {"-force-attribute=optsize"}), ("Oz", {"-force-attribute=optsize", "-force-attribute=minsize"})])
def test_size_optimization_uses_supported_llvm23_pipeline(fake_tools: dict[str, Any], level: str, attributes: set[str]) -> None:
    compile_fake(fake_tools, runtime=False, optimization=level)
    args = next(args for name, args in calls(fake_tools) if name == "opt")
    assert "-passes=forceattrs,default<O2>" in args
    assert attributes <= set(args)


def test_intermediate_names_cannot_overwrite_the_original_input(fake_tools: dict[str, Any]) -> None:
    source = fake_tools["out"].with_suffix(".optimized.ll")
    source.parent.mkdir()
    source.write_text(IR)
    fake_tools["source"] = source
    with pytest.raises(RuntimeError, match="intermediate output would overwrite the input"):
        compile_fake(fake_tools, runtime=False)
    assert source.read_text() == IR
    assert not fake_tools["log"].exists()


@pytest.mark.parametrize(("output_format", "expected"), [("hex", b"5542\nF000\n"), ("binary", bytes.fromhex("5542 F000"))])
def test_machine_output_is_encoded_by_the_project_assembler(fake_tools: dict[str, Any], output_format: str, expected: bytes) -> None:
    fake_tools["out"] = fake_tools["out"].with_suffix(".hex" if output_format == "hex" else ".bin")
    output = compile_fake(fake_tools, runtime=False, output_format=output_format)
    assert output.read_bytes() == expected
    assert output.with_suffix(".asm").read_text() == "LLI R2, 42\nHALT\n"


@pytest.mark.parametrize("suffix", [".ll", ".bc"])
def test_incompatible_pointer_layout_is_rejected_before_optimization(fake_tools: dict[str, Any], suffix: str) -> None:
    text = 'target datalayout = "e-p:64:64"\n' + IR
    fake_tools["source"] = fake_tools["source"].with_suffix(suffix)
    fake_tools["source"].write_bytes(text.encode() if suffix == ".ll" else b"BCfake bitcode")
    versions = json.loads(fake_tools["config"].read_text())
    versions["decoded_ir"] = text
    fake_tools["config"].write_text(json.dumps(versions))
    with pytest.raises(RuntimeError, match="incompatible LLVM data layout.*16-bit pointer/data layout"):
        compile_fake(fake_tools, runtime=False)
    invocations = calls(fake_tools) if fake_tools["log"].exists() else []
    assert all(name == "opt" and "-passes=verify" in args for name, args in invocations)


@pytest.mark.parametrize("declared_layout", ["", 'target datalayout = "' + driver.DATA_LAYOUT + '"\n'])
def test_optimizer_receives_the_target_layout_before_processing_ir(fake_tools: dict[str, Any], declared_layout: str) -> None:
    fake_tools["source"] = fake_tools["source"].with_suffix(".ll")
    fake_tools["source"].write_text(declared_layout + IR)
    compile_fake(fake_tools, runtime=False)
    args = next(args for name, args in calls(fake_tools) if name == "opt")
    assert "-data-layout=" + driver.DATA_LAYOUT in args
