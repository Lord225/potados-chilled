from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any

import cocotb
import pytest
from cocotb.triggers import Timer
from cocotb_tools.runner import get_runner

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RTL_DIR = PROJECT_ROOT / "rtl"
SIM_BUILD = PROJECT_ROOT / "build" / "sim" / "potados_instruction_decoder"

Dut = Any
Runner = Any


async def _expect(
    dut: Dut,
    instruction_low: int,
    *,
    op_primary: int,
    dst: int,
    op_secondary: int,
    src_a: int,
    src_b: int,
    immediate: int,
    partialy_decoded: int = 0,
    is_long: int = 0,
    instruction_high: int = 0,
    high_valid: int = 0,
) -> None:
    """Drive one instruction and compare every decoded output field."""
    dut.instruction_low.value = instruction_low
    dut.instruction_high.value = instruction_high
    dut.high_valid.value = high_valid
    await Timer(1, unit="ns")

    decoded = int(dut.decoded_instruction.value)
    assert (decoded >> 30) & 0b1111 == op_primary
    assert (decoded >> 27) & 0b111 == dst
    assert (decoded >> 24) & 0b111 == op_secondary
    assert (decoded >> 21) & 0b111 == src_a
    assert (decoded >> 18) & 0b111 == src_b
    assert (decoded >> 2) & 0xFFFF == immediate
    assert (decoded >> 1) & 0b1 == partialy_decoded
    assert decoded & 0b1 == is_long


@cocotb.test()
async def flat_fixed_instruction_decoding(dut: Dut) -> None:
    # NOP: 0b0000_000_000_000_000
    await _expect(
        dut, 0b0000_000_000_000_000,
        op_primary=0b0000, dst=0b000, op_secondary=0b000,
        src_a=0b000, src_b=0b000, immediate=0x0000,
    )

    # ADD R5, R4, R5: 0b0000_101_001_100_101
    await _expect(
        dut, 0b0000_101_001_100_101,
        op_primary=0b0000, dst=0b101, op_secondary=0b001,
        src_a=0b100, src_b=0b101, immediate=0x0000,
    )

    # SGE R6, R7, R2: 0b0001_110_000_111_010
    await _expect(
        dut, 0b0001_110_000_111_010,
        op_primary=0b0001, dst=0b110, op_secondary=0b000,
        src_a=0b111, src_b=0b010, immediate=0x0000,
    )

    # POP R6: 0b1100_000_010_000_110
    await _expect(
        dut, 0b1100_000_010_000_110,
        op_primary=0b1100, dst=0b110, op_secondary=0b010,
        src_a=0b000, src_b=0b110, immediate=0x0000,
    )

    # JALR R1 -> R7: 0b1101_000_000_010_111
    await _expect(
        dut, 0b1101_000_000_010_111,
        op_primary=0b1101, dst=0b111, op_secondary=0b000,
        src_a=0b010, src_b=0b111, immediate=0x0000,
    )

    # FADD R3, R2, R1: 0b1110_011_001_010_001
    await _expect(
        dut, 0b1110_011_001_010_001,
        op_primary=0b1110, dst=0b011, op_secondary=0b001,
        src_a=0b010, src_b=0b001, immediate=0x0000,
    )

    # HALT: 0b1111_010_110_100_011
    await _expect(
        dut, 0b1111_010_110_100_011,
        op_primary=0b1111, dst=0b000, op_secondary=0b110,
        src_a=0b100, src_b=0b011, immediate=0xF5A3,
    )


