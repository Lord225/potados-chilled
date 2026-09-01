`timescale 1ns / 1ps

// Minimal Gowin RAM-inference reproducer.
// 
// Sequence after reset:
//   1. write 0xcafe to RAM[1]
//   2. request a read from RAM[1]
//   3. switch to an IO write at 0x8000 and capture the RAM read response
//
// Expected result: 0xcafe.
// LED0 on  = pass; LED1 on = fail.
module bram_inference_repro #(
    // 0 reproduces the original POTADOS RAM behaviour.  1 lets the BSRAM
    // keep its prior response while no read request is present.
    parameter bit HOLD_READ_DATA = 1'b0
) (
    input  logic       clk,
    input  logic       btn1,
    output logic [5:0] led
);
    localparam logic [15:0] RAM_LAST = 16'h00ff;
    localparam logic [15:0] EXPECTED = 16'hcafe;

    typedef enum logic [2:0] {
        RESET,
        WRITE_RAM,
        READ_RAM,
        WRITE_IO,
        CHECK,
        DONE
    } state_t;

    state_t state;
    logic [15:0] memory [16'h0000:RAM_LAST];
    logic [15:0] address;
    logic        store_enable;
    logic        load_enable;
    logic [15:0] store_data;
    logic        address_is_ram;
    logic [15:0] ram_address;
    logic        ram_store_enable;
    logic        ram_load_enable;
    logic [15:0] ram_load_data;
    logic [15:0] io_captured_data;
    logic        passed;

    always_comb begin
        address = 16'h0000;
        store_enable = 1'b0;
        load_enable = 1'b0;
        store_data = 16'h0000;

        case (state)
            WRITE_RAM: begin
                address = 16'h0001;
                store_enable = 1'b1;
                store_data = EXPECTED;
            end
            READ_RAM: begin
                address = 16'h0001;
                load_enable = 1'b1;
            end
            WRITE_IO: begin
                address = 16'h8000;
                store_enable = 1'b1;
            end
            default: ;
        endcase

        address_is_ram = address <= RAM_LAST;
        ram_address = address_is_ram ? address : 16'h0000;
        ram_store_enable = address_is_ram && store_enable;
        ram_load_enable = address_is_ram && load_enable;
    end

    // This is intentionally the same inferred-RAM style as potados_ram.
    // The hold form permits Yosys to use the BSRAM clock-enable as a true
    // read enable.  The clear form forces a read/update on every clock.
    generate
        if (HOLD_READ_DATA) begin : gen_hold_read_data
            always_ff @(posedge clk) begin
                if (ram_store_enable) begin
                    memory[ram_address[7:0]] <= store_data;
                end
                if (ram_load_enable) begin
                    ram_load_data <= memory[ram_address[7:0]];
                end
            end
        end else begin : gen_clear_read_data
            always_ff @(posedge clk) begin
                if (ram_store_enable) begin
                    memory[ram_address[7:0]] <= store_data;
                end
                if (ram_load_enable) begin
                    ram_load_data <= memory[ram_address[7:0]];
                end else begin
                    ram_load_data <= 16'h0000;
                end
            end
        end
    endgenerate

    always_ff @(posedge clk or negedge btn1) begin
        if (!btn1) begin
            state <= RESET;
            io_captured_data <= 16'h0000;
            passed <= 1'b0;
        end else begin
            case (state)
                RESET:     state <= WRITE_RAM;
                WRITE_RAM: state <= READ_RAM;
                READ_RAM:  state <= WRITE_IO;
                WRITE_IO: begin
                    io_captured_data <= ram_load_data;
                    state <= CHECK;
                end
                CHECK: begin
                    passed <= io_captured_data == EXPECTED;
                    state <= DONE;
                end
                default: state <= DONE;
            endcase
        end
    end

    always_comb begin
        led = 6'b111111;
        if (state == DONE) begin
            led[0] = passed ? 1'b0 : 1'b1;
            led[1] = passed ? 1'b1 : 1'b0;
        end
    end
endmodule
