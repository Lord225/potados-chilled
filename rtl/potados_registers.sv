`ifndef POTADOS_REGISTERS_SV
`define POTADOS_REGISTERS_SV


`timescale 1ns / 1ns
`include "potados_common.sv"


module potados_registers  (
    input logic        clk,
    input logic        reset,
    input logic        write_enable,
    input logic [2:0]  write_address,
    input logic [15:0] write_data,
    input logic [15:0] stack_pointer_write_data,
    input logic        stack_pointer_write_enable,
    input logic        stack_pointer_increment_enable,
    input logic        stack_pointer_decrement_enable,

    input logic [2:0]  read_address_a,
    input logic [2:0]  read_address_b,

    output logic [15:0] read_data_a,
    output logic [15:0] read_data_b,
    output logic [15:0] stack_pointer,
    output logic [15:0] stack_pointer_decremented,

    output register_file_t registers
);
    register_file_t regs;

    always_ff @(posedge clk or posedge reset) begin
        if (reset) begin
            regs.SP <= 16'h0000;
            regs.R2 <= 16'h0000;
            regs.R3 <= 16'h0000;
            regs.R4 <= 16'h0000;
            regs.R5 <= 16'h0000;
            regs.R6 <= 16'h0000;
            regs.R7 <= 16'h0000;
        end else begin
            if (write_enable) begin
                case (write_address)
                    3'b000: ;
                    3'b001: ;
                    3'b010: regs.R2 <= write_data;
                    3'b011: regs.R3 <= write_data;
                    3'b100: regs.R4 <= write_data;
                    3'b101: regs.R5 <= write_data;
                    3'b110: regs.R6 <= write_data;
                    3'b111: regs.R7 <= write_data;
                    default: ;
                endcase
            end

            // Explicit SP writes take priority over automatic stack updates.
            // Increment and decrement enables are mutually exclusive.
            if (stack_pointer_write_enable) begin
                regs.SP <= stack_pointer_write_data;
            end else if (stack_pointer_increment_enable) begin
                regs.SP <= regs.SP + 16'h0001;
            end else if (stack_pointer_decrement_enable) begin
                regs.SP <= regs.SP - 16'h0001;
            end else if (write_enable && write_address == 3'b001) begin
                regs.SP <= write_data;
            end
        end
    end

    always_comb begin
        case (read_address_a)
            3'b000: read_data_a = 16'h0000;
            3'b001: read_data_a = regs.SP;
            3'b010: read_data_a = regs.R2;
            3'b011: read_data_a = regs.R3;
            3'b100: read_data_a = regs.R4;
            3'b101: read_data_a = regs.R5;
            3'b110: read_data_a = regs.R6;
            3'b111: read_data_a = regs.R7;
            default: read_data_a = 16'h0000;
        endcase

        case (read_address_b)
            3'b000: read_data_b = 16'h0000;
            3'b001: read_data_b = regs.SP;
            3'b010: read_data_b = regs.R2;
            3'b011: read_data_b = regs.R3;
            3'b100: read_data_b = regs.R4;
            3'b101: read_data_b = regs.R5;
            3'b110: read_data_b = regs.R6;
            3'b111: read_data_b = regs.R7;
            default: read_data_b = 16'h0000;
        endcase

        registers = regs;
        stack_pointer = regs.SP;
        stack_pointer_decremented = regs.SP - 16'h0001;
    end


endmodule


`endif
