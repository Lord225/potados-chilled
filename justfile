set shell := ["zsh", "-cu"]

default: build

assemble:
    asm/.venv/bin/potados-asm demo.asm -o rom.hex

build: assemble
    mkdir -p build
    # The current OSS CAD Suite apycula packer cannot encode a DSP attribute
    # emitted for inferred MULT18X18 cells.  Keep MUL functional in LUT/ALU
    # fabric until that toolchain issue is fixed.
    yosys -p "read_verilog -sv rtl/top.sv; synth_gowin -top top -json build/top.json -family gw1n -nodsp"
    nextpnr-himbaechel --json build/top.json --write build/top_pnr.json --device GW1NR-LV9QN88PC6/I5 --vopt family=GW1N-9C --vopt cst=constraints/tangnano9k.cst --freq 27
    gowin_pack -d GW1N-9C -o build/top.fs build/top_pnr.json

test:
    uv run pytest -q

program: build
    openFPGALoader -b tangnano9k build/top.fs

flash: build
    openFPGALoader -b tangnano9k -f build/top.fs

clean:
    rm -rf build