@cocotb.test()
async def flat_immediate_edge_case_decoding(dut: Dut) -> None:
    # SH: canonical signed IMM5 values occupy bits [10:6]; bit [11] is reserved.
    await _expect(dut, 0b0010_000001_010_010, op_primary=0b0010, dst=0b010, op_secondary=0b001, src_a=0b010, src_b=0b010, immediate=0x0001)
    await _expect(dut, 0b0010_011111_010_010, op_primary=0b0010, dst=0b010, op_secondary=0b111, src_a=0b010, src_b=0b010, immediate=0xFFFF)
    await _expect(dut, 0b0010_001111_010_010, op_primary=0b0010, dst=0b010, op_secondary=0b111, src_a=0b010, src_b=0b010, immediate=0x000F)
    await _expect(dut, 0b0010_010000_010_010, op_primary=0b0010, dst=0b010, op_secondary=0b000, src_a=0b010, src_b=0b010, immediate=0xFFF0)
    # A noncanonical word with reserved bit [11] set still decodes from IMM5.
    await _expect(dut, 0b0010_111111_010_010, op_primary=0b0010, dst=0b010, op_secondary=0b111, src_a=0b010, src_b=0b010, immediate=0xFFFF)

    # ASH uses the same signed 5-bit immediate field.
    await _expect(dut, 0b0011_000001_010_010, op_primary=0b0011, dst=0b010, op_secondary=0b001, src_a=0b010, src_b=0b010, immediate=0x0001)
    await _expect(dut, 0b0011_011111_010_010, op_primary=0b0011, dst=0b010, op_secondary=0b111, src_a=0b010, src_b=0b010, immediate=0xFFFF)
    await _expect(dut, 0b0011_001111_010_010, op_primary=0b0011, dst=0b010, op_secondary=0b111, src_a=0b010, src_b=0b010, immediate=0x000F)
    await _expect(dut, 0b0011_010000_010_010, op_primary=0b0011, dst=0b010, op_secondary=0b000, src_a=0b010, src_b=0b010, immediate=0xFFF0)

    # ADDI: immediate 1, -1, maximum (255), and minimum (-256).
    await _expect(dut, 0b0100_000001_000_110, op_primary=0b0100, dst=0b110, op_secondary=0b001, src_a=0b000, src_b=0b110, immediate=0x0001)
    await _expect(dut, 0b0100_111111_111_111, op_primary=0b0100, dst=0b111, op_secondary=0b111, src_a=0b111, src_b=0b111, immediate=0xFFFF)
    await _expect(dut, 0b0100_111111_011_110, op_primary=0b0100, dst=0b110, op_secondary=0b111, src_a=0b011, src_b=0b110, immediate=0x00FF)
    await _expect(dut, 0b0100_000000_100_010, op_primary=0b0100, dst=0b010, op_secondary=0b000, src_a=0b100, src_b=0b010, immediate=0xFF00)

    # LLI/LUI, LDSP, and STSP use the same signed 9-bit immediate extraction.
    await _expect(dut, 0b0101_000001_000_110, op_primary=0b0101, dst=0b110, op_secondary=0b001, src_a=0b000, src_b=0b110, immediate=0x0001)
    await _expect(dut, 0b0101_111111_111_111, op_primary=0b0101, dst=0b111, op_secondary=0b111, src_a=0b111, src_b=0b111, immediate=0xFFFF)
    await _expect(dut, 0b1000_111111_011_110, op_primary=0b1000, dst=0b110, op_secondary=0b111, src_a=0b011, src_b=0b110, immediate=0x00FF)
    await _expect(dut, 0b1001_000000_100_010, op_primary=0b1001, dst=0b010, op_secondary=0b000, src_a=0b100, src_b=0b010, immediate=0xFF00)

    # LD: displacement 1, -1, maximum (31), and minimum (-32).
    await _expect(dut, 0b0110_000001_110_001, op_primary=0b0110, dst=0b001, op_secondary=0b001, src_a=0b110, src_b=0b001, immediate=0x0001)
    await _expect(dut, 0b0110_111111_110_001, op_primary=0b0110, dst=0b001, op_secondary=0b111, src_a=0b110, src_b=0b001, immediate=0xFFFF)
    await _expect(dut, 0b0110_011111_110_001, op_primary=0b0110, dst=0b001, op_secondary=0b111, src_a=0b110, src_b=0b001, immediate=0x001F)
    await _expect(dut, 0b0110_100000_110_001, op_primary=0b0110, dst=0b001, op_secondary=0b000, src_a=0b110, src_b=0b001, immediate=0xFFE0)

    # ST uses the same signed 6-bit displacement field.
    await _expect(dut, 0b0111_000001_110_001, op_primary=0b0111, dst=0b001, op_secondary=0b001, src_a=0b110, src_b=0b001, immediate=0x0001)
    await _expect(dut, 0b0111_111111_110_001, op_primary=0b0111, dst=0b001, op_secondary=0b111, src_a=0b110, src_b=0b001, immediate=0xFFFF)
    await _expect(dut, 0b0111_011111_110_001, op_primary=0b0111, dst=0b001, op_secondary=0b111, src_a=0b110, src_b=0b001, immediate=0x001F)
    await _expect(dut, 0b0111_100000_110_001, op_primary=0b0111, dst=0b001, op_secondary=0b000, src_a=0b110, src_b=0b001, immediate=0xFFE0)


