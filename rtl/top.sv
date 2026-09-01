`timescale 1ns / 1ps
`include "potados.sv"

module top #(
    // Keep the default build self-contained.  Supply another file with
    // `chparam -set ROM_FILE \"your-program.hex\" top` when needed.
    parameter ROM_FILE = "rom.hex"
) (
    input  logic       clk,
    input  logic       btn1,
    input  logic       btn2,
    output logic [5:0] led
);
    logic [15:0] io_address;
    logic        io_read_enable;
    logic        io_write_enable;
    logic [15:0] io_write_data;
    logic [15:0] io_read_data;

    logic [15:0] io_registers[0:5]; // One for each LED

    integer pwm_counter = 0;

    potados #(
        .ROM_FILE(ROM_FILE),
        .RAM_LOW_ADDRESS(16'h0000),
        .RAM_HIGH_ADDRESS(16'h1fff),
        .ROM_SIZE(16'h1fff)
    ) potados_inst (
        .clk(clk),
        .reset(!btn1),
        .io_address(io_address),
        .io_read_enable(io_read_enable),
        .io_write_enable(io_write_enable),
        .io_write_data(io_write_data),
        .io_read_data(io_read_data)
    );

    always_ff @(posedge clk) begin
        if (io_write_enable) begin
            case(io_address[3:0])
                4'h0: io_registers[0] <= io_write_data;
                4'h1: io_registers[1] <= io_write_data;
                4'h2: io_registers[2] <= io_write_data;
                4'h3: io_registers[3] <= io_write_data;
                4'h4: io_registers[4] <= io_write_data;
                4'h5: io_registers[5] <= io_write_data;
                default: ; // Do nothing for invalid IO write
            endcase
        end
        if (io_read_enable) begin
            case (io_address[3:0])
                4'h0: io_read_data <= io_registers[0];
                4'h1: io_read_data <= io_registers[1];
                4'h2: io_read_data <= io_registers[2];
                4'h3: io_read_data <= io_registers[3];
                4'h4: io_read_data <= io_registers[4];
                4'h5: io_read_data <= io_registers[5];
                4'h6: io_read_data <= {15'b0, !btn1};  // Read button state
                4'h7: io_read_data <= {15'b0, !btn2};  // Read button state
                default: io_read_data <= 16'h0000;     // Return 0 for invalid
            endcase
        end else begin
            io_read_data <= 16'h0000;
        end

        if (pwm_counter == 255) begin
            pwm_counter <= 0;
        end else begin
            pwm_counter <= pwm_counter + 1;
        end

        if (!btn1) begin
            // Reset IO registers when btn1 is pressed
            for (int i = 0; i < 6; i++) begin
                io_registers[i] <= 16'h0000;
                pwm_counter <= 0;
            end
        end
    end

    always_comb begin
        for (int i = 0; i < 6; i++) begin
            // Tang Nano 9K LEDs are active-low.
            led[i] = (pwm_counter < io_registers[i]) ? 1'b0 : 1'b1;
        end
    end
endmodule
