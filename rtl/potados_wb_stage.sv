`ifndef POTADOS_WBS_SV
`define POTADOS_WBS_SV
`include "potados_common.sv"





module potados_writeback_stage(
    input writeback_stage_t writeback_stage,
    input logic [15:0] ram_load_data,
    output logic writeback_declare_stall,

    output register_write_request_t register_write_request,
    output stack_pointer_request_t  stack_pointer_request
);
    always_comb begin
        // Should write sth to register in this cycle?
        register_write_request.write_enable = writeback_stage.valid && (writeback_stage.writeback_source != WB_NONE);
        // Which register to write to?
        register_write_request.write_address = writeback_stage.dst;
        writeback_declare_stall = 1'b0;
        
        // Choose data based on requested writeback source. If the source is WB_NONE, the data is ignored.
        case (writeback_stage.writeback_source)
            WB_NONE: register_write_request.write_data = '0;
            WB_ALU:  register_write_request.write_data = writeback_stage.alu_result;
            WB_FPU:  register_write_request.write_data = writeback_stage.fpu_result;
            WB_MEMORY:  register_write_request.write_data = ram_load_data;
            WB_RETURN_ADDRESS:   register_write_request.write_data = writeback_stage.next_pc;
            default: register_write_request.write_data = '0;
        endcase
 
        if (writeback_stage.valid) begin
            if (writeback_stage.stack_pointer_op == STACK_POINTER_NONE) begin
                stack_pointer_request.operation = STACK_POINTER_NONE;
                stack_pointer_request.write_data = '0; // TODO
            end else begin
                stack_pointer_request.operation = writeback_stage.stack_pointer_op;
                stack_pointer_request.write_data = '0; // TODO
            end
        end else begin
            stack_pointer_request.operation = STACK_POINTER_NONE;
            stack_pointer_request.write_data = '0; 
        end
    end
endmodule


`endif