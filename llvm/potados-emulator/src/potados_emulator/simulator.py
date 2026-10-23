"""cocotb control loop for the actual POTADOS RTL simulation wrapper.

Python provides reset, clocks, debug access, and synchronous peripheral fixtures.
Instruction decode, execution, hazards, memory transactions and writeback all
come from potados.sv and its included RTL modules.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import socket
from typing import Any

import cocotb
from cocotb.triggers import Timer


class Simulation:
    def __init__(self, dut: Any) -> None:
        self.dut = dut
        self.cycles = 0
        self.instructions = 0
        self.low = 0
        self.high = 0x7FFF
        self.io: dict[int, int] = {}
        self.io_writes: list[list[int]] = []
        self.written: set[int] = set()
        self.rom = dut.cpu.program_memory_inst.rom_inst.memory
        self.ram = dut.cpu.potados_memory.ram_inst.memory
        self._cleared = False
        self.program: dict[int, int] = {}

    def registers(self) -> list[int]:
        packed = int(self.dut.registers_out.value)
        return [0] + [(packed >> ((7 - address) * 16)) & 0xFFFF for address in range(1, 8)]

    def snapshot(self, include_ram: bool = True) -> dict[str, Any]:
        d = self.dut
        state: dict[str, Any] = {
            "backend": "cocotb-verilator", "rtl_source": os.environ.get("POTADOS_RTL_SOURCE", "potados.sv"),
            "registers": self.registers(),
            "pc": int(d.fetch_pc.value) if int(d.fetch_valid.value) or int(d.done.value) else int(d.next_fetch_pc.value),
            "cycles": self.cycles, "steps": self.cycles,
            "instructions": self.instructions, "halted": bool(int(d.done.value)),
            "io": self.io, "io_writes": self.io_writes,
            "fetch_valid": bool(int(d.fetch_valid.value)),
            "instruction_accepted": bool(int(d.instruction_accepted.value)),
            "pipeline": {"execute": int(d.execute_packet.value),
                         "memory": int(d.memory_packet.value),
                         "writeback": int(d.writeback_packet.value)},
        }
        if include_ram:
            values = {str(address): int(self.ram[address].value) for address in self.written}
            state["ram"] = {address: value for address, value in values.items() if value}
        return state

    async def reset(self, request: dict[str, Any]) -> None:
        self.low, self.high = int(request.get("ram_low", self.low)), int(request.get("ram_high", self.high))
        self.io = {int(a): int(v) & 0xFFFF for a, v in request.get("io", {}).items()}
        self.io_writes = []
        d = self.dut
        d.clk.value = 0
        d.reset.value = 1
        d.io_read_data.value = 0
        if "program" in request:
            self.program = {int(a): int(v) for a, v in request["program"].items()}
        for address in range(0x8000):
            self.rom[address].value = 0xF000
        for address, word in self.program.items():
            self.rom[int(address)].value = int(word)
        # Deterministic testbench initialization writes the real HDL memory.
        # It is not a substitute data-memory model used during execution.
        for address in (range(self.low, self.high + 1) if not self._cleared else self.written):
            self.ram[address].value = 0
        self._cleared = True
        self.written.clear()
        await Timer(1, unit="ns")
        d.clk.value = 1
        await Timer(1, unit="ns")
        d.clk.value = 0
        d.reset.value = 0
        await Timer(1, unit="ns")
        d.cpu.registers_inst.regs.value = (int(request.get("initial_sp", 0)) & 0xFFFF) << 96
        d.cpu.program_memory_inst.pc.value = int(request.get("pc", 0)) & 0xFFFF
        await Timer(1, unit="ns")
        self.cycles = self.instructions = 0

    async def cycle(self, trace: bool) -> dict[str, Any] | None:
        d = self.dut
        before = self.registers() if trace else None
        accepted = bool(int(d.instruction_accepted.value))
        if accepted:
            self.instructions += 1
        pre: dict[str, Any] = {}
        commit = int(d.cpu.register_write_request.value) if trace else 0
        stack_op = int(d.cpu.stack_pointer_request.value) & 3 if trace else 0
        if trace:
            pre = {"pc": int(d.fetch_pc.value) if int(d.fetch_valid.value) else int(d.next_fetch_pc.value),
                   "fetch_valid": bool(int(d.fetch_valid.value)), "instruction_accepted": accepted, "fetch_accepted": accepted,
                   "fetch_low": int(d.fetch_low.value), "fetch_high": int(d.fetch_high.value),
                   "fetch_high_valid": bool(int(d.fetch_high_valid.value)),
                   "execute_valid": bool(int(d.execute_valid.value)), "execute_pc": int(d.execute_pc.value),
                   "jump_enable": bool(int(d.jump_enable.value)), "jump_address": int(d.jump_address.value)}
        load, store = bool(int(d.memory_read_enable.value)), bool(int(d.memory_write_enable.value))
        address = int(d.memory_address.value) if load or store else 0
        is_io = not self.low <= address <= self.high
        data = int(d.memory_write_data.value) if store else 0
        # Match the synchronous external-peripheral contract. The old response
        # remains visible to writeback until this rising edge; only then does
        # the newly accepted I/O load acquire its next response.
        response = self.io.get(address, 0) if load and is_io else 0
        if store:
            if is_io:
                self.io[address] = data
                self.io_writes.append([address, data])
            else:
                self.written.add(address)
        d.clk.value = 1
        await Timer(1, unit="ns")
        d.io_read_data.value = response
        d.clk.value = 0
        await Timer(1, unit="ns")
        self.cycles += 1
        if not trace:
            return None
        after = self.registers()
        destination = (commit >> 16) & 7
        committed = [[destination, commit & 0xFFFF]] if (commit >> 19) & 1 and destination else []
        if stack_op and not ((commit >> 19) & 1 and destination == 1):
            committed.append([1, after[1]])
        return {"cycle": self.cycles, "index": self.cycles,
                **pre, "next_pc": int(d.pc.value), "registers": after,
                "register_writes": committed,
                "register_changes": [[i, value] for i, value in enumerate(after) if value != before[i]],
                "writeback": {"enable": bool((commit >> 19) & 1), "address": destination, "data": commit & 0xFFFF, "stack_operation": stack_op},
                "memory_reads": [{"address": address, "value": int(d.memory_read_data.value), "io": is_io}] if load else [],
                "memory_writes": [{"address": address, "value": data, "io": is_io}] if store else [],
                "halted": bool(int(d.done.value)),
                "pipeline": {"execute": int(d.execute_packet.value), "memory": int(d.memory_packet.value), "writeback": int(d.writeback_packet.value)}}

    async def command(self, request: dict[str, Any]) -> dict[str, Any]:
        op = request.get("op")
        events: list[dict[str, Any]] = []
        reason = None
        value = None
        if op == "reset":
            await self.reset(request)
        elif op in {"run", "tick"}:
            count = int(request.get("max_cycles", 1_000_000) if op == "run" else request.get("count", 1))
            if count < 0:
                raise ValueError("cycle count must not be negative")
            breakpoints = {int(a) for a in request.get("breakpoints", [])}
            trace_path = request.get("trace_path")
            trace = bool(request.get("trace")) or bool(trace_path)
            output = Path(trace_path).open("w", encoding="utf-8") if trace_path else None
            try:
                for iteration in range(count):
                    if int(self.dut.done.value):
                        reason = "halt"
                        break
                    if (op == "run" and breakpoints and
                        not (iteration == 0 and request.get("ignore_current_breakpoint")) and
                        int(self.dut.instruction_accepted.value) and int(self.dut.fetch_pc.value) in breakpoints):
                        reason = "breakpoint"
                        break
                    event = await self.cycle(trace)
                    if event is not None:
                        if output is not None:
                            output.write(json.dumps(event) + "\n")
                        else:
                            events.append(event)
                else:
                    reason = "halt" if int(self.dut.done.value) else "limit" if op == "run" else None
            finally:
                if output is not None:
                    output.close()
        elif op == "snapshot":
            pass
        elif op in {"read", "write", "set_io"}:
            address = int(request["address"]) & 0xFFFF
            if op == "read":
                value = int(self.ram[address].value) if self.low <= address <= self.high else self.io.get(address, 0)
            elif op == "set_io" or not self.low <= address <= self.high:
                self.io[address] = int(request["value"]) & 0xFFFF
            else:
                self.ram[address].value = int(request["value"]) & 0xFFFF
                self.written.add(address)
                await Timer(1, unit="ns")
        elif op == "set_reg":
            register = int(request["register"])
            if not 1 <= register <= 7:
                raise ValueError("only registers SP/R1 through R7 are writable; ZERO is read-only")
            packed = int(self.dut.cpu.registers_inst.regs.value)
            shift = (7 - register) * 16
            packed = (packed & ~(0xFFFF << shift)) | ((int(request["value"]) & 0xFFFF) << shift)
            self.dut.cpu.registers_inst.regs.value = packed
            await Timer(1, unit="ns")
        else:
            raise ValueError(f"unknown RTL debug command: {op}")
        return {"ok": True, "state": self.snapshot(request.get("include_ram", True)),
                "events": events, "reason": reason, "value": value}


@cocotb.test()
async def rtl_control_server(dut: Any) -> None:
    connection = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    connection.connect(os.environ["POTADOS_RTL_SOCKET"])
    stream = connection.makefile("rwb")
    simulation = Simulation(dut)
    try:
        while line := stream.readline():
            request = json.loads(line)
            if request.get("op") == "close":
                break
            try:
                response = await simulation.command(request)
            except Exception as exc:
                response = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
            stream.write(json.dumps(response).encode() + b"\n")
            stream.flush()
    finally:
        stream.close()
        connection.close()
