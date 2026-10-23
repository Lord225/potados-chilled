// Simulation-only observability wrapper. All execution remains in potados.sv.
`timescale 1ns / 1ps
`include "potados.sv"
module potados_sim_top #(
    parameter logic [15:0] RAM_LOW_ADDRESS = 16'h0000,
    parameter logic [15:0] RAM_HIGH_ADDRESS = 16'h7fff
)(
    input logic clk,
    input logic reset,
    input logic [15:0] io_read_data,
    output logic [111:0] registers_out,
    output logic done,
    output logic [15:0] pc,
    output logic [15:0] io_address,
    output logic io_read_enable,
    output logic io_write_enable,
    output logic [15:0] io_write_data,
    output logic [15:0] fetch_pc,
    output logic [15:0] next_fetch_pc,
    output logic [15:0] fetch_low,
    output logic [15:0] fetch_high,
    output logic fetch_valid,
    output logic fetch_high_valid,
    output logic instruction_accepted,
    output logic execute_valid,
    output logic [15:0] execute_pc,
    output logic jump_enable,
    output logic [15:0] jump_address,
    output logic [15:0] memory_address,
    output logic memory_read_enable,
    output logic memory_write_enable,
    output logic [15:0] memory_write_data,
    output logic [15:0] memory_read_data,
    output logic [122:0] execute_packet,
    output logic [74:0] memory_packet,
    output logic [56:0] writeback_packet
);
    potados #(
        .LOAD_ROM_FILE(1'b0),
        .RAM_LOW_ADDRESS(RAM_LOW_ADDRESS),
        .RAM_HIGH_ADDRESS(RAM_HIGH_ADDRESS)
    ) cpu (
        .clk(clk), .reset(reset), .registers_out(registers_out),
        .potados_done(done), .pc_out(pc), .io_address(io_address),
        .io_read_enable(io_read_enable), .io_write_enable(io_write_enable),
        .io_write_data(io_write_data), .io_read_data(io_read_data)
    );
    assign fetch_pc = cpu.fetched_instruction_pc;
    assign next_fetch_pc = cpu.program_memory_inst.pc;
    assign fetch_low = cpu.fetched_instruction_low;
    assign fetch_high = cpu.fetched_instruction_high;
    assign fetch_valid = cpu.fetched_instruction_valid;
    assign fetch_high_valid = cpu.fetched_high_valid;
    assign instruction_accepted = cpu.fetched_instruction_accepted;
    assign execute_valid = cpu.execute_stage.valid;
    assign execute_pc = cpu.execute_stage.pc;
    assign jump_enable = cpu.jump_enable;
    assign jump_address = cpu.jump_address;
    assign memory_address = cpu.ram_address;
    assign memory_read_enable = cpu.ram_load_enable;
    assign memory_write_enable = cpu.ram_store_enable;
    assign memory_write_data = cpu.ram_store_data;
    assign memory_read_data = cpu.ram_load_data;
    assign execute_packet = cpu.execute_stage;
    assign memory_packet = cpu.memory_stage;
    assign writeback_packet = cpu.writeback_stage;
endmodule
