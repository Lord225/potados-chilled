`ifndef POTADOS_EXECUTE_STAGE_SV
`define POTADOS_EXECUTE_STAGE_SV
`timescale 1ns/1ns

`include "potados_common.sv"
`include "potados_alu.sv"


module potados_execute_stage (
    input logic         clk,
    input logic         reset,

    input execute_stage_t execute_stage,

    input logic [15:0]  fpu_output,

    output memory_stage_t memory_stage,
    output logic          should_stall,

    output logic         jump_enable,
    output logic [15:0]  jump_address,

    output logic         halt
);
    alu_request_t alu_request;
    logic [15:0] alu_output;
    cmp_result_t cmp_output;
    logic alu_ready;

    potados_alu alu_inst (
        .clk(clk),
        .reset(reset),
        .alu_request(alu_request),
        .alu_output(alu_output),
        .cmp_output(cmp_output),
        .out_ready(alu_ready)
    );

    always_comb begin
        alu_request = '0;
        alu_request.operard_a = execute_stage.operand_a_value;
        alu_request.operard_b = execute_stage.operand_b_value;
        alu_request.alu_op = execute_stage.alu_op;
        alu_request.cmp_op = execute_stage.cmp_op;

        memory_stage = '0;
        memory_stage.valid = execute_stage.valid;
        memory_stage.alu_result = alu_output;
        memory_stage.memory_write_data = execute_stage.memory_write_data;
        memory_stage.fpu_result = fpu_output;
        memory_stage.next_pc = execute_stage.next_pc;
        memory_stage.memory_op = execute_stage.memory_op;
        memory_stage.stack_pointer_op = execute_stage.stack_pointer_op;
        memory_stage.dst = execute_stage.dst;
        memory_stage.writeback_source = execute_stage.writeback_source;

        jump_enable = 1'b0;
        jump_address = execute_stage.jump_target;
        if (execute_stage.valid) begin
            case (execute_stage.jump_op)
                JUMP_NONE:
                    jump_enable = 1'b0;
                JUMP_CONDITIONAL:
                    jump_enable = cmp_output == CMP_RESULT_TRUE;
                JUMP_ALWAYS:
                    jump_enable = 1'b1;
                default:
                    jump_enable = 1'b0;
            endcase
        end

        halt = execute_stage.valid && execute_stage.halt;
        should_stall = 1'b0;
    end
endmodule



`endif
