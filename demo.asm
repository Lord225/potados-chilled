; POTADOS Tang Nano 20K demonstration program.
; 0x8000..0x8005  PWM brightness registers for LED0..LED5
; 0x8006           button 1 (also wired as CPU reset, so normally 0 here)
; 0x8007           button 2

; R2 = IO base address, 0x8000.
LUI R2, 0x80
; R3 = brightness written to each LED PWM register.
LLI R3, 0x0000

; R5 - Where to count
LUI R5, 0xFF

loop:
    ST R3, [R2 + 0]  ; LED0
    ST R3, [R2 + 1]  ; LED1
    ST R3, [R2 + 2]  ; LED2
    ST R3, [R2 + 3]  ; LED3
    ST R3, [R2 + 4]  ; LED4
    ST R3, [R2 + 5]  ; LED5
    ADDI R3, R3, 1
    
    LUI R4, 0x01 ; 0x0100
    JB R3, R4, skip 
        LLI R3, 0x0000
    skip:

    LLI R4, 0x0000
    delay:
        ADDI R4, R4, 1
        JNE R4, R5, delay

    JMP loop

HALT
