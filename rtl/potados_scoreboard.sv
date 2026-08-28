`ifndef POTADOS_SCOREBOARD_SV
`define POTADOS_SCOREBOARD_SV

`timescale 1ns / 1ns
`include "potados_common.sv"

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

    always_comb begin
        // A newly issued instruction wins over a retiring instruction when
        // both refer to the same register.
        register_status_next.pending_write =
            (register_status.pending_write & ~release_write_mask)
            | reserve_write_mask;
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
