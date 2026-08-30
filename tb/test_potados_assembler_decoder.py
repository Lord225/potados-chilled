from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any

import cocotb
import pytest
from cocotb.triggers import Timer
from cocotb_tools.runner import get_runner
from potados_asm import assemble

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RTL_DIR = PROJECT_ROOT / "rtl"
SIM_BUILD = PROJECT_ROOT / "build" / "sim" / "potados_assembler_decoder"

Dut = Any
Runner = Any


async def _expect_decoded(
    dut: Dut,
    source: str,
    *,
    op_primary: int,
    dst: int,
    op_secondary: int,
    src_a: int,
    src_b: int,
    immediate: int = 0,
    is_long: int = 0,
) -> None:
    """Assemble one instruction, then compare every decoder output field."""
    words = assemble(source, filename="decoder_bridge.asm").dense_words()
    assert len(words) == 1 + is_long, source
    dut.instruction_low.value = words[0]
    dut.instruction_high.value = words[1] if is_long else 0
    dut.high_valid.value = is_long
    await Timer(1, unit="ns")

    decoded = int(dut.decoded_instruction.value)
    checks = (
        ("op_primary", (decoded >> 30) & 0b1111, op_primary),
        ("dst", (decoded >> 27) & 0b111, dst),
        ("op_secondary", (decoded >> 24) & 0b111, op_secondary),
        ("src_a", (decoded >> 21) & 0b111, src_a),
        ("src_b", (decoded >> 18) & 0b111, src_b),
        ("immediate", (decoded >> 2) & 0xFFFF, immediate),
        ("partialy_decoded", (decoded >> 1) & 0b1, 0),
        ("is_long", decoded & 0b1, is_long),
    )
    for field, actual, expected in checks:
        assert actual == expected, f"{source!r}: decoded.{field} == 0x{expected:X}; got 0x{actual:X}"


@cocotb.test()
async def assembled_integer_and_immediate_forms_decode_correctly(dut: Dut) -> None:
    await _expect_decoded(dut, "ADD R4, R2, R3", op_primary=0, dst=4, op_secondary=1, src_a=2, src_b=3)
    await _expect_decoded(dut, "NOT R4, R3", op_primary=0, dst=4, op_secondary=6, src_a=0, src_b=3)
    await _expect_decoded(dut, "SGE R4, R2, R3", op_primary=1, dst=4, op_secondary=0, src_a=2, src_b=3)
    await _expect_decoded(dut, "SH R2, R2, -1", op_primary=2, dst=2, op_secondary=7, src_a=2, src_b=2, immediate=0xFFFF)
    await _expect_decoded(dut, "ADDI R3, -1", op_primary=4, dst=3, op_secondary=7, src_a=7, src_b=3, immediate=0xFFFF)
    await _expect_decoded(dut, "LLI R2, 0xA5", op_primary=5, dst=2, op_secondary=5, src_a=2, src_b=2, immediate=0x00A5)


@cocotb.test()
async def assembled_memory_and_stack_forms_decode_correctly(dut: Dut) -> None:
    await _expect_decoded(dut, "LD R4, [R2 - 1]", op_primary=6, dst=4, op_secondary=7, src_a=2, src_b=4, immediate=0xFFFF)
    await _expect_decoded(dut, "ST R3, [ R2 + 1 ]", op_primary=7, dst=3, op_secondary=1, src_a=2, src_b=3, immediate=1)
    await _expect_decoded(dut, "LDSP R4, -1", op_primary=8, dst=4, op_secondary=7, src_a=7, src_b=4, immediate=0xFFFF)
    await _expect_decoded(dut, "STSP R3, 1", op_primary=9, dst=3, op_secondary=1, src_a=0, src_b=3, immediate=1)
    await _expect_decoded(dut, "PUSH R2", op_primary=12, dst=2, op_secondary=1, src_a=0, src_b=2)
    await _expect_decoded(dut, "POP R3", op_primary=12, dst=3, op_secondary=2, src_a=0, src_b=3)


@cocotb.test()
async def assembled_long_and_register_jumps_decode_correctly(dut: Dut) -> None:
    await _expect_decoded(dut, "JNE R2, R3, 0x1234", op_primary=10, dst=0, op_secondary=3, src_a=2, src_b=3, immediate=0x1234, is_long=1)
    await _expect_decoded(dut, "JMP 0x1234", op_primary=11, dst=0, op_secondary=1, src_a=0, src_b=0, immediate=0x1234, is_long=1)
    await _expect_decoded(dut, "JAL R7, 0x1234", op_primary=11, dst=7, op_secondary=2, src_a=0, src_b=7, immediate=0x1234, is_long=1)
    await _expect_decoded(dut, "JMPR R2", op_primary=13, dst=2, op_secondary=1, src_a=0, src_b=2)
    await _expect_decoded(dut, "JALR R5, R2", op_primary=13, dst=5, op_secondary=2, src_a=2, src_b=5)


@cocotb.test()
async def assembled_label_target_reaches_the_rtl_decoder(dut: Dut) -> None:
    program = assemble(
        """
        .org 0x20
        target: HALT
        .org 0
        JMP target
        """,
        filename="label_target.asm",
    )
    assert program.words == {0: 0xB040, 1: 0x0020, 0x20: 0xF000}
    dut.instruction_low.value = program.words[0]
    dut.instruction_high.value = program.words[1]
    dut.high_valid.value = 1
    await Timer(1, unit="ns")
    decoded = int(dut.decoded_instruction.value)
    assert (decoded >> 2) & 0xFFFF == 0x0020
    assert decoded & 0b1 == 1


def _runner() -> Runner:
    runner = get_runner(os.getenv("SIM", "verilator"))
    shutil.rmtree(SIM_BUILD, ignore_errors=True)
    runner.build(
        sources=[RTL_DIR / "potados_instruction_decoder.sv"],
        includes=[RTL_DIR],
        hdl_toplevel="potados_instruction_decoder",
        build_dir=SIM_BUILD,
        always=True,
        waves=os.getenv("WAVES", "0") in {"1", "true", "yes"},
    )
    return runner


@pytest.fixture(scope="module")
def assembler_decoder_runner() -> Runner:
    return _runner()


def _run_cocotb_test(runner: Runner, testcase: str) -> None:
    try:
        runner.test(
            hdl_toplevel="potados_instruction_decoder",
            test_module=__name__,
            build_dir=SIM_BUILD,
            test_filter=testcase,
        )
    except SystemExit as exc:
        pytest.fail(f"cocotb test {testcase!r} failed with exit code {exc.code}", pytrace=False)


def test_assembled_integer_and_immediate_forms_decode_correctly(assembler_decoder_runner: Runner) -> None:
    _run_cocotb_test(assembler_decoder_runner, "assembled_integer_and_immediate_forms_decode_correctly")


def test_assembled_memory_and_stack_forms_decode_correctly(assembler_decoder_runner: Runner) -> None:
    _run_cocotb_test(assembler_decoder_runner, "assembled_memory_and_stack_forms_decode_correctly")


def test_assembled_long_and_register_jumps_decode_correctly(assembler_decoder_runner: Runner) -> None:
    _run_cocotb_test(assembler_decoder_runner, "assembled_long_and_register_jumps_decode_correctly")


def test_assembled_label_target_reaches_the_rtl_decoder(assembler_decoder_runner: Runner) -> None:
    _run_cocotb_test(assembler_decoder_runner, "assembled_label_target_reaches_the_rtl_decoder")
