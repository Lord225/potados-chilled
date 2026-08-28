from __future__ import annotations

import argparse
from pathlib import Path
import sys

from .assembler import AssemblerError, OutputFormat, assemble, assemble_file, write_output


FORMAT_CHOICES = ("hex", "annotated-hex", "hex-comments", "bytecode", "binary")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Assemble POTADOS source code")
    parser.add_argument("source", help="assembly input file, or '-' for standard input")
    parser.add_argument("-o", "--output", help="output path; defaults to standard output")
    parser.add_argument("-f", "--format", choices=FORMAT_CHOICES, default="hex", help="output format (default: hex)")
    return parser


def run(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.source == "-":
            result = assemble(sys.stdin.read(), filename="<stdin>")
        else:
            result = assemble_file(Path(args.source))
        output_format: OutputFormat = "annotated-hex" if args.format == "hex-comments" else args.format
        if args.output:
            write_output(result, Path(args.output), output_format)
        else:
            rendered = result.render(output_format)
            if isinstance(rendered, bytes):
                sys.stdout.buffer.write(rendered)
            else:
                sys.stdout.write(rendered)
        return 0
    except AssemblerError as error:
        print(error, file=sys.stderr)
        return 1
    except OSError as error:
        print(f"I/O error: {error}", file=sys.stderr)
        return 1


def main() -> None:
    raise SystemExit(run())
