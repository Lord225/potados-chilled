`ifndef POTADOS_REGISTERS_SV
`define POTADOS_REGISTERS_SV

`timescale 1ns / 1ns
`include "potados_common.sv"


module potados_registers  (
    input logic        clk,
    input logic        reset,

    input register_read_request_t  read_request,
    output register_read_response_t read_response,

    input register_write_request_t write_request,
    input stack_pointer_request_t  stack_pointer_request,

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
            if (write_request.write_enable) begin
                case (write_request.write_address)
                    3'b000: ;
                    3'b001: ; // SP is handled separately below
                    3'b010: regs.R2 <= write_request.write_data;
                    3'b011: regs.R3 <= write_request.write_data;
                    3'b100: regs.R4 <= write_request.write_data;
                    3'b101: regs.R5 <= write_request.write_data;
                    3'b110: regs.R6 <= write_request.write_data;
                    3'b111: regs.R7 <= write_request.write_data;
                    default: ;
                endcase
            end

            // Explicit SP writes take priority over automatic stack updates.
            // Increment and decrement enables are mutually exclusive.
            if (write_request.write_enable && write_request.write_address == 3'b001) begin
                regs.SP <= write_request.write_data;
            end else if (stack_pointer_request.operation == STACK_POINTER_WRITE) begin
                regs.SP <= stack_pointer_request.write_data;
            end else if (stack_pointer_request.operation == STACK_POINTER_INCREMENT) begin
                regs.SP <= regs.SP + 16'h0001;
            end else if (stack_pointer_request.operation == STACK_POINTER_DECREMENT) begin
                regs.SP <= regs.SP - 16'h0001;
            end
        end
    end

    always_comb begin
        case (read_request.address_a)
            3'b000: read_response.data_a = 16'h0000;
            3'b001: read_response.data_a = regs.SP;
            3'b010: read_response.data_a = regs.R2;
            3'b011: read_response.data_a = regs.R3;
            3'b100: read_response.data_a = regs.R4;
            3'b101: read_response.data_a = regs.R5;
            3'b110: read_response.data_a = regs.R6;
            3'b111: read_response.data_a = regs.R7;
            default: read_response.data_a = 16'h0000;
        endcase
    
        case (read_request.address_b)
            3'b000: read_response.data_b = 16'h0000;
            3'b001: read_response.data_b = regs.SP;
            3'b010: read_response.data_b = regs.R2;
            3'b011: read_response.data_b = regs.R3;
            3'b100: read_response.data_b = regs.R4;
            3'b101: read_response.data_b = regs.R5;
            3'b110: read_response.data_b = regs.R6;
            3'b111: read_response.data_b = regs.R7;
            default: read_response.data_b = 16'h0000;
        endcase

        registers = regs;
        read_response.stack_pointer = regs.SP;
        read_response.stack_pointer_decremented = regs.SP - 16'h0001;
    end
endmodule

`endif
