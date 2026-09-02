`ifndef POTADOS_INSTRUCTION_DECODER_SV
`define POTADOS_INSTRUCTION_DECODER_SV

`timescale 1ns / 1ns
`include "potados_common.sv"


module potados_instruction_decoder(
    input logic [15:0] instruction_low,
    input logic [15:0] instruction_high,
    input logic        high_valid,
    output decoded_instruction_t decoded_instruction
);
    function automatic op_primary_t extract_op_primary(
        input logic [15:0] instruction
    );
        extract_op_primary = op_primary_t'(instruction[15:12]);
    endfunction

    function automatic logic[2:0] extract_dst(
        input logic [15:0] instruction
    );
        extract_dst = instruction[11:9];
    endfunction

    function automatic logic[2:0] extract_op_secondary(
        input logic [15:0] instruction
    );
        extract_op_secondary = instruction[8:6];
    endfunction

    function automatic logic[2:0] extract_src_a(
        input logic [15:0] instruction
    );
        extract_src_a = instruction[5:3];
    endfunction

    function automatic logic[2:0] extract_src_b(
        input logic [15:0] instruction
    );
        extract_src_b = instruction[2:0];
    endfunction

    function automatic logic[2:0] extract_sdp(
        input logic [15:0] instruction
    );
        extract_sdp = instruction[2:0];
    endfunction

    function automatic logic[5:0] extract_immediate_6(
        input logic [15:0] instruction
    );
        extract_immediate_6 = {
            instruction[11],
            instruction[10],
            instruction[9],
            instruction[8],
            instruction[7],
            instruction[6]
        };
    endfunction

    function automatic logic[15:0] se_6_bit_immediate(
        input logic [5:0] immediate
    );
        se_6_bit_immediate = {
            {10{immediate[5]}},
            immediate[5:0]
        };
    endfunction

    function automatic logic[15:0] se_5_bit_immediate(
        input logic [4:0] immediate
    );
        se_5_bit_immediate = {
            {11{immediate[4]}},
            immediate
        };
    endfunction
    
    function automatic logic[8:0] extract_immediate_9(
        input logic [15:0] instruction
    );
        extract_immediate_9 = {
            instruction[5],
            instruction[4],
            instruction[3],
            instruction[11],
            instruction[10],
            instruction[9],
            instruction[8],
            instruction[7],
            instruction[6]
        };
    endfunction

    function automatic logic[15:0] se_9_bit_immediate(
        input logic [8:0] immediate
    );
        se_9_bit_immediate = {
            {7{immediate[8]}},
            immediate[8:0]
        };
    endfunction

    // This function is supposed to decode the instruction and return a decoded_instruction_t struct. 
    // It takes instruction in two forms: low and high, and a flag indicating if the high part is valid.
    function automatic decoded_instruction_t decode_instruction(
        input logic [15:0] instruction_low,
        input logic [15:0] instruction_high,
        input logic        high_valid
    );
        decoded_instruction_t decoded;
    
        decoded.op_primary = extract_op_primary(instruction_low);
        decoded.op_secondary = extract_op_secondary(instruction_low);
        decoded.src_a = extract_src_a(instruction_low);
        decoded.src_b = extract_src_b(instruction_low);
        
        decoded.dst = 3'b0;
        decoded.immediate = 16'b0;
        decoded.partialy_decoded = 1'b0;
        decoded.is_long = 1'b0;
        
        case(decoded.op_primary)
            OP_ALU: begin
                decoded.dst = extract_dst(instruction_low);
            end
            OP_SET: begin
                decoded.dst = extract_dst(instruction_low);
            end
            OP_SH: begin
                decoded.dst = extract_sdp(instruction_low);
                decoded.immediate = se_5_bit_immediate(instruction_low[10:6]);
            end
            OP_ASH: begin
                decoded.dst = extract_sdp(instruction_low);
                decoded.immediate = se_5_bit_immediate(instruction_low[10:6]);
            end
            OP_ADDI: begin
                decoded.dst = extract_sdp(instruction_low);
                decoded.immediate = se_9_bit_immediate(extract_immediate_9(instruction_low));
            end
            OP_LDIMM: begin
                decoded.dst = extract_sdp(instruction_low);
                decoded.immediate = se_9_bit_immediate(extract_immediate_9(instruction_low));
            end
            OP_LD: begin
                decoded.dst = extract_sdp(instruction_low);
                decoded.immediate = se_6_bit_immediate(extract_immediate_6(instruction_low));
            end
            OP_ST: begin
                decoded.dst = extract_sdp(instruction_low);
                decoded.immediate = se_6_bit_immediate(extract_immediate_6(instruction_low));
            end
            OP_LDSP: begin
                decoded.dst = extract_sdp(instruction_low);
                decoded.immediate = se_9_bit_immediate(extract_immediate_9(instruction_low));
            end
            OP_STSP: begin
                decoded.dst = extract_sdp(instruction_low);
                decoded.immediate = se_9_bit_immediate(extract_immediate_9(instruction_low));
            end
            OP_CJUMP: begin
                decoded.immediate = instruction_high;
                decoded.is_long = 1'b1;
                if(high_valid) begin
                    decoded.partialy_decoded = 1'b0;
                end else begin
                    decoded.partialy_decoded = 1'b1;
                end
            end
            OP_JUMP: begin
                decoded.dst = extract_sdp(instruction_low);
                decoded.immediate = instruction_high;
                decoded.is_long = 1'b1;
                if(high_valid) begin
                    decoded.partialy_decoded = 1'b0;
                end else begin
                    decoded.partialy_decoded = 1'b1;
                end
            end
            OP_STACK: begin
                decoded.dst = extract_sdp(instruction_low);
            end
            OP_JUMP_REG: begin
                decoded.dst = extract_sdp(instruction_low);
            end
            OP_FPU: begin
                decoded.dst = extract_dst(instruction_low);
            end
            OP_HALT: begin
                decoded.immediate = instruction_low;
            end
            default: begin
            end
        endcase
        // Yosys does not support SystemVerilog's procedural `return` in a
        // function.  Assigning the function name is the portable Verilog and
        // SystemVerilog form.
        decode_instruction = decoded;
    endfunction

    always_comb begin
        decoded_instruction = decode_instruction(instruction_low, instruction_high, high_valid);
    end
