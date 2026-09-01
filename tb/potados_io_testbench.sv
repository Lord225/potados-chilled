`timescale 1ns / 1ps

// A tiny fixed-latency memory-mapped peripheral used only by the cocotb test.
//
//   0x8000: readable/writable output register
//   0x8001: read-only input register
//
// Reads are registered: a request presented before a rising edge produces
// io_read_data immediately after that edge.
module potados_io_test_peripheral (
    input  logic        clk,
    input  logic        reset,
    input  logic [15:0] io_address,
    input  logic        io_read_enable,
    input  logic        io_write_enable,
    input  logic [15:0] io_write_data,
    output logic [15:0] io_read_data,
    input  logic [15:0] input_value,
    output logic [15:0] output_value
);
    always_ff @(posedge clk or posedge reset) begin
        if (reset) begin
            io_read_data <= 16'h0000;
            output_value <= 16'h0000;
        end else begin
            if (io_write_enable && io_address == 16'h8000) begin
                output_value <= io_write_data;
            end

            if (io_read_enable) begin
                case (io_address)
                    16'h8000: io_read_data <= output_value;
                    16'h8001: io_read_data <= input_value;
                    default:  io_read_data <= 16'h0000;
                endcase
            end else begin
                io_read_data <= 16'h0000;
            end
        end
    end
endmodule


module potados_io_testbench (
    input  logic        clk,
    input  logic        reset,
    input  logic [15:0] peripheral_input,
    output logic [15:0] peripheral_output,
    output logic [15:0] io_address,
    output logic        io_read_enable,
    output logic        io_write_enable,
    output logic [15:0] io_write_data,
    output register_file_t registers_out,
    output logic          potados_done
);
    logic [15:0] io_read_data;

    // Internal RAM occupies the low half of memory.  The test peripheral owns
    // the first two addresses above it.
    potados #(
        .LOAD_ROM_FILE(1'b0),
        .RAM_LOW_ADDRESS(16'h0000),
        .RAM_HIGH_ADDRESS(16'h7FFF)
    ) cpu (
        .clk(clk),
        .reset(reset),
        .registers_out(registers_out),
        .potados_done(potados_done),
        .pc_out(),
        .io_address(io_address),
        .io_read_enable(io_read_enable),
        .io_write_enable(io_write_enable),
        .io_write_data(io_write_data),
        .io_read_data(io_read_data)
    );

    potados_io_test_peripheral peripheral (
        .clk(clk),
        .reset(reset),
        .io_address(io_address),
        .io_read_enable(io_read_enable),
        .io_write_enable(io_write_enable),
        .io_write_data(io_write_data),
        .io_read_data(io_read_data),
        .input_value(peripheral_input),
        .output_value(peripheral_output)
    );
endmodule
