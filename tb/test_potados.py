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
from potados_asm import assemble_file

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RTL_DIR = PROJECT_ROOT / "rtl"
PROGRAM_DIR = PROJECT_ROOT / "tb" / "programs"
SIM_BUILD = PROJECT_ROOT / "build" / "sim" / "potados"

Dut = Any
Runner = Any


def _register(register_file: int, address: int) -> int:
    """Return one architectural register from packed register_file_t."""
    return (register_file >> ((7 - address) * 16)) & 0xFFFF


def _load_program(dut: Dut, program: str) -> None:
    result = assemble_file(PROGRAM_DIR / program)
    memory = dut.program_memory_inst.rom_inst.memory
    for address, word in result.words.items():
        memory[address].value = word


async def _reset_and_run_program(dut: Dut, program: str, *, maximum_cycles: int = 96) -> None:
    _load_program(dut, program)
    dut.clk.value = 0
    dut.reset.value = 1
    dut.io_read_data.value = 0
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())

    await RisingEdge(dut.clk)
    await Timer(1, unit="ns")
    dut.reset.value = 0

    for _ in range(maximum_cycles):
        await RisingEdge(dut.clk)
        await Timer(1, unit="ns")
        if int(dut.potados_done.value):
            return

    raise AssertionError(f"CPU did not reach HALT within {maximum_cycles} cycles")


@cocotb.test()
async def cpu_executes_one_lli_instruction(dut: Dut) -> None:
    """LLI R2, 7 writes its ALU result through the whole pipeline."""
    await _reset_and_run_program(dut, "one_lli_then_halt.asm")

    registers = int(dut.registers_out.value)
    assert _register(registers, 0b010) == 0x0007


@cocotb.test()
async def cpu_executes_two_independent_writes_and_an_add(dut: Dut) -> None:
    """Run LLI R2, 7; LLI R3, 9; ADD R4, R2, R3 with drain NOPs.

    The NOPs intentionally separate dependent instructions.  This is a
    straight-through pipeline test, not a hazard or forwarding test.
    """
    await _reset_and_run_program(dut, "two_lli_and_add_then_halt.asm")

    registers = int(dut.registers_out.value)
    assert _register(registers, 0b010) == 0x0007
    assert _register(registers, 0b011) == 0x0009
    assert _register(registers, 0b100) == 0x0010


@cocotb.test()
async def cpu_executes_hazard_free_multiply_accumulate(dut: Dut) -> None:
    """Compute (3 * 4) + (5 * 6) and write 42 to R2.

    NOP drain slots make every read occur after its producer has reached
    writeback.  This is intentionally a functional datapath regression rather
    than a test of the not-yet-implemented forwarding/stall mechanism.
    """
    await _reset_and_run_program(dut, "multiply_accumulate_then_halt.asm")
    registers = int(dut.registers_out.value)
    assert _register(registers, 0b100) == 0x000C
    assert _register(registers, 0b111) == 0x001E
    assert _register(registers, 0b010) == 0x002A


def _runner() -> Runner:
    sim = os.getenv("SIM", "verilator")
    runner = get_runner(sim)
    shutil.rmtree(SIM_BUILD, ignore_errors=True)
    runner.build(
        # potados.sv includes its component RTL files. Listing them again
        # would define the memory modules twice.
        sources=[RTL_DIR / "potados.sv"],
        includes=[RTL_DIR],
        hdl_toplevel="potados",
        build_dir=SIM_BUILD,
        parameters={"LOAD_ROM_FILE": 0},
        build_args=["-Wno-WIDTHTRUNC"],
        always=True,
        waves=os.getenv("WAVES", "0") in {"1", "true", "yes"},
    )
    return runner


@pytest.fixture(scope="module")
def potados_runner() -> Runner:
    return _runner()


def _run_cocotb_test(runner: Runner, testcase: str) -> None:
    try:
        runner.test(
            hdl_toplevel="potados",
            test_module=__name__,
            build_dir=SIM_BUILD,
            test_filter=testcase,
        )
    except SystemExit as exc:
        pytest.fail(f"cocotb test {testcase!r} failed with exit code {exc.code}", pytrace=False)


def test_cpu_executes_one_lli_instruction(potados_runner: Runner) -> None:
    _run_cocotb_test(potados_runner, "cpu_executes_one_lli_instruction")


def test_cpu_executes_two_independent_writes_and_an_add(potados_runner: Runner) -> None:
    _run_cocotb_test(
        potados_runner,
        "cpu_executes_two_independent_writes_and_an_add",
    )


def test_cpu_executes_hazard_free_multiply_accumulate(potados_runner: Runner) -> None:
    _run_cocotb_test(
        potados_runner,
        "cpu_executes_hazard_free_multiply_accumulate",
    )
