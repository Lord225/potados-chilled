set shell := ["zsh", "-cu"]

default: build

build:
    mkdir -p build
    yosys -p "read_verilog -sv rtl/top.sv; synth_gowin -top top -json build/top.json -family gw2a"
    nextpnr-himbaechel --json build/top.json --write build/top_pnr.json --device GW2AR-LV18QN88C8/I7 --vopt family=GW2A-18C --vopt cst=constraints/tangnano20k.cst
    gowin_pack -d GW2A-18C -o build/top.fs build/top_pnr.json

test:
    uv run pytest -q

program: build
    openFPGALoader -b tangnano20k build/top.fs

flash: build
    openFPGALoader -b tangnano20k -f build/top.fs

clean:
    rm -rf build
