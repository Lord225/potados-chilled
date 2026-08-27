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

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RTL_DIR = PROJECT_ROOT / "rtl"
ROM_IMAGE = PROJECT_ROOT / "rom.hex"
SIM_BUILD = PROJECT_ROOT / "build" / "sim" / "potados_program_memory"

Dut = Any
Runner = Any

ROM_WORDS = (0x1234, 0xABCD, 0x0001, 0xCAFE, 0x0F0F, 0xDEAD, 0xBEEF, 0x0000)


async def _clock_cycle(dut: Dut) -> None:
    await RisingEdge(dut.clk)
    await Timer(1, unit="ns")


async def _idle(dut: Dut) -> None:
    dut.request_long_instruction.value = 0
    dut.request_next_instruction.value = 0
    dut.jump_enable.value = 0
    await Timer(1, unit="ns")


async def _reset(dut: Dut) -> None:
    dut.reset.value = 1
    dut.request_long_instruction.value = 0
    dut.request_next_instruction.value = 0
    dut.jump_address.value = 0
    dut.jump_enable.value = 0
    await _clock_cycle(dut)
    assert int(dut.low_valid.value) == 0
    dut.reset.value = 0

    # Allow the synchronous ROM to load address zero.
    await _clock_cycle(dut)


async def _fetch_short(dut: Dut, expected_word: int) -> None:
    """Request one instruction and wait for its registered response."""
    dut.request_next_instruction.value = 1
    await _clock_cycle(dut)
    dut.request_next_instruction.value = 0

    assert int(dut.low_valid.value) == 1
    assert int(dut.low_instruction.value) == expected_word
    assert int(dut.high_instruction.value) == 0
    # The response is held for one cycle; return with the fetch controller idle
    # so the caller can issue the next command.
    await _clock_cycle(dut)


async def _fetch_long(
    dut: Dut, expected_low_word: int, expected_high_word: int
) -> None:
    """Request one long instruction and wait for its registered response."""
    dut.request_long_instruction.value = 1
    await _clock_cycle(dut)
    dut.request_long_instruction.value = 0

    assert int(dut.low_valid.value) == 1
    assert int(dut.low_instruction.value) == expected_low_word
    assert int(dut.high_instruction.value) == expected_high_word
    await _clock_cycle(dut)


@cocotb.test()
async def reset_and_short_instruction_fetch(dut: Dut) -> None:
    dut.clk.value = 0
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await _reset(dut)

    await _fetch_short(dut, ROM_WORDS[0])
    await _fetch_short(dut, expected_word=ROM_WORDS[1])
    await _fetch_short(dut, expected_word=ROM_WORDS[2])


@cocotb.test()
async def reset_and_long_instruction_fetch(dut: Dut) -> None:
    dut.clk.value = 0
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await _reset(dut)

    await _fetch_short(dut, ROM_WORDS[0])
    await _fetch_long(
        dut, expected_low_word=ROM_WORDS[0], expected_high_word=ROM_WORDS[1]
    )
    await _fetch_short(dut, expected_word=ROM_WORDS[2])


@cocotb.test()
async def reset_and_jump(dut: Dut) -> None:
    dut.clk.value = 0
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await _reset(dut)

    await _fetch_short(dut, ROM_WORDS[0])
    await _fetch_short(dut, expected_word=ROM_WORDS[1])

    dut.jump_address.value = 4
    dut.jump_enable.value = 1
    await _clock_cycle(dut)
    dut.jump_enable.value = 0

    await _fetch_short(dut, expected_word=ROM_WORDS[4])


@cocotb.test()
async def stress_mixed_short_and_long_fetches(dut: Dut) -> None:
    """Repeated long fetches must not duplicate or skip adjacent ROM words."""
    dut.clk.value = 0
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await _reset(dut)

    # A long response repeats its previously fetched low word and supplies the
    # next ROM word as its high word. Repeat this pattern across the image.
    await _fetch_short(dut, ROM_WORDS[0])
    await _fetch_long(dut, ROM_WORDS[0], ROM_WORDS[1])
    await _fetch_short(dut, ROM_WORDS[2])
    await _fetch_long(dut, ROM_WORDS[2], ROM_WORDS[3])
    await _fetch_short(dut, ROM_WORDS[4])
    await _fetch_long(dut, ROM_WORDS[4], ROM_WORDS[5])
    await _fetch_short(dut, ROM_WORDS[6])
    await _fetch_short(dut, ROM_WORDS[7])

    # Return to the start and verify that the ROM/fetch pipeline was reset to
    # the requested address rather than retaining an old prefetched word.
    dut.jump_address.value = 0
    dut.jump_enable.value = 1
    await _clock_cycle(dut)
    dut.jump_enable.value = 0
    await _fetch_short(dut, ROM_WORDS[0])


@cocotb.test()
async def reset_cancels_a_pending_long_fetch(dut: Dut) -> None:
    """Reset must clear the saved low word and long-fetch-valid state."""
    dut.clk.value = 0
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await _reset(dut)

    await _fetch_short(dut, ROM_WORDS[0])

    # Start a long fetch, then reset before another instruction can be used.
    dut.request_long_instruction.value = 1
    await _clock_cycle(dut)
    dut.request_long_instruction.value = 0
    dut.reset.value = 1
    await _clock_cycle(dut)
    assert int(dut.low_valid.value) == 0
    assert int(dut.low_instruction.value) == 0
    assert int(dut.high_instruction.value) == 0

    dut.reset.value = 0
    await _clock_cycle(dut)
    await _fetch_short(dut, ROM_WORDS[0])


def _runner() -> Runner:
    sim = os.getenv("SIM", "verilator")
    runner = get_runner(sim)
    shutil.rmtree(SIM_BUILD, ignore_errors=True)
    runner.build(
        sources=[RTL_DIR / "potados_memory.sv"],
        hdl_toplevel="potados_program_memory",
        build_dir=SIM_BUILD,
        always=True,
        waves=os.getenv("WAVES", "0") in {"1", "true", "yes"},
    )
    shutil.copyfile(ROM_IMAGE, SIM_BUILD / "rom.hex")
    return runner


@pytest.fixture(scope="module")
def program_memory_runner() -> Runner:
    return _runner()


def _run_cocotb_test(runner: Runner, testcase: str) -> None:
    try:
        runner.test(
            hdl_toplevel="potados_program_memory",
            test_module=__name__,
            build_dir=SIM_BUILD,
            test_filter=testcase,
        )
    except SystemExit as exc:
        pytest.fail(
            f"cocotb test {testcase!r} failed with exit code {exc.code}", pytrace=False
        )


def test_reset_and_short_instruction_fetch(program_memory_runner: Runner) -> None:
    _run_cocotb_test(program_memory_runner, "reset_and_short_instruction_fetch")


def test_reset_and_long_instruction_fetch(program_memory_runner: Runner) -> None:
    _run_cocotb_test(program_memory_runner, "reset_and_long_instruction_fetch")


def test_reset_and_jump(program_memory_runner: Runner) -> None:
    _run_cocotb_test(program_memory_runner, "reset_and_jump")


def test_stress_mixed_short_and_long_fetches(program_memory_runner: Runner) -> None:
    _run_cocotb_test(program_memory_runner, "stress_mixed_short_and_long_fetches")


def test_reset_cancels_a_pending_long_fetch(program_memory_runner: Runner) -> None:
    _run_cocotb_test(program_memory_runner, "reset_cancels_a_pending_long_fetch")