endmodule


// Result of resolving one architectural register for the instruction entering
// execute. `matched && !ready` means the youngest producer is a load whose
// data is not available yet, so decode must stall.
typedef struct packed {
    // is the value coming from a forwarding source, or the register file?
    logic        matched;
    // is the value ready to be used, or is it still pending from a load?
    logic        ready;
    // the operand value itself.
    logic [15:0] value;
} operand_result_t;


// Forwarding source is a producer of a register value that may be younger than the architectural register file.
// Value may be in the execute stage, memory stage, or writeback stage.
typedef struct packed {
    // Valid is true if the forwarding source is a valid producer of a register value.
    logic        valid;
    // The destination register address that this forwarding source produces.
    logic [2:0]  dst;
    // The value is valid only when ready is true. 
    logic        ready;
    // The value produced by this forwarding source. It is valid only when ready is true.
    logic [15:0] value;
} forwarding_source_t;

module potados_decode_stage(
    input logic                 instruction_valid,
    input logic [15:0]          instruction_pc,
    input logic [15:0]          instruction_next_pc,
    input decoded_instruction_t decoded_instruction,

    output register_read_request_t  register_read_request,
    input register_read_response_t  register_read_response,
    // Kept only while the old decoder-case call sites are simplified. It is
    // no longer consulted for normal-register hazards.
    // input register_status_t         register_status,

    // The execute result is the youngest in-flight producer, followed by the
    // registered memory and writeback stages.
    input memory_stage_t execute_forward_stage,
    input memory_stage_t current_memory_stage,
    input register_write_request_t writeback_forward,

    // Stack-pointer auto-updates are not yet forwarded.  Decode waits for
    // them to commit, while normal register dependencies are forwarded.
    input writeback_stage_t current_writeback_stage,

    output execute_stage_t execute_stage,
    output logic should_stall
);
    function automatic alu_op_t decode_alu_operation(
        input logic [2:0] operation
    );
        case (operation)
            3'b001: decode_alu_operation = ALU_ADD;
            3'b010: decode_alu_operation = ALU_SUB;
            3'b011: decode_alu_operation = ALU_AND;
            3'b100: decode_alu_operation = ALU_OR;
            3'b101: decode_alu_operation = ALU_XOR;
            3'b110: decode_alu_operation = ALU_NOT;
            3'b111: decode_alu_operation = ALU_MUL;
            default: decode_alu_operation = ALU_NONE;
        endcase
    endfunction

    function automatic cmp_op_t decode_compare_operation(
        input logic [2:0] operation
    );
        case (operation)
            3'b000: decode_compare_operation = CMP_GE;
            3'b001: decode_compare_operation = CMP_L;
            3'b010: decode_compare_operation = CMP_E;
            3'b011: decode_compare_operation = CMP_NE;
            3'b100: decode_compare_operation = CMP_AE;
            3'b101: decode_compare_operation = CMP_B;
            default: decode_compare_operation = CMP_NONE;
        endcase
    endfunction

    function automatic fpu_op_t decode_fpu_operation(
        input logic [2:0] operation
    );
        case (operation)
            3'b001: decode_fpu_operation = FPU_ADD;
            3'b010: decode_fpu_operation = FPU_SUB;
            3'b011: decode_fpu_operation = FPU_MUL;
            3'b100: decode_fpu_operation = FPU_DIV;
            3'b101: decode_fpu_operation = FPU_ITOF;
            3'b110: decode_fpu_operation = FPU_FTOI;
            3'b111: decode_fpu_operation = FPU_UTOF;
            default: decode_fpu_operation = FPU_NONE;
        endcase
    endfunction

    function automatic forwarding_source_t source_from_memory_stage(
        input memory_stage_t stage
    );
        forwarding_source_t source;
        source = '0;
        source.valid = stage.valid &&
                       stage.writeback_source != WB_NONE &&
                       stage.dst != 3'b000;
        source.dst = stage.dst;

        case (stage.writeback_source)
            WB_ALU: begin
                source.ready = 1'b1;
                source.value = stage.alu_result;
            end
            WB_FPU: begin
                source.ready = 1'b1;
                source.value = stage.fpu_result;
            end
            WB_RETURN_ADDRESS: begin
                source.ready = 1'b1;
                source.value = stage.next_pc;
            end
            // A load's address is known, but its response is not available
            // until the instruction reaches writeback.
            WB_MEMORY: begin
                source.ready = 1'b0;
                source.value = '0;
            end
            WB_NONE: begin
                source.ready = 1'b0;
                source.value = '0;
            end
            default: begin
                source.ready = 1'b0;
                source.value = '0;
            end
        endcase
        source_from_memory_stage = source;
    endfunction

    function automatic forwarding_source_t source_from_writeback(
        input register_write_request_t write_request
    );
        forwarding_source_t source;
        source = '0;
        source.valid = write_request.write_enable &&
                       write_request.write_address != 3'b000;
        source.dst = write_request.write_address;
        source.ready = source.valid;
        source.value = write_request.write_data;
        source_from_writeback = source;
    endfunction

    function automatic operand_result_t resolve_operand(
        input logic [2:0] register_address,
        input logic [15:0] register_file_value,
        input forwarding_source_t execute_source,
        input forwarding_source_t memory_source,
        input forwarding_source_t writeback_source
    );
        operand_result_t result;
        result = '0;
        result.matched = 1'b0;
        result.ready = 1'b1;
        result.value = register_file_value;

        if (register_address == 3'b000) begin
            result.value = 16'h0000;
        end else if (execute_source.valid && execute_source.dst == register_address) begin
            result.matched = 1'b1;
            result.ready = execute_source.ready;
            result.value = execute_source.value;
        end else if (memory_source.valid && memory_source.dst == register_address) begin
            result.matched = 1'b1;
            result.ready = memory_source.ready;
            result.value = memory_source.value;
        end else if (writeback_source.valid && writeback_source.dst == register_address) begin
            result.matched = 1'b1;
            result.ready = writeback_source.ready;
            result.value = writeback_source.value;
        end

        resolve_operand = result;
    endfunction

    // `status`, `src_a`, and `src_b` remain in this interface temporarily so
    // the instruction cases stay readable while the scoreboard is removed.
    // Readiness comes exclusively from the direct stage inspection above.
    function automatic logic check_should_stall(
        input operand_result_t operand_a,
        input operand_result_t operand_b,
        input logic src_a_is_used,
        input logic src_b_is_used
    );
        check_should_stall =
            (src_a_is_used && !operand_a.ready) ||
            (src_b_is_used && !operand_b.ready);
    endfunction

    forwarding_source_t execute_source;
    forwarding_source_t memory_source;
    forwarding_source_t writeback_source;
    operand_result_t result_a;
    operand_result_t result_b;
    logic [2:0] source_a_address;
    logic [2:0] source_b_address;
    logic source_a_used;
    logic source_b_used;
    logic automatic_sp_update_pending;
    
    always_comb begin
        source_a_address = decoded_instruction.src_a;
        source_b_address = decoded_instruction.src_b;
        source_a_used = 1'b0;
        source_b_used = 1'b0;

        // Select architectural source registers before driving the two
        // combinational register-file read ports.
        case (decoded_instruction.op_primary)
            OP_ALU, OP_SET, OP_CJUMP, OP_FPU: begin
                source_a_used = decoded_instruction.op_primary != OP_FPU ||
                                decoded_instruction.op_secondary < 3'b101;
                source_b_used = 1'b1;
            end
            OP_SH, OP_ASH, OP_LD: source_a_used = 1'b1;
            OP_ADDI: source_b_used = 1'b1;
            OP_ST: begin
                source_a_used = 1'b1;
                source_b_used = 1'b1;
            end
            OP_LDSP: begin
                source_a_address = 3'b001;
                source_a_used = 1'b1;
            end
            OP_STSP: begin
                source_a_address = 3'b001;
                source_a_used = 1'b1;
                source_b_used = 1'b1;
            end
            OP_STACK: begin
                source_a_address = 3'b001;
                source_a_used = decoded_instruction.op_secondary == 3'b001 ||
                                decoded_instruction.op_secondary == 3'b010;
                source_b_used = decoded_instruction.op_secondary == 3'b001;
            end
            OP_JUMP_REG: begin
                if (decoded_instruction.op_secondary == 3'b001)
                    source_b_used = 1'b1;
                if (decoded_instruction.op_secondary == 3'b010)
                    source_a_used = 1'b1;
            end
            default: ;
        endcase

        register_read_request.address_a = source_a_address;
        register_read_request.address_b = source_b_address;
    end

    always_comb begin
        execute_source = source_from_memory_stage(execute_forward_stage);
        memory_source = source_from_memory_stage(current_memory_stage);
        writeback_source = source_from_writeback(writeback_forward);
        result_a = resolve_operand(source_a_address, register_read_response.data_a,
                                   execute_source, memory_source, writeback_source);
        result_b = resolve_operand(source_b_address, register_read_response.data_b,
                                   execute_source, memory_source, writeback_source);
        automatic_sp_update_pending =
            (execute_forward_stage.valid && execute_forward_stage.stack_pointer_op != STACK_POINTER_NONE) ||
            (current_memory_stage.valid && current_memory_stage.stack_pointer_op != STACK_POINTER_NONE) ||
            (current_writeback_stage.valid && current_writeback_stage.stack_pointer_op != STACK_POINTER_NONE);

        // zero is default state for execute
        execute_stage = '0;
        should_stall = 1'b0;


        if (instruction_valid && decoded_instruction.partialy_decoded=='0) begin
            execute_stage.valid = 1'b1;
            execute_stage.pc = instruction_pc;
            execute_stage.next_pc = instruction_next_pc;
            execute_stage.dst = decoded_instruction.dst;

            execute_stage.operand_a_value = result_a.value;
            execute_stage.operand_b_value = result_b.value;
            
            case (decoded_instruction.op_primary)
                OP_ALU: begin
                    execute_stage.alu_op = decode_alu_operation(decoded_instruction.op_secondary);
                    execute_stage.writeback_source = WB_ALU;

                    // should_stall = register_status.pending_write[decoded_instruction.src_a] || register_status.pending_write[decoded_instruction.src_b];
                    should_stall = check_should_stall(
                        result_a, 
                        result_b, 
                        source_a_used,
                        source_b_used
                    );
                end

                OP_SET: begin
                    execute_stage.cmp_op = decode_compare_operation(decoded_instruction.op_secondary);
                    execute_stage.alu_op = ALU_SET;
                    execute_stage.writeback_source = WB_ALU;

                    // should_stall = register_status.pending_write[decoded_instruction.src_a] || register_status.pending_write[decoded_instruction.src_b];
                    should_stall = check_should_stall(
                        result_a, 
                        result_b, 
                        source_a_used,
                        source_b_used
                    );
                end

                OP_SH: begin
                    execute_stage.alu_op = ALU_SH;
                    execute_stage.operand_b_value = decoded_instruction.immediate;
                    execute_stage.writeback_source = WB_ALU;

                    // should_stall = register_status.pending_write[decoded_instruction.src_a];
                    should_stall = check_should_stall(
                        result_a, 
                        result_b, 
                        1'b1,
                        1'b0 
                    );
                end

                OP_ASH: begin
                    execute_stage.alu_op = ALU_ASH;
                    execute_stage.operand_b_value = decoded_instruction.immediate;
                    execute_stage.writeback_source = WB_ALU;

                    // should_stall = register_status.pending_write[decoded_instruction.src_a];
                    should_stall = check_should_stall(
                        result_a, 
                        result_b, 
                        1'b1,
                        1'b0 
                    );
                end

                OP_ADDI: begin
                    execute_stage.alu_op = ALU_ADD;
                    execute_stage.operand_a_value = result_b.value;
                    execute_stage.operand_b_value = decoded_instruction.immediate;
                    execute_stage.writeback_source = WB_ALU;

                    // should_stall = register_status.pending_write[decoded_instruction.src_b];
                    should_stall = check_should_stall(
                        result_a, 
                        result_b, 
                        1'b0,
                        1'b1 
                    );
                end

                OP_LDIMM: begin
                    // src_a[2] is the LLI/LUI selector bit.  The remaining
                    // eight immediate bits are decoded_instruction.immediate[7:0].
                    // pass-through the ALU to registers. 
                    if (decoded_instruction.src_a[2]) begin
                        execute_stage.operand_b_value = {decoded_instruction.immediate[7:0], 8'h00};
                    end else begin
                        execute_stage.operand_b_value = {8'h00, decoded_instruction.immediate[7:0]};
                    end
                    execute_stage.alu_op = ALU_OR;
                    execute_stage.writeback_source = WB_ALU;
                    execute_stage.operand_a_value = 16'h0000;
                end

                OP_LD: begin
                    execute_stage.alu_op = ALU_ADD;
                    execute_stage.operand_b_value = decoded_instruction.immediate;
                    execute_stage.memory_op = MEMORY_LOAD;
                    execute_stage.writeback_source = WB_MEMORY;

                    // should_stall = register_status.pending_write[decoded_instruction.src_a];
                    should_stall = check_should_stall(
                        result_a, 
                        result_b, 
                        1'b1,
                        1'b0 
                    );
                end

                OP_ST: begin
                    execute_stage.alu_op = ALU_ADD;
                    execute_stage.operand_b_value = decoded_instruction.immediate;
                    execute_stage.memory_write_data = result_b.value;
                    execute_stage.memory_op = MEMORY_STORE;

                    // should_stall = register_status.pending_write[decoded_instruction.src_a] || register_status.pending_write[decoded_instruction.src_b];
                    should_stall = check_should_stall(
                        result_a, 
                        result_b, 
                        1'b1,
                        1'b1 
                    );
                end

                OP_LDSP: begin
                    execute_stage.alu_op = ALU_ADD;
                    execute_stage.operand_a_value = result_a.value;
                    execute_stage.operand_b_value = decoded_instruction.immediate;
                    execute_stage.memory_op = MEMORY_LOAD;
                    execute_stage.writeback_source = WB_MEMORY;

                    // should_stall = register_status.pending_write[3'b001];
                    should_stall = check_should_stall(
                        result_a, 
                        result_b, 
                        1'b1,
                        1'b0 
                    );
                end

                OP_STSP: begin
                    execute_stage.alu_op = ALU_ADD;
                    execute_stage.operand_a_value = result_a.value;
                    execute_stage.operand_b_value = decoded_instruction.immediate;
                    execute_stage.memory_write_data = result_b.value;
                    execute_stage.memory_op = MEMORY_STORE;

                    // should_stall = register_status.pending_write[3'b001] || register_status.pending_write[decoded_instruction.src_b];
                    should_stall = check_should_stall(
                        result_a, 
                        result_b, 
                        1'b1,
                        1'b1 
                    );
                end

                OP_CJUMP: begin
                    execute_stage.alu_op = ALU_CMP;
                    execute_stage.cmp_op = decode_compare_operation(decoded_instruction.op_secondary);
                    execute_stage.jump_op = JUMP_CONDITIONAL;
                    execute_stage.jump_target = decoded_instruction.immediate;

                    // should_stall = register_status.pending_write[decoded_instruction.src_a] || register_status.pending_write[decoded_instruction.src_b];
                    should_stall = check_should_stall(
                        result_a, 
                        result_b, 
                        1'b1,
                        1'b1 
                    );
                end

                OP_JUMP: begin
                    case (decoded_instruction.op_secondary)
                        3'b001: begin // JMP IMM16
                            execute_stage.jump_op = JUMP_ALWAYS;
                            execute_stage.jump_target = decoded_instruction.immediate;
                        end
                        3'b010: begin // JAL IMM16, DST
                            execute_stage.jump_op = JUMP_ALWAYS;
                            execute_stage.jump_target = decoded_instruction.immediate;
                            execute_stage.writeback_source = WB_RETURN_ADDRESS;
                        end
                        default: begin
                        end
                    endcase
                end

                OP_STACK: begin
                    case (decoded_instruction.op_secondary)
                        3'b001: begin // PUSH SRC
                            execute_stage.alu_op = ALU_ADD;
                            execute_stage.operand_a_value = result_a.value;
                            execute_stage.operand_b_value = 16'h0000;
                            execute_stage.memory_write_data = result_b.value;
                            execute_stage.memory_op = MEMORY_STORE;
                            execute_stage.stack_pointer_op = STACK_POINTER_INCREMENT;

                            // should_stall = register_status.pending_write[3'b001] || register_status.pending_write[decoded_instruction.src_b];
                            should_stall = check_should_stall(
                                result_a, 
                                result_b, 
                                1'b1,
                                1'b1 
                            );
                        end
                        3'b010: begin // POP DST
                            execute_stage.alu_op = ALU_ADD;
                            execute_stage.operand_a_value = result_a.value - 16'h0001;
                            execute_stage.operand_b_value = 16'h0000;
                            execute_stage.memory_op = MEMORY_LOAD;
                            execute_stage.stack_pointer_op = STACK_POINTER_DECREMENT;
                            execute_stage.writeback_source = WB_MEMORY;

                            // should_stall = register_status.pending_write[3'b001];
                            should_stall = check_should_stall(
                                result_a, 
                                result_b, 
                                1'b1,
                                1'b0 
                            );
                        end
                        default: begin
                        end
                    endcase
                end

                OP_JUMP_REG: begin
                    case (decoded_instruction.op_secondary)
                        3'b001: begin // JMPR SRC_B
                            execute_stage.jump_op = JUMP_ALWAYS;
                            execute_stage.jump_target = result_b.value;
                            // should_stall = register_status.pending_write[decoded_instruction.src_b];
                            should_stall = check_should_stall(
                                result_a, 
                                result_b, 
                                1'b0,
                                1'b1 
                            );
                        end
                        3'b010: begin // JALR SRC_A, DST
                            execute_stage.jump_op = JUMP_ALWAYS;
                            execute_stage.jump_target = result_a.value;
                            execute_stage.writeback_source = WB_RETURN_ADDRESS;
                            // should_stall = register_status.pending_write[decoded_instruction.src_a];
                            should_stall = check_should_stall(
                                result_a, 
                                result_b, 
                                1'b1,
                                1'b0 
                            );
                        end
                        default: begin
                        end
                    endcase
                end

                OP_FPU: begin
                    execute_stage.fpu_op = decode_fpu_operation(decoded_instruction.op_secondary);
                    execute_stage.writeback_source = WB_FPU;
                    // Conversion instructions are unary and use SRC_B.
                    if (decoded_instruction.op_secondary >= 3'b101) begin
                        execute_stage.operand_a_value = result_b.value;
                        execute_stage.operand_b_value = 16'h0000;
                    end
                    // should_stall = register_status.pending_write[decoded_instruction.src_a] || register_status.pending_write[decoded_instruction.src_b];
                    should_stall = check_should_stall(
                        result_a, 
                        result_b, 
                        source_a_used,
                        source_b_used
                    );
                end

                OP_HALT: begin
                    execute_stage.halt = 1'b1;
                end

                default: begin
                end
            endcase

            // Automatic SP updates are not yet bypassed, so serialize only
            // instructions that read or modify SP. Normal GPR WAWs are safe:
            // writeback is in program order and consumers choose the youngest
            // matching producer.
            if (automatic_sp_update_pending &&
                ((source_a_used && source_a_address == 3'b001) ||
                 (source_b_used && source_b_address == 3'b001) ||
                 execute_stage.stack_pointer_op != STACK_POINTER_NONE)) begin
                should_stall = 1'b1;
            end

            if (should_stall) begin
                execute_stage.valid = 1'b0;
            end
        end
    end
endmodule



// Small integration harness for testing decode/register-read preparation.
// It contains the instruction decoder, register file, and decode stage, while
// exposing simple scalar ports for Cocotb to drive instructions and registers.
module instruction_decoder_stage_testbech_helper(
    input logic        clk,
    input logic        reset,

    input logic        instruction_valid,
    input logic [15:0] instruction_pc,
    input logic [15:0] instruction_next_pc,
    input logic [15:0] instruction_low,
    input logic [15:0] instruction_high,
    input logic        high_valid,

    input logic        register_write_enable,
    input logic [2:0]  register_write_address,
    input logic [15:0] register_write_data,
    input logic [15:0] stack_pointer_write_data,
    input stack_pointer_op_t stack_pointer_operation,

    output execute_stage_t execute_stage
);
    decoded_instruction_t decoded_instruction;
    register_read_request_t register_read_request;
    register_read_response_t register_read_response;
    register_status_t register_status;
    register_write_request_t register_write_request;
    stack_pointer_request_t stack_pointer_request;
    logic decode_should_stall;

    always_comb begin
        register_write_request.write_enable = register_write_enable;
        register_write_request.write_address = register_write_address;
        register_write_request.write_data = register_write_data;

        stack_pointer_request.write_data = stack_pointer_write_data;
        stack_pointer_request.operation = stack_pointer_operation;

        // The helper has no in-flight pipeline instructions.
        register_status = '0;
    end

    potados_instruction_decoder instruction_decoder_inst (
        .instruction_low(instruction_low),
        .instruction_high(instruction_high),
        .high_valid(high_valid),
        .decoded_instruction(decoded_instruction)
    );

    potados_registers registers_inst (
        .clk(clk),
        .reset(reset),
        .read_request(register_read_request),
        .read_response(register_read_response),
        .write_request(register_write_request),
        .stack_pointer_request(stack_pointer_request),
        .registers()
    );

    potados_decode_stage decode_stage_inst (
        .instruction_valid(instruction_valid),
        .instruction_pc(instruction_pc),
        .instruction_next_pc(instruction_next_pc),
        .decoded_instruction(decoded_instruction),
        .register_read_request(register_read_request),
        .register_read_response(register_read_response),
        .execute_forward_stage('0),
        .current_memory_stage('0),
        .writeback_forward(register_write_request),
        .current_writeback_stage('0),
        .should_stall(decode_should_stall),
        .execute_stage(execute_stage)
    );
endmodule

`endif
