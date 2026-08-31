"""Human-readable views of POTADOS pipeline registers.

The formatter accepts packed SystemVerilog stage values so it can be used both
by Cocotb traces and by a future software emulator.
"""

from __future__ import annotations


MEMORY_NONE = 0
MEMORY_LOAD = 1
MEMORY_STORE = 2

WB_NONE = 0
WB_ALU = 1
WB_MEMORY = 2
WB_FPU = 3
WB_RETURN_ADDRESS = 4


def _field(value: int, least_significant_bit: int, width: int) -> int:
    return (value >> least_significant_bit) & ((1 << width) - 1)


def _register_name(register: int) -> str:
    return "ZERO" if register == 0 else f"R{register}"


def _execute_cell(stage: int) -> str:
    """Describe an execute_stage_t packet (used for DX and EX columns)."""
    valid = _field(stage, 122, 1)
    if not valid:
        return ""

    destination = _field(stage, 18, 3)
    memory_op = _field(stage, 8, 2)
    writeback_source = _field(stage, 1, 3)
    halt = _field(stage, 0, 1)

    if halt:
        return "HALT"
    if memory_op == MEMORY_LOAD:
        return f"LD → {_register_name(destination)}"
    if memory_op == MEMORY_STORE:
        return "ST"
    if writeback_source == WB_RETURN_ADDRESS:
        return f"JAL → {_register_name(destination)}"
    if writeback_source == WB_ALU:
        return f"ALU → {_register_name(destination)}"
    if writeback_source == WB_FPU:
        return f"FPU → {_register_name(destination)}"
    return "control"


def _memory_cell(stage: int) -> str:
    """Describe a memory_stage_t packet."""
    valid = _field(stage, 74, 1)
    if not valid:
        return ""

    address = _field(stage, 58, 16)
    write_data = _field(stage, 42, 16)
    destination = _field(stage, 3, 3)
    memory_op = _field(stage, 8, 2)
    writeback_source = _field(stage, 0, 3)

    if memory_op == MEMORY_LOAD:
        return f"LD [0x{address:04X}] → {_register_name(destination)}"
    if memory_op == MEMORY_STORE:
        return f"ST 0x{write_data:04X} → [0x{address:04X}]"
    if writeback_source == WB_ALU:
        return f"ALU → {_register_name(destination)}"
    if writeback_source == WB_FPU:
        return f"FPU → {_register_name(destination)}"
    return "pass"


def _writeback_cell(stage: int, ram_load_data: int) -> str:
    """Describe a writeback_stage_t packet."""
    valid = _field(stage, 56, 1)
    if not valid:
        return ""

    destination = _field(stage, 3, 3)
    writeback_source = _field(stage, 0, 3)
    if writeback_source == WB_MEMORY:
        return f"LD 0x{ram_load_data:04X} → {_register_name(destination)}"
    if writeback_source == WB_ALU:
        return f"ALU → {_register_name(destination)}"
    if writeback_source == WB_FPU:
        return f"FPU → {_register_name(destination)}"
    if writeback_source == WB_RETURN_ADDRESS:
        return f"JAL → {_register_name(destination)}"
    return "pass"


def format_pipeline(
    decode_stage: int,
    execute_stage: int,
    memory_stage: int,
    writeback_stage: int,
    *,
    ram_load_data: int = 0,
    cell_width: int = 28,
) -> str:
    """Return a fixed-width four-stage pipeline table.

    ``decode_stage`` is the packet produced by decode and waiting to enter EX;
    it has the ``execute_stage_t`` layout, as does ``execute_stage``.
    """
    headers = ("DX", "EX", "ME", "WB")
    cells = (
        _execute_cell(decode_stage),
        _execute_cell(execute_stage),
        _memory_cell(memory_stage),
        _writeback_cell(writeback_stage, ram_load_data),
    )
    separator = " | "
    header_row = separator.join(f"{header:^{cell_width}}" for header in headers)
    value_row = separator.join(f"{cell:^{cell_width}}" for cell in cells)
    return f"{header_row}\n{value_row}"
