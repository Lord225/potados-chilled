
module potados_rom #(
    parameter ROM_FILE = "rom.hex",
    parameter LOAD_ROM_FILE = 1'b1
)(
    input logic        clk,
    
    input logic[15:0]  address,

    output logic[15:0] rom_data
);
    logic [15:0] memory [16'h0000:16'hffff];

    integer word_index;
    initial begin
        for (word_index = 0; word_index < 65536; word_index = word_index + 1) begin
            memory[word_index] = 16'h0000;
        end
        if (LOAD_ROM_FILE) begin
            $readmemh(ROM_FILE, memory);
        end
    end

    always_ff @(posedge clk) begin
        rom_data <= memory[address];
    end
endmodule

module potados_ram (
    input logic        clk,
    
    input logic[15:0]  address,

    input logic        store_enable,
    input logic[15:0]  store_data,

    input logic        load_enable,
    output logic[15:0] load_data
);
    logic [15:0] memory [16'h0000:16'hffff];

    always_ff @(posedge clk) begin
        if (store_enable) begin
            memory[address] <= store_data;
        end
        if (load_enable) begin
            load_data <= memory[address];
        end else begin
            load_data <= 16'h0000;
        end
    end
endmodule

// Wrapper for optional future expansion of memory mapped peripherals.
module potados_memory (
    input logic        clk,
    
    input logic[15:0]  address,

    input logic        store_enable,
    input logic[15:0]  store_data,

    input logic        load_enable,
    output logic[15:0] load_data
);
    potados_ram ram_inst (
        .clk(clk),
        .address(address),
        .store_enable(store_enable),
        .store_data(store_data),
        .load_enable(load_enable),
        .load_data(load_data)
    );
endmodule

module potados_program_memory #(
    parameter ROM_FILE = "rom.hex",
    parameter LOAD_ROM_FILE = 1'b1
)(
    input logic        clk,
    input logic        reset,
    
    input logic        request_long_instruction,
    input logic        request_next_instruction,
    input logic[15:0]  jump_address,
    input logic        jump_enable,

    output logic[15:0] low_instruction,
    output logic[15:0] high_instruction,
    output logic[15:0] instruction_pc,
    output logic       low_valid,
    output logic       high_valid
);
    logic [15:0] pc;
    logic [15:0] pc_next;
    logic [15:0] rom_data;
    logic [15:0] rom_data_prev;

    typedef enum logic [1:0] {
        FETCH_IDLE,
        FETCH_SHORT_RESPONSE,
        FETCH_LONG_RESPONSE
    } fetch_state_t;

    fetch_state_t fetch_state;
    fetch_state_t fetch_state_next;
    logic [15:0] rom_data_prev_next;


    potados_rom #(
        .ROM_FILE(ROM_FILE),
        .LOAD_ROM_FILE(LOAD_ROM_FILE)
    ) rom_inst (
        .clk(clk),
        .address(pc),
        .rom_data(rom_data)
    );

    always_comb begin
        pc_next = pc;
        fetch_state_next = fetch_state;
        rom_data_prev_next = rom_data_prev;
        low_instruction = 16'h0000;
        high_instruction = 16'h0000;
        instruction_pc = 16'h0000;
        low_valid = 1'b0;
        high_valid = 1'b0;

        if (jump_enable) begin
            pc_next = jump_address;
            fetch_state_next = FETCH_IDLE;
        end else begin
            case (fetch_state)
                FETCH_IDLE: begin
                    if (request_long_instruction) begin
                        // PC already points to the high word. The preceding
                        // short response was saved in rom_data_prev.
                        pc_next = pc + 16'h0001;
                        fetch_state_next = FETCH_LONG_RESPONSE;
                    end else if (request_next_instruction) begin
                        pc_next = pc + 16'h0001;
                        fetch_state_next = FETCH_SHORT_RESPONSE;
                    end
                end
                FETCH_SHORT_RESPONSE: begin
                    low_instruction = rom_data;
                    instruction_pc = pc - 16'h0001;
                    low_valid = 1'b1;
                    // Retain this word in case the decoder requests its high
                    // word on the following fetch command.
                    rom_data_prev_next = rom_data;
                    fetch_state_next = FETCH_IDLE;
                end
                FETCH_LONG_RESPONSE: begin
                    low_instruction = rom_data_prev;
                    high_instruction = rom_data;
                    instruction_pc = pc - 16'h0002;
                    low_valid = 1'b1;
                    high_valid = 1'b1;
                    fetch_state_next = FETCH_IDLE;
                end
                default: begin
                    fetch_state_next = FETCH_IDLE;
                end
            endcase
        end
    end
    

    always_ff @(posedge clk or posedge reset) begin
        if (reset) begin
            pc <= 16'h0000;
            rom_data_prev <= 16'h0000;
            fetch_state <= FETCH_IDLE;
        end else begin
            pc <= pc_next;
            rom_data_prev <= rom_data_prev_next;
            fetch_state <= fetch_state_next;
        end
    end
endmodule
