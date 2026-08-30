`ifndef POTADOS_SCOREBOARD_SV
`define POTADOS_SCOREBOARD_SV

`timescale 1ns / 1ns
`include "potados_common.sv"


// TODO: Rewrite to make it more readable & easy to work with
// 1) All inputs explicit, let's assume 3 channels for reserve and release
// 2) Must add memory adress reservation
// 3) We even must consider adding two memory adresses.

// Tracks architectural registers that will be written by instructions already
// accepted into the pipeline. It is deliberately separate from the register
// file: register values are architectural state, while this mask is pipeline
// control state.
module potados_scoreboard (
    input logic clk,
    input logic reset,

    // Registers written by an instruction entering execute this clock.
    input logic [7:0] reserve_write_mask,
    // Registers whose in-flight writes commit in writeback this clock.
    input logic [7:0] release_write_mask,

    output register_status_t register_status
);
    register_status_t register_status_next;
    integer register_index;

    always_comb begin
        register_status_next = register_status;

        // Evaluate reservation and release independently for every register.
        // A reservation wins when an older writeback releases the same one.
        for (register_index = 0; register_index < 8; register_index = register_index + 1) begin
            case ({
                reserve_write_mask[register_index],
                release_write_mask[register_index]
            })
                2'b00: begin
                    register_status_next.pending_write[register_index] = register_status.pending_write[register_index];
                end
                2'b01: begin
                    register_status_next.pending_write[register_index] = 1'b0;
                end
                2'b10: begin
                    register_status_next.pending_write[register_index] = 1'b1;
                end
                2'b11: begin
                    register_status_next.pending_write[register_index] = 1'b1;
                end
                default: begin
                    register_status_next.pending_write[register_index] = 1'b0;
                end
            endcase
        end

        register_status_next.pending_write[3'b000] = 1'b0;
    end

    always_ff @(posedge clk or posedge reset) begin
        if (reset) begin
            register_status <= '0;
        end else begin
            register_status <= register_status_next;
        end
    end
endmodule

`endif
