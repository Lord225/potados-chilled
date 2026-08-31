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
from emulator import format_pipeline
from potados_asm import assemble_file

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RTL_DIR = PROJECT_ROOT / "rtl"
PROGRAM_DIR = PROJECT_ROOT / "tb" / "programs"
SIM_BUILD = PROJECT_ROOT / "build" / "sim" / "potados_cpu_edge_cases"

Dut = Any
Runner = Any


def _register(register_file: int, address: int) -> int:
    return (register_file >> ((7 - address) * 16)) & 0xFFFF


def _ram(dut: Dut, address: int) -> int:
    return int(dut.potados_memory.ram_inst.memory[address].value)


def _dump_registers(dut: Dut) -> str:
    registers = int(dut.registers_out.value)
    out = []
    for i in range(8):
        out.append(f"R{i}={_register(registers, i):04X}")
    return ",".join(out)


def _dump_pipeline(dut: Dut) -> str:
    return format_pipeline(
        int(dut.execute_stage_next.value),
        int(dut.execute_stage.value),
        int(dut.memory_stage.value),
        int(dut.writeback_stage.value),
        ram_load_data=int(dut.ram_load_data.value),
    )


def _load_program(dut: Dut, program: str) -> None:
    result = assemble_file(PROGRAM_DIR / program)
    memory = dut.program_memory_inst.rom_inst.memory
    for address, word in result.words.items():
        memory[address].value = word


async def _reset(dut: Dut, program: str) -> None:
    _load_program(dut, program)
    dut.clk.value = 0
    dut.reset.value = 1
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await RisingEdge(dut.clk)
    await Timer(1, unit="ns")
    dut.reset.value = 0


async def _run_until_halt(dut: Dut, *, maximum_cycles: int = 96) -> None:
    for _ in range(maximum_cycles):
        await RisingEdge(dut.clk)
        await Timer(1, unit="ns")
        dut._log.info(
            "Cycle %d: HALT=%d, Registers=%s, Ram[16]=%04X\n%s",
            _,
            int(dut.halt_out.value),
            _dump_registers(dut),
            _ram(dut, 16),
            _dump_pipeline(dut),
        )
        if int(dut.halt_out.value):
            return
    raise AssertionError(f"CPU did not reach HALT within {maximum_cycles} cycles")


@cocotb.test()
async def raw_alu_dependency_uses_the_previous_result(dut: Dut) -> None:
    """LLI R2, 3; ADDI R2, 1 must produce R2 == 4 without hand-inserted NOPs."""
    await _reset(dut, "edge_raw_lli_addi.asm")
    await _run_until_halt(dut)
    assert _register(int(dut.registers_out.value), 0b010) == 0x0004


@cocotb.test()
async def store_then_load_returns_the_stored_word(dut: Dut) -> None:
    """A synchronous RAM response must be retained until LD writeback."""
    await _reset(dut, "edge_store_load.asm")
    await _run_until_halt(dut)
    assert _register(int(dut.registers_out.value), 0b100) == 0x00A5


@cocotb.test()
async def back_to_back_memory_operations_preserve_load_alignment(dut: Dut) -> None:
    """Adjacent RAM requests retain address/data alignment across WB_MEMORY."""
    await _reset(dut, "edge_memory_back_to_back.asm")
    await _run_until_halt(dut)

    registers = int(dut.registers_out.value)
    assert _ram(dut, 32) == 0x0011
    assert _ram(dut, 95) == 0x00A5
    assert _register(registers, 0b101) == 0x0011
    assert _register(registers, 0b110) == 0x00A5
    assert _register(registers, 0b111) == 0x0011


@cocotb.test()
async def alternating_store_loads_at_one_address_return_each_new_value(
    dut: Dut,
) -> None:
    """Each LD observes the preceding adjacent ST at the same RAM address."""
    await _reset(dut, "edge_memory_alternating_same_address.asm")

    observed_r6: list[int] = []
    previous_r6 = _register(int(dut.registers_out.value), 0b110)
    for _ in range(96):
        await RisingEdge(dut.clk)
        await Timer(1, unit="ns")
        current_r6 = _register(int(dut.registers_out.value), 0b110)
        if current_r6 != previous_r6:
            observed_r6.append(current_r6)
            previous_r6 = current_r6
        if int(dut.halt_out.value):
            break
    else:
        raise AssertionError("CPU did not reach HALT within 96 cycles")

    registers = int(dut.registers_out.value)
    assert _ram(dut, 64) == 0x0056
    assert observed_r6 == [0x0012, 0x0056]
    assert _register(registers, 0b111) == 0x0034


@cocotb.test()
async def push_then_pop_preserves_value_and_stack_pointer(dut: Dut) -> None:
    """PUSH/POP must use the old/decremented SP addresses and restore SP."""
    await _reset(dut, "edge_push_pop.asm")
    await _run_until_halt(dut)
    registers = int(dut.registers_out.value)
    assert _register(registers, 0b001) == 0x0020
    assert _register(registers, 0b011) == 0x00A5


