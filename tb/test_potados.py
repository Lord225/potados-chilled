from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any

import cocotb
import pytest
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer
from cocotb_tools.runner import get_runner
import logging

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RTL_DIR = PROJECT_ROOT / "rtl"
ROM_IMAGE = PROJECT_ROOT / "tb" / "potados_test_program.hex"
SIM_BUILD = PROJECT_ROOT / "build" / "sim" / "potados"

Dut = Any
Runner = Any


async def _clock_cycle(dut: Dut) -> None:
    await RisingEdge(dut.clk)
    await Timer(1, unit="ns")


@cocotb.test()
async def cpu_fetches_and_decodes_a_long_instruction(dut: Dut) -> None:
    """Temporary integration test for the fetch/decode path in potados.sv.

    The program contains a long JAL, several short instruction families, a
    long conditional jump, an FPU instruction, and HALT. This checks that the
    fetch controller resumes normal sequential fetching after each long pair.
    """
    dut.clk.value = 0
    dut.reset.value = 1
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())

    await _clock_cycle(dut)
    dut.reset.value = 0

    responses: list[tuple[int, int, int]] = []
    for _ in range(32):
        await _clock_cycle(dut)
        if int(dut.instruction_ready.value):
            responses.append(
                (
                    int(dut.low_instruction_out.value),
                    int(dut.high_instruction_out.value),
                    int(dut.instruction_is_long.value),
                )
            )
    dut._log.info(
        f"CPU observed {len(responses)} instruction responses: {[f'{low:04X} {high:04X} {long}' for low, high, long in responses]}"
    )

    expected_responses = [
        (0xB085, 0x0000, 1),  # JAL low word; high word is pending
        (0xB085, 0x1234, 1),  # JAL: completed long instruction
        (0x4046, 0x0000, 0),  # ADDI
        (0x2052, 0x0000, 0),  # SH
        (0x6071, 0x0000, 0),  # LD
        (0xA021, 0x0000, 1),  # JGE low word; high word is pending
        (0xA021, 0x0008, 1),  # JGE: completed long instruction
        (0xE651, 0x0000, 0),  # FADD
        (0xF000, 0x0000, 0),  # HALT
    ]
    assert responses[: len(expected_responses)] == expected_responses


def _runner() -> Runner:
    sim = os.getenv("SIM", "verilator")
    runner = get_runner(sim)
    shutil.rmtree(SIM_BUILD, ignore_errors=True)
    runner.build(
        sources=[RTL_DIR / "potados.sv", RTL_DIR / "potados_memory.sv"],
        includes=[RTL_DIR],
        hdl_toplevel="potados",
        build_dir=SIM_BUILD,
        build_args=["-Wno-WIDTHTRUNC"],
        always=True,
        waves=os.getenv("WAVES", "0") in {"1", "true", "yes"},
    )
    shutil.copyfile(ROM_IMAGE, SIM_BUILD / "rom.hex")
    return runner


@pytest.fixture(scope="module")
def potados_runner() -> Runner:
    return _runner()


def test_cpu_fetches_and_decodes_a_long_instruction(potados_runner: Runner) -> None:
    try:
        potados_runner.test(
            hdl_toplevel="potados",
            test_module=__name__,
            build_dir=SIM_BUILD,
            test_filter="cpu_fetches_and_decodes_a_long_instruction",
        )
    except SystemExit as exc:
        pytest.fail(
            f"cocotb test 'cpu_fetches_and_decodes_a_long_instruction' failed with exit code {exc.code}",
            pytrace=False,
        )
