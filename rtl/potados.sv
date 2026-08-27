`ifndef POTADOS_SV
`define POTADOS_SV

`timescale 1ns / 1ps
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

    function automatic logic[15:0] se_8_bit_immediate(
        input logic [7:0] immediate
    );
        se_8_bit_immediate = {
            {8{immediate[7]}},
            immediate[7:0]
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
        decoded.partialy_decoded = 16'b0;
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
                decoded.immediate = se_6_bit_immediate(extract_immediate_6(instruction_low));
            end
            OP_ASH: begin
                decoded.dst = extract_sdp(instruction_low);
                decoded.immediate = se_6_bit_immediate(extract_immediate_6(instruction_low));
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
        return decoded;
    endfunction

    always_comb begin
        decoded_instruction = decode_instruction(instruction_low, instruction_high, high_valid);
    end
endmodule

module potados(
    input logic clk,
    input logic reset,
    output logic [15:0] low_instruction_out,
    output logic [15:0] high_instruction_out,
    output logic instruction_is_long,
    output logic instruction_ready,
    output decoded_instruction_t decoded_instruction_out
);
    // Fetched instruction words and their validity flags.
    logic [15:0] fetched_instruction_low;
    logic [15:0] fetched_instruction_high;
    logic        fetched_instruction_valid;
    logic        fetched_high_valid;

    // Decoded form of the fetched instruction.
    decoded_instruction_t decoded_instruction;

    // Requests sent to the instruction-fetch unit.
    logic fetch_request_long;
    logic fetch_request_next;
    logic fetch_request_long_next;
    logic fetch_request_next_next;

    potados_program_memory program_memory_inst (
        .clk(clk),
        .reset(reset),
        
        .request_long_instruction(fetch_request_long),
        .request_next_instruction(fetch_request_next),
        
        .jump_address(16'b0),
        .jump_enable(1'b0),
        
        .low_instruction(fetched_instruction_low),
        .high_instruction(fetched_instruction_high),

        .high_valid(fetched_high_valid),

        .low_valid(fetched_instruction_valid)
    );

    potados_instruction_decoder instruction_decoder_inst (
        .instruction_low(fetched_instruction_low),
        .instruction_high(fetched_instruction_high),
        .high_valid(fetched_high_valid),
        
        .decoded_instruction(decoded_instruction)
    );


    always_ff @(posedge clk or posedge reset) begin
        if (reset) begin
            fetch_request_long <= 1'b0;
            fetch_request_next <= 1'b1;
        end else begin
            fetch_request_long <= fetch_request_long_next;
            fetch_request_next <= fetch_request_next_next;
        end
    end

    always_comb begin
        fetch_request_long_next = 1'b0;
        fetch_request_next_next = 1'b0;

        if (fetched_instruction_valid) begin
            if (decoded_instruction.is_long && decoded_instruction.partialy_decoded) begin
                fetch_request_long_next = 1'b1;
            end else begin
                fetch_request_next_next = 1'b1;
            end
        end
    end







    assign instruction_ready = fetched_instruction_valid;
    assign instruction_is_long = decoded_instruction.is_long;
    assign low_instruction_out = fetched_instruction_low;
    assign high_instruction_out = fetched_instruction_high;
    assign decoded_instruction_out = decoded_instruction;

endmodule

`endif
