`ifndef POTADOS_ALU_SV
`define POTADOS_ALU_SV

`timescale 1ns / 1ns
`include "potados_common.sv"



module potados_alu  (
    input logic        clk,
    input logic        reset,
    input logic        cin,
    input logic [15:0] operard_a,
    input logic [15:0] operard_b,
    input alu_op_t     alu_op,
    input cmp_op_t     cmp_op,

    output logic [15:0] alu_output,
    output cmp_result_t cmp_output,
    output logic        out_ready
);
    logic [15:0] alu_output_next;
    cmp_result_t cmp_output_next;
    logic        out_ready_next;

    function automatic cmp_result_t compare(
        input logic [15:0] operand_a,
        input logic [15:0] operand_b,
        input cmp_op_t     op
    );
        case(op)
            CMP_NONE: compare = CMP_RESULT_NONE;
            CMP_GE:   compare = ($signed(operand_a) >= $signed(operand_b)) ? CMP_RESULT_TRUE : CMP_RESULT_FALSE;
            CMP_L:    compare = ($signed(operand_a) <  $signed(operand_b)) ? CMP_RESULT_TRUE : CMP_RESULT_FALSE;
            CMP_E:    compare = (operand_a == operand_b) ? CMP_RESULT_TRUE : CMP_RESULT_FALSE;
            CMP_NE:   compare = (operand_a != operand_b) ? CMP_RESULT_TRUE : CMP_RESULT_FALSE;
            CMP_AE:   compare = (operand_a >= operand_b) ? CMP_RESULT_TRUE : CMP_RESULT_FALSE;
            CMP_B:    compare = (operand_a <  operand_b) ? CMP_RESULT_TRUE : CMP_RESULT_FALSE;
            default:  compare = CMP_RESULT_NONE;
        endcase
    endfunction

    function automatic logic[15:0] logic_shift(
        input logic [15:0] value,
        input logic [4:0] shift
    );
        if (shift[4]) begin
            logic_shift = value >> shift[3:0];
        end else begin
            logic_shift = value << shift[3:0];
        end
    endfunction

    function automatic logic[15:0] arithmetic_shift(
        input logic [15:0] value,
        input logic [4:0] shift
    );
        if (shift[4]) begin
            arithmetic_shift = $signed(value) >>> shift[3:0];
        end else begin
            arithmetic_shift = value << shift[3:0];
        end
    endfunction

    always_ff @(posedge clk, posedge reset) begin
        if (reset) begin
            alu_output <= '0;
            cmp_output <= CMP_RESULT_NONE;
            out_ready  <= 1'b0;
        end else begin
            alu_output <= alu_output_next;
            cmp_output <= cmp_output_next;
            out_ready  <= out_ready_next;
        end
    end

    always_comb begin
        alu_output_next = 0;
        cmp_output_next = CMP_RESULT_NONE;
        out_ready_next  = 0;
    
        case(alu_op)
            ALU_NONE: begin
                alu_output_next = '0;
                cmp_output_next = CMP_RESULT_NONE;
                out_ready_next  = 1'b0;
            end
            ALU_ADD: begin
                alu_output_next = operard_a + operard_b + 16'(cin);
                cmp_output_next = CMP_RESULT_NONE;
                out_ready_next  = 1'b1;
            end
            ALU_SUB: begin
                alu_output_next = operard_a - operard_b - 16'(cin);
                cmp_output_next = compare(operard_a, operard_b, cmp_op);
                out_ready_next  = 1'b1;        
            end
            ALU_AND: begin
                alu_output_next = operard_a & operard_b;
                cmp_output_next = CMP_RESULT_NONE;
                out_ready_next  = 1'b1;
            end
            ALU_OR: begin
                alu_output_next = operard_a | operard_b;
                cmp_output_next = CMP_RESULT_NONE;
                out_ready_next  = 1'b1;
            end
            ALU_XOR: begin
                alu_output_next = operard_a ^ operard_b;
                cmp_output_next = CMP_RESULT_NONE;
                out_ready_next  = 1'b1;
            end
            ALU_NOT: begin
                alu_output_next = ~operard_a;
                cmp_output_next = CMP_RESULT_NONE;
                out_ready_next  = 1'b1;
            end
            ALU_MUL: begin
                alu_output_next = operard_a * operard_b;
                cmp_output_next = CMP_RESULT_NONE;
                out_ready_next  = 1'b1;
            end
            ALU_SH: begin
                alu_output_next = logic_shift(operard_a, operard_b[4:0]);
                cmp_output_next = CMP_RESULT_NONE;
                out_ready_next  = 1'b1;
            end
            ALU_ASH: begin
                alu_output_next = arithmetic_shift(operard_a, operard_b[4:0]);
                cmp_output_next = CMP_RESULT_NONE;
                out_ready_next  = 1'b1;
            end
            ALU_SET: begin
                alu_output_next = (compare(operard_a, operard_b, cmp_op) == CMP_RESULT_TRUE) ? 16'd1 : 16'd0;
                cmp_output_next = compare(operard_a, operard_b, cmp_op);
                out_ready_next = 1'b1;
            end
            ALU_CMP: begin
                alu_output_next = operard_a - operard_b - 16'(cin);
                cmp_output_next = compare(operard_a, operard_b, cmp_op);
                out_ready_next  = 1'b1;  
            end
            default: begin
                alu_output_next = '0;
                cmp_output_next = CMP_RESULT_NONE;
                out_ready_next  = 1'b0;
            end
        endcase
    end
endmodule

`endif
