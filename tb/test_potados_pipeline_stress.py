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
SIM_BUILD = PROJECT_ROOT / "build" / "sim" / "potados_pipeline_stress"

Dut = Any
Runner = Any


def _register(register_file: int, address: int) -> int:
    return (register_file >> ((7 - address) * 16)) & 0xFFFF


def _load_program(dut: Dut, program: str) -> None:
    result = assemble_file(PROGRAM_DIR / program)
    memory = dut.program_memory_inst.rom_inst.memory
    for address, word in result.words.items():
        memory[address].value = word


async def _run_program(dut: Dut, program: str, *, maximum_cycles: int = 160) -> int:
    _load_program(dut, program)
    dut.clk.value = 0
    dut.reset.value = 1
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await RisingEdge(dut.clk)
    await Timer(1, unit="ns")
    dut.reset.value = 0

    for _ in range(maximum_cycles):
        await RisingEdge(dut.clk)
        await Timer(1, unit="ns")
        if int(dut.halt_out.value):
            return int(dut.registers_out.value)

    raise AssertionError(f"CPU did not reach HALT within {maximum_cycles} cycles")


@cocotb.test()
async def repeated_addi_accumulates_on_one_register(dut: Dut) -> None:
    """Sixteen adjacent `ADDI R2, 1` operations must produce R2 == 16."""
    registers = await _run_program(dut, "stress_repeated_addi.asm")
    assert _register(registers, 0b010) == 0x0010


@cocotb.test()
async def same_register_on_both_read_ports_tracks_latest_value(dut: Dut) -> None:
    """Repeated `ADD R2, R2, R2` must consume the preceding ADD result."""
    registers = await _run_program(dut, "stress_same_register_doubling.asm")
    assert _register(registers, 0b010) == 0x1000


@cocotb.test()
async def alternating_register_dependencies_remain_independent(dut: Dut) -> None:
    """Interleave R2 increments with R3 decrements without cross-talk."""
    registers = await _run_program(dut, "stress_alternating_registers.asm")
    assert _register(registers, 0b010) == 0x0008
    assert _register(registers, 0b011) == 0x0008


@cocotb.test()
async def back_to_back_writes_commit_in_program_order(dut: Dut) -> None:
    """Three adjacent writes to R2 must leave the youngest value committed."""
    registers = await _run_program(dut, "stress_ordered_writes.asm")
    assert _register(registers, 0b010) == 0x0003


@cocotb.test()
async def dense_mixed_alu_chain_uses_each_latest_result(dut: Dut) -> None:
    """Compute R2=2+3, R3=R2*R2+1, R4=R3+R2 without NOPs."""
    registers = await _run_program(dut, "stress_dense_alu_chain.asm")
    assert _register(registers, 0b010) == 0x0005
    assert _register(registers, 0b011) == 0x001A
    assert _register(registers, 0b100) == 0x001F


def _runner() -> Runner:
    runner = get_runner(os.getenv("SIM", "verilator"))
    shutil.rmtree(SIM_BUILD, ignore_errors=True)
    runner.build(
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
def pipeline_runner() -> Runner:
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


@pytest.mark.xfail(strict=True, reason="Adjacent ADDI operations need RAW forwarding or stalls.")
def test_repeated_addi_accumulates_on_one_register(pipeline_runner: Runner) -> None:
    _run_cocotb_test(pipeline_runner, "repeated_addi_accumulates_on_one_register")


@pytest.mark.xfail(strict=True, reason="Both ALU read ports observe a stale value without RAW handling.")
def test_same_register_on_both_read_ports_tracks_latest_value(pipeline_runner: Runner) -> None:
    _run_cocotb_test(pipeline_runner, "same_register_on_both_read_ports_tracks_latest_value")


def test_alternating_register_dependencies_remain_independent(pipeline_runner: Runner) -> None:
    _run_cocotb_test(pipeline_runner, "alternating_register_dependencies_remain_independent")


def test_back_to_back_writes_commit_in_program_order(pipeline_runner: Runner) -> None:
    _run_cocotb_test(pipeline_runner, "back_to_back_writes_commit_in_program_order")


@pytest.mark.xfail(strict=True, reason="The dense mixed ALU chain needs RAW forwarding or stalls.")
def test_dense_mixed_alu_chain_uses_each_latest_result(pipeline_runner: Runner) -> None:
    _run_cocotb_test(pipeline_runner, "dense_mixed_alu_chain_uses_each_latest_result")