@cocotb.test()
async def flat_long_instruction_decoding(dut: Dut) -> None:
    # JGE R4, R1, 0xBEEF with no second word yet.
    await _expect(
        dut, 0b1010_000_000_100_001,
        op_primary=0b1010, dst=0b000, op_secondary=0b000,
        src_a=0b100, src_b=0b001, immediate=0xBEEF,
        partialy_decoded=1, is_long=1, instruction_high=0xBEEF,
    )

    # The same JGE once its second word is valid.
    await _expect(
        dut, 0b1010_000_000_100_001,
        op_primary=0b1010, dst=0b000, op_secondary=0b000,
        src_a=0b100, src_b=0b001, immediate=0xBEEF,
        partialy_decoded=0, is_long=1, instruction_high=0xBEEF, high_valid=1,
    )

    # JAL 0x1234, return address in R5.
    await _expect(
        dut, 0b1011_000_010_000_101,
        op_primary=0b1011, dst=0b101, op_secondary=0b010,
        src_a=0b000, src_b=0b101, immediate=0x1234,
        partialy_decoded=0, is_long=1, instruction_high=0x1234, high_valid=1,
    )


def _runner() -> Runner:
    sim = os.getenv("SIM", "verilator")
    runner = get_runner(sim)
    shutil.rmtree(SIM_BUILD, ignore_errors=True)
    runner.build(
        sources=[RTL_DIR / "potados.sv"],
        includes=[RTL_DIR],
        hdl_toplevel="potados_instruction_decoder",
        build_dir=SIM_BUILD,
        build_args=["-Wno-WIDTHTRUNC"],
        always=True,
        waves=os.getenv("WAVES", "0") in {"1", "true", "yes"},
    )
    return runner


@pytest.fixture(scope="module")
def instruction_decoder_runner() -> Runner:
    return _runner()


def _run_cocotb_test(runner: Runner, testcase: str) -> None:
    """Run one named Cocotb coroutine as one Pytest test."""
    try:
        runner.test(
            hdl_toplevel="potados_instruction_decoder",
            test_module=__name__,
            build_dir=SIM_BUILD,
            test_filter=testcase,
        )
    except SystemExit as exc:
        pytest.fail(
            f"cocotb test {testcase!r} failed with exit code {exc.code}",
            pytrace=False,
        )


def test_flat_fixed_instruction_decoding(instruction_decoder_runner: Runner) -> None:
    _run_cocotb_test(instruction_decoder_runner, "flat_fixed_instruction_decoding")


def test_flat_immediate_edge_case_decoding(
    instruction_decoder_runner: Runner,
) -> None:
    _run_cocotb_test(
        instruction_decoder_runner,
        "flat_immediate_edge_case_decoding",
    )


def test_flat_long_instruction_decoding(instruction_decoder_runner: Runner) -> None:
    _run_cocotb_test(instruction_decoder_runner, "flat_long_instruction_decoding")
