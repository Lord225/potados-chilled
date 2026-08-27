`timescale 1ns / 1ps
`include "potados_memory.sv"

module top #(
    parameter int unsigned COUNT_WIDTH = 6
) (
    input  logic                   clk,
    input  logic                   btn1,
    input  logic                   btn2,
    output logic [COUNT_WIDTH-1:0] led
);
    logic [COUNT_WIDTH-1:0] count;
    logic [15:0] ram_load_data;

    potados_ram ram_inst (
        .clk(clk),
        .address({{(16 - COUNT_WIDTH){1'b0}}, count}),
        .store_enable(btn1),
        .store_data({{(16 - COUNT_WIDTH){1'b0}}, count}),
        .load_enable(1'b1),
        .load_data(ram_load_data)
    );

    always_ff @(posedge clk) begin
        if (btn2) begin
            count <= '0;
        end else if (btn1) begin
            count <= count + 1'b1;
        end
    end

    assign led = ram_load_data[COUNT_WIDTH-1:0];
endmodule
