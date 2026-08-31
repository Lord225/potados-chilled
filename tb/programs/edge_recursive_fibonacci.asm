; fib(6) using R2 as both the argument and return value.
;
; Each recursive frame saves its return address and original argument. The
; fib(n - 1) result is then kept on the same stack while fib(n - 2) runs.
LLI SP, 0x40
LLI R2, 6
JAL R7, fibonacci
HALT

fibonacci:
    LLI R3, 2
    JL R2, R3, fibonacci_base_case

    PUSH R7
    PUSH R2

    ADDI R2, -1
    JAL R7, fibonacci

    POP R3
    PUSH R2
    ADD R2, R3, ZERO
    ADDI R2, -2
    JAL R7, fibonacci

    POP R3
    ADD R2, R2, R3
    POP R7
    JMPR R7

fibonacci_base_case:
    JMPR R7
