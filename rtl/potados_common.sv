`ifndef POTADOS_COMMON_SV
`define POTADOS_COMMON_SV

typedef enum logic[4:0] {
    ALU_NONE, 
    ALU_ADD,
    ALU_SUB,
    ALU_AND,
    ALU_OR,
    ALU_XOR,
    ALU_NOT,
    ALU_MUL,
    ALU_SH,
    ALU_ASH,
    ALU_SET,
    ALU_CMP
} alu_op_t ;

typedef enum logic[3:0] {  
    CMP_NONE,
    CMP_GE,
    CMP_L,
    CMP_E,
    CMP_NE,
    CMP_AE,
    CMP_B
} cmp_op_t;

typedef enum logic[1:0] {
    CMP_RESULT_NONE,
    CMP_RESULT_TRUE,
    CMP_RESULT_FALSE
} cmp_result_t;

typedef enum logic[3:0] {
    FPU_NONE,
    FPU_ADD,
    FPU_SUB,
    FPU_MUL,
    FPU_DIV,
    FPU_FTOI,
    FPU_ITOF,
    FPU_UTOF
} fpu_op_t;

typedef enum logic[2:0] {
    PIPELINE_STALL_NONE,
    PIPELINE_STALL_EXECUTE,
    PIPELINE_STALL_MEMORY,
    PIPELINE_STALL_WRITEBACK // Should not be possible, but included for completeness.
} pipeline_stall_t;


typedef struct packed {
    logic [15:0] SP;
    logic [15:0] R2;
    logic [15:0] R3;
    logic [15:0] R4;
    logic [15:0] R5;
    logic [15:0] R6;
    logic [15:0] R7;
} register_file_t;

typedef struct packed {
    // One bit for each architectural register with a future writeback.
    // ZERO (bit 0) is always clear.
    logic [7:0] pending_write;
} register_status_t;


typedef enum logic[3:0] {
    OP_ALU,
    OP_SET,
    OP_SH,
    OP_ASH,
    OP_ADDI,
    OP_LDIMM,
    OP_LD,
    OP_ST,
    OP_LDSP,
    OP_STSP,
    OP_CJUMP,
    OP_JUMP,
    OP_STACK,
    OP_JUMP_REG,
    OP_FPU,
    OP_HALT
} op_primary_t;


typedef struct packed {
    op_primary_t op_primary;
    logic [2:0] dst;
    logic [2:0] op_secondary;
    logic [2:0] src_a;
    logic [2:0] src_b;
    logic [15:0] immediate;
    logic partialy_decoded;
    logic is_long;
} decoded_instruction_t;

typedef enum logic [1:0] {
    // No data-memory operation is performed.
    MEMORY_NONE,
    // Read RAM at the effective address produced by the ALU.
    MEMORY_LOAD,
    // Write memory_write_data to RAM at the effective address produced by the ALU.
    MEMORY_STORE
} memory_op_t;

typedef enum logic [1:0] {
    // The stack pointer is not modified.
    STACK_POINTER_NONE,
    // The stack pointer is explicitly written to a new value.
    STACK_POINTER_WRITE,
    // Increment SP after the memory operation (used by PUSH).
    STACK_POINTER_INCREMENT,
    // Decrement SP after the memory operation (used by POP).
    STACK_POINTER_DECREMENT
} stack_pointer_op_t;

// Addresses requested from the two combinational register-file read ports.
typedef struct packed {
    logic [2:0] address_a;
    logic [2:0] address_b;
} register_read_request_t;

// Values returned by the register-file read ports and stack-pointer helpers.
typedef struct packed {
    logic [15:0] data_a;
    logic [15:0] data_b;
    logic [15:0] stack_pointer;
    logic [15:0] stack_pointer_decremented;
} register_read_response_t;

// A register-file write committed by the writeback stage.
typedef struct packed {
    logic        write_enable;
    logic [2:0]  write_address;
    logic [15:0] write_data;
} register_write_request_t;

// An explicit stack-pointer write or an automatic stack-pointer update.
typedef struct packed {
    logic [15:0] write_data;
    stack_pointer_op_t operation;
} stack_pointer_request_t;

typedef enum logic [1:0] {
    // No jump is performed
    JUMP_NONE,
    // The jump is performed if the condition is met
    JUMP_CONDITIONAL,
    // The jump will be performed
    JUMP_ALWAYS
} jump_op_t;

// What should be written into dst
typedef enum logic [2:0] {
    // Nothing is source
    WB_NONE,
    // The ALU is the source
    WB_ALU,
    // The RAM is the source
    WB_MEMORY,
    // The FPU is the source
    WB_FPU,
    // The address of the following instruction is the source (JAL/JALR).
    WB_RETURN_ADDRESS
} writeback_source_t;



// A decoded instruction at the input of the execute stage.
//
// Decode/register-read prepares this packet, replacing register indices and
// immediates with their final operand values.  Execute must use only this
// packet: it drives the ALU, comparator, FPU, memory-address calculation,
// stack update, control-flow decision, and register writeback.
typedef struct packed {
    // A complete instruction is present.  No side effect is permitted when 0.
    logic valid;

    // Address of the first instruction word
    logic [15:0] pc;
    // Address of the first word of the next sequential instruction.
    logic [15:0] next_pc;

    // Fully prepared execution operands.  Each may originate from a register,
    // immediate, stack pointer, or other decode-time selection.
    logic [15:0] operand_a_value;
    logic [15:0] operand_b_value;
    // Data presented to RAM during a memory store operation.
    logic [15:0] memory_write_data;
    // Address selected for a control-flow transfer.
    logic [15:0] jump_target;

    // Register written during writeback when writeback_source is not WB_NONE.
    logic [2:0] dst;

    // Functional-unit operations.
    alu_op_t alu_op;
    cmp_op_t cmp_op;
    fpu_op_t fpu_op;

    // MEMORY_LOAD consumes the ALU result as an address and writes RAM data
    // back later.  MEMORY_STORE writes memory_write_data at that address.
    memory_op_t memory_op;
    // Stack-pointer update performed for this instruction.
    stack_pointer_op_t stack_pointer_op;

    // Selects whether a branch is taken and which prepared value supplies its
    // target address.
    jump_op_t jump_op;
    // Selects the value eventually written to dst, if any.
    writeback_source_t writeback_source;

    // Stops architectural execution after this instruction.
    logic halt;
} execute_stage_t;

// Values produced by execute and consumed by the data-memory stage.
typedef struct packed {
    // A completed execute-stage entry is present.
    logic valid;

    // Result produced by the integer ALU; also the effective RAM address for
    // MEMORY_LOAD and MEMORY_STORE.
    logic [15:0] alu_result;
    // Data presented to RAM for MEMORY_STORE.
    logic [15:0] memory_write_data;
    // Result supplied by the optional FPU execution unit.
    logic [15:0] fpu_result;
    // Address of the next sequential instruction, used by JAL/JALR writeback.
    logic [15:0] next_pc;

    // Data-memory request and stack-pointer update associated with this entry.
    memory_op_t memory_op;
    stack_pointer_op_t stack_pointer_op;

    // Destination and source selection used by the writeback stage.
    logic [2:0] dst;
    writeback_source_t writeback_source;
} memory_stage_t;

typedef struct packed {
    logic valid;

    // from memory stage
    logic [15:0] alu_result;
    logic [15:0] fpu_result;
    logic [15:0] next_pc;

    logic [2:0] dst;
    
    stack_pointer_op_t stack_pointer_op;

    writeback_source_t writeback_source;
} writeback_stage_t;


`endif