@cocotb.test()
async def dense_stack_program_is_lifo_and_supports_sp_relative_memory(
    dut: Dut,
) -> None:
    """Adjacent stack operations must preserve order and restore SP exactly."""
    await _reset(dut, "edge_stack_dense_lifo.asm")
    await _run_until_halt(dut, maximum_cycles=192)

    registers = int(dut.registers_out.value)
    assert _register(registers, 0b001) == 0x0020
    assert _register(registers, 0b100) == 0x0022
    assert _register(registers, 0b101) == 0x0011
    assert _register(registers, 0b111) == 0x00A5
    assert _ram(dut, 0x20) == 0x0011
    assert _ram(dut, 0x21) == 0x0022
    assert _ram(dut, 0x1F) == 0x00A5


@cocotb.test()
async def recursive_fibonacci_restores_every_stack_frame(dut: Dut) -> None:
    """fib(6) stresses nested calls, return addresses, and dense PUSH/POP hazards."""
    await _reset(dut, "edge_recursive_fibonacci.asm")
    await _run_until_halt(dut, maximum_cycles=1024)

    registers = int(dut.registers_out.value)
    assert _register(registers, 0b001) == 0x0040
    assert _register(registers, 0b010) == 8


@cocotb.test()
async def unconditional_jump_discards_the_fallthrough_path(dut: Dut) -> None:
    """JMP must execute its target, not an already fetched fallthrough HALT."""
    await _reset(dut, "edge_jump_unconditional.asm")
    await _run_until_halt(dut)
    assert _register(int(dut.registers_out.value), 0b010) == 0x002A


@cocotb.test()
async def taken_conditional_jump_discards_the_fallthrough_path(dut: Dut) -> None:
    """JE with equal operands must select its target and flush fallthrough."""
    await _reset(dut, "edge_jump_taken.asm")
    await _run_until_halt(dut)
    assert _register(int(dut.registers_out.value), 0b100) == 0x002A


@cocotb.test()
async def not_taken_conditional_jump_keeps_the_fallthrough_path(dut: Dut) -> None:
    """JE with unequal operands must not redirect fetch to its target."""
    await _reset(dut, "edge_jump_not_taken.asm")
    await _run_until_halt(dut)
    assert _register(int(dut.registers_out.value), 0b100) == 0x0011


@cocotb.test()
async def halt_is_sticky_until_reset(dut: Dut) -> None:
    """HALT must remain observable and prevent execution from restarting."""
    await _reset(dut, "edge_halt_sticky.asm")
    await _run_until_halt(dut)
    for _ in range(4):
        await RisingEdge(dut.clk)
        await Timer(1, unit="ns")
        assert int(dut.halt_out.value) == 1


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
def edge_case_runner() -> Runner:
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
        pytest.fail(
            f"cocotb test {testcase!r} failed with exit code {exc.code}", pytrace=False
        )


def test_raw_alu_dependency_uses_the_previous_result(edge_case_runner: Runner) -> None:
    _run_cocotb_test(edge_case_runner, "raw_alu_dependency_uses_the_previous_result")


def test_store_then_load_returns_the_stored_word(edge_case_runner: Runner) -> None:
    _run_cocotb_test(edge_case_runner, "store_then_load_returns_the_stored_word")


def test_back_to_back_memory_operations_preserve_load_alignment(
    edge_case_runner: Runner,
) -> None:
    _run_cocotb_test(
        edge_case_runner, "back_to_back_memory_operations_preserve_load_alignment"
    )


def test_alternating_store_loads_at_one_address_return_each_new_value(
    edge_case_runner: Runner,
) -> None:
    _run_cocotb_test(
        edge_case_runner,
        "alternating_store_loads_at_one_address_return_each_new_value",
    )


def test_push_then_pop_preserves_value_and_stack_pointer(
    edge_case_runner: Runner,
) -> None:
    _run_cocotb_test(
        edge_case_runner, "push_then_pop_preserves_value_and_stack_pointer"
    )


def test_dense_stack_program_is_lifo_and_supports_sp_relative_memory(
    edge_case_runner: Runner,
) -> None:
    _run_cocotb_test(
        edge_case_runner,
        "dense_stack_program_is_lifo_and_supports_sp_relative_memory",
    )


def test_recursive_fibonacci_restores_every_stack_frame(
    edge_case_runner: Runner,
) -> None:
    _run_cocotb_test(
        edge_case_runner, "recursive_fibonacci_restores_every_stack_frame"
    )


def test_unconditional_jump_discards_the_fallthrough_path(
    edge_case_runner: Runner,
) -> None:
    _run_cocotb_test(
        edge_case_runner, "unconditional_jump_discards_the_fallthrough_path"
    )


def test_taken_conditional_jump_discards_the_fallthrough_path(
    edge_case_runner: Runner,
) -> None:
    _run_cocotb_test(
        edge_case_runner, "taken_conditional_jump_discards_the_fallthrough_path"
    )


def test_not_taken_conditional_jump_keeps_the_fallthrough_path(
    edge_case_runner: Runner,
) -> None:
    _run_cocotb_test(
        edge_case_runner, "not_taken_conditional_jump_keeps_the_fallthrough_path"
    )


def test_halt_is_sticky_until_reset(edge_case_runner: Runner) -> None:
    _run_cocotb_test(edge_case_runner, "halt_is_sticky_until_reset")
