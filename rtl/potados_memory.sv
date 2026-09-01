
module potados_rom #(
    parameter ROM_FILE = "rom.hex",
    parameter LOAD_ROM_FILE = 1'b1,
    parameter logic [15:0] ROM_SIZE = 16'h7fff
)(
    input logic        clk,
    
    input logic[15:0]  address,

    output logic[15:0] rom_data
);
    logic [15:0] memory [16'h0000:ROM_SIZE];

    initial begin
        if (LOAD_ROM_FILE) begin
            $readmemh(ROM_FILE, memory);
        end
    end

    always_ff @(posedge clk) begin
        rom_data <= memory[address];
    end
endmodule

module potados_ram #(
    parameter logic [15:0] RAM_LOW_ADDRESS = 16'h0000,
    parameter logic [15:0] RAM_HIGH_ADDRESS = 16'h7fff
) (
    input logic        clk,
    
    input logic[15:0]  address,

    input logic        store_enable,
    input logic[15:0]  store_data,

    input logic        load_enable,
    output logic[15:0] load_data
);
    logic [15:0] memory [RAM_LOW_ADDRESS:RAM_HIGH_ADDRESS];

    always_ff @(posedge clk) begin
        if (store_enable) begin
            memory[address] <= store_data;
        end
        if (load_enable) begin
            load_data <= memory[address];
        end
    end
endmodule

// Wrapper for optional future expansion of memory mapped peripherals.
module potados_memory #(
    parameter logic [15:0] RAM_LOW_ADDRESS = 16'h0000,
    parameter logic [15:0] RAM_HIGH_ADDRESS = 16'h7fff
) (
    input logic        clk,
    input logic        reset,
    
    input logic[15:0]  address,

    input logic        store_enable,
    input logic[15:0]  store_data,

    input logic        load_enable,
    output logic[15:0] load_data,

    output logic [15:0] io_address,
    output logic        io_read_enable,
    output logic        io_write_enable,
    output logic [15:0] io_write_data,
    input  logic [15:0] io_read_data
);
    // Wires used by internal RAM instance.
    logic[15:0] memory_address;
    logic memory_store_enable;
    logic[15:0] memory_store_data;
    logic memory_load_enable;
    logic[15:0] memory_load_data;
    logic address_is_ram;
    logic load_from_io;


    potados_ram #(
        .RAM_LOW_ADDRESS(RAM_LOW_ADDRESS),
        .RAM_HIGH_ADDRESS(RAM_HIGH_ADDRESS)
    ) ram_inst (
        .clk(clk),
        .address(memory_address),
        .store_enable(memory_store_enable),
        .store_data(memory_store_data),
        .load_enable(memory_load_enable),
        .load_data(memory_load_data)
    );

    always_comb begin
        // Unsigned subtraction makes an address below RAM_LOW_ADDRESS wrap
        // above the valid span, so one comparison covers either RAM base.
        address_is_ram =
            (address - RAM_LOW_ADDRESS) <= (RAM_HIGH_ADDRESS - RAM_LOW_ADDRESS);

        // The data returned this cycle belongs to the most recently accepted
        // load, not necessarily to the address of the next request.
        load_data = load_from_io ? io_read_data : memory_load_data;

        if (address_is_ram) begin
            memory_address = address;
            memory_store_enable = store_enable;
            memory_store_data = store_data;
            memory_load_enable = load_enable;

            io_address = 16'h0000;
            io_read_enable = 1'b0;
            io_write_enable = 1'b0;
            io_write_data = 16'h0000;
        end else begin
            memory_address = 16'h0000;
            memory_store_enable = 1'b0;
            memory_store_data = 16'h0000;
            memory_load_enable = 1'b0;

            io_address = address;
            io_read_enable = load_enable;
            io_write_enable = store_enable;
            io_write_data = store_data;
        end
    end

    always_ff @(posedge clk or posedge reset) begin
        if (reset) begin
            load_from_io <= 1'b0;
        end else if (load_enable) begin
            load_from_io <= !address_is_ram;
        end
    end
endmodule

