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


typedef struct packed {
    logic [15:0] SP;
    logic [15:0] R1;
    logic [15:0] R2;
    logic [15:0] R3;
    logic [15:0] R4;
    logic [15:0] R5;
    logic [15:0] R6;
    logic [15:0] R7;    
} register_file_t;


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
    MEMORY_NONE,
    MEMORY_LOAD,
    MEMORY_STORE
} memory_op_t;

typedef enum logic [1:0] {
    STACK_NONE,
    STACK_PUSH,
    STACK_POP
} stack_op_t;

typedef enum logic [1:0] {
    JUMP_NONE,
    JUMP_CONDITIONAL,
    JUMP_ALWAYS
} jump_op_t;

typedef enum logic [2:0] {
    // Nothing is source
    WB_NONE,
    // The ALU is the source
    WB_ALU,
    // The RAM is the source
    WB_MEMORY,
    // The IMM is the source
    WB_IMMEDIATE,
    // The FPU is the source
    WB_FPU,
    // The PC is the source
    WB_RETURN_ADDRESS
} writeback_source_t;


typedef struct packed {
    // Whenever the Instruction is decoded and valid
    logic valid;
    // Whenever the instruction is only half decoded
    logic partialy_decoded;
    // Whenever instruction has 16 bit immediate
    logic is_long;
    // The program counter value of the instruction
    logic [15:0] pc;
    // The final value for first (A) argument (taken from reg or imm)
    logic [15:0] src_a_value;
    // The final value for second (B) argument (taken from reg or imm)
    logic [15:0] src_b_value;
    // The final value of the SP register
    logic [15:0] stack_pointer;
    // The destination register for the instruction (if any), look at write back.
    logic [2:0] dst;
    
    // Selected ALU operation for the instruction (if any)
    alu_op_t alu_op;
    // Selected CMP operation for the instruction (if any)
    cmp_op_t cmp_op;

    // Selected FPU operation for the instruction (if any)
    fpu_op_t fpu_op;

    // Selected Memory operation for the instruction (if any)
    memory_op_t memory_op;
    // Selected Stack logic for the instruction (if any)
    stack_op_t stack_op;
    // Selected Jump logic for the instruction (if any)
    jump_op_t jump_op;
    // Selected Writeback source for the instruction (if any)
    writeback_source_t writeback_source;

    // Whenever the cpu should halt
    logic halt;
} execute_stage_t;


`endif
