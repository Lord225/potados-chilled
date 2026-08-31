`ifndef POTADOS_MEMS_SV
`define POTADOS_MEMS_SV
`include "potados_common.sv"


module potados_memory_stage(
    input memory_stage_t memory_stage,

    output logic [15:0] ram_address,
    output logic        ram_store_enable,
    output logic [15:0] ram_store_data,
    output logic        ram_load_enable,
    
    output writeback_stage_t writeback_stage,
    output logic should_stall
);

    always_comb begin
        ram_address = memory_stage.alu_result;
        ram_store_enable = memory_stage.valid && (memory_stage.memory_op == MEMORY_STORE);
        ram_store_data = memory_stage.memory_write_data;
        ram_load_enable = memory_stage.valid && (memory_stage.memory_op == MEMORY_LOAD);

        writeback_stage = '0;
        writeback_stage.valid = memory_stage.valid;
        writeback_stage.alu_result = memory_stage.alu_result;
        writeback_stage.fpu_result = memory_stage.fpu_result;
        writeback_stage.next_pc = memory_stage.next_pc;
        writeback_stage.dst = memory_stage.dst;
        writeback_stage.stack_pointer_op = memory_stage.stack_pointer_op;
        writeback_stage.writeback_source = memory_stage.writeback_source;
        should_stall = 1'b0;
    end
endmodule

`endif