module potados_program_memory #(
    parameter ROM_FILE = "rom.hex",
    parameter LOAD_ROM_FILE = 1'b1,
    parameter logic [15:0] ROM_SIZE = 16'h7fff
)(
    input logic        clk,
    input logic        reset,
    
    // High when the CPU has decoded the low word of a long instruction and
    // needs the high word on the next clock.
    input logic        request_long_instruction,
    // High when the CPU has accepted the complete instruction currently
    // presented on low_instruction/high_instruction.
    input logic        instruction_accepted,
    // The address to jump to on the next clock.  This is the address of the
    input logic[15:0]  jump_address,
    // High when the CPU has requested a jump to jump_address on the next clock.
    input logic        jump_enable,
    // High when the CPU has requested a halt.  The program memory will stop
    input logic        halt,

    // The low and high words of the instruction currently presented to the CPU.
    output logic[15:0] low_instruction,
    output logic[15:0] high_instruction,
    
    // The address of the low word of the instruction currently presented to the CPU.
    output logic[15:0] instruction_pc,

    // High when low_instruction is valid.  Low when the CPU has accepted it.
    output logic       low_valid,
    // High when high_instruction is valid.  Low when the CPU has accepted it.
    output logic       high_valid,

    output logic       halted
);
    logic [15:0] pc;
    logic [15:0] pc_next;
    logic [15:0] rom_data;
    logic [15:0] rom_data_prev;
    logic [15:0] rom_data_high_prev;

    typedef enum logic [2:0] {
        FETCH_START_SHORT,
        FETCH_SHORT_RESPONSE,
        FETCH_SHORT_HELD,
        FETCH_LONG_RESPONSE,
        FETCH_LONG_HELD,
        HALTED
    } fetch_state_t;

    fetch_state_t fetch_state;
    fetch_state_t fetch_state_next;
    logic [15:0] rom_data_prev_next;
    logic [15:0] rom_data_high_prev_next;


    potados_rom #(
        .ROM_FILE(ROM_FILE),
        .LOAD_ROM_FILE(LOAD_ROM_FILE),
        .ROM_SIZE(ROM_SIZE)
    ) rom_inst (
        .clk(clk),
        .address(pc),
        .rom_data(rom_data)
    );

    always_comb begin
        pc_next = pc;
        fetch_state_next = fetch_state;
        rom_data_prev_next = rom_data_prev;
        rom_data_high_prev_next = rom_data_high_prev;
        low_instruction = 16'h0000;
        high_instruction = 16'h0000;
        instruction_pc = 16'h0000;
        low_valid = 1'b0;
        high_valid = 1'b0;
        halted = 0;

        if (jump_enable) begin
            pc_next = jump_address;
            fetch_state_next = FETCH_START_SHORT;
        end else begin
            if (halt) begin
                fetch_state_next = HALTED;
                low_instruction = 16'h0000;
                high_instruction = 16'h0000;
                instruction_pc = pc - 16'h0001;
                low_valid = 1'b0;
                high_valid = 1'b0;
                halted = 1'b1;
            end else begin
                case (fetch_state)
                    // Entry point for the fetch
                    FETCH_START_SHORT: begin
                        // The ROM samples the current PC on this clock edge.
                        // Advance PC for the following sequential fetch.
                        pc_next = pc + 16'h0001;
                        fetch_state_next = FETCH_SHORT_RESPONSE;
                    end
                    // Fetch short instruction and cerry to next one
                    FETCH_SHORT_RESPONSE: begin
                        low_instruction = rom_data;
                        instruction_pc = pc - 16'h0001;
                        low_valid = 1'b1;
                        if (request_long_instruction) begin
                            // Decode consumed the low word and identified a long instruction.
                            rom_data_prev_next = rom_data;
                            pc_next = pc + 16'h0001;
                            fetch_state_next = FETCH_LONG_RESPONSE;
                        end else if (instruction_accepted) begin
                            // Decode consumed a complete short instruction.
                            pc_next = pc + 16'h0001;
                            fetch_state_next = FETCH_SHORT_RESPONSE;
                        end else begin
                            // The registered ROM will present its next output on
                            // the next clock, so retain this response while decode
                            // is stalled.
                            rom_data_prev_next = rom_data;
                            fetch_state_next = FETCH_SHORT_HELD;
                        end
                    end
                    // If instruction was not accepted, we need to hold it until it is.
                    FETCH_SHORT_HELD: begin
                        low_instruction = rom_data_prev;
                        instruction_pc = pc - 16'h0001;
                        low_valid = 1'b1;
                        if (request_long_instruction) begin
                            pc_next = pc + 16'h0001;
                            fetch_state_next = FETCH_LONG_RESPONSE;
                        end else if (instruction_accepted) begin
                            pc_next = pc + 16'h0001;
                            fetch_state_next = FETCH_SHORT_RESPONSE;
                        end
                    end
                    // We need to fetch the next word of a long instruction
                    // The ROM samples the current PC on this clock edge. and advances the PC
                    FETCH_LONG_RESPONSE: begin
                        low_instruction = rom_data_prev;
                        high_instruction = rom_data;
                        instruction_pc = pc - 16'h0002;
                        low_valid = 1'b1;
                        high_valid = 1'b1;
                        if (instruction_accepted) begin
                            pc_next = pc + 16'h0001;
                            fetch_state_next = FETCH_SHORT_RESPONSE;
                        end else if (halt) begin
                            // Decode has requested a halt.  Stop fetching instructions.
                            fetch_state_next = HALTED;
                        end else begin
                            rom_data_high_prev_next = rom_data;
                            fetch_state_next = FETCH_LONG_HELD;
                        end
                    end
                    // If instruction was not accepted we need to hold it until it is.
                    FETCH_LONG_HELD: begin
                        low_instruction = rom_data_prev;
                        high_instruction = rom_data_high_prev;
                        instruction_pc = pc - 16'h0002;
                        low_valid = 1'b1;
                        high_valid = 1'b1;
                        if (instruction_accepted) begin
                            pc_next = pc + 16'h0001;
                            fetch_state_next = FETCH_SHORT_RESPONSE;
                        end
                    end
                    HALTED: begin
                        low_instruction = 16'h0000;
                        high_instruction = 16'h0000;
                        instruction_pc = pc - 16'h0001;
                        low_valid = 1'b0;
                        high_valid = 1'b0;
                        halted = 1'b1;
                        fetch_state_next = HALTED;
                    end
                    default: begin
                        fetch_state_next = FETCH_START_SHORT;
                    end
                endcase
            end
        end
    end
    

    always_ff @(posedge clk or posedge reset) begin
        if (reset) begin
            pc <= 16'h0000;
            rom_data_prev <= 16'h0000;
            rom_data_high_prev <= 16'h0000;
            fetch_state <= FETCH_START_SHORT;
        end else begin
            pc <= pc_next;
            rom_data_prev <= rom_data_prev_next;
            rom_data_high_prev <= rom_data_high_prev_next;
            fetch_state <= fetch_state_next;
        end
    end
endmodule
