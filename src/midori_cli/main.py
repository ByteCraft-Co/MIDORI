from __future__ import annotations

import argparse
import subprocess
import tempfile
from pathlib import Path

from midori_cli.formatter import format_source
from midori_cli.pipeline import compile_file
from midori_compiler.errors import MidoriError


def _cmd_build(args: argparse.Namespace) -> int:
    src = Path(args.source)
    out = Path(args.output) if args.output else src.with_suffix(".exe")
    compile_file(src, out, emit_llvm=args.emit_llvm, emit_asm=args.emit_asm)
    print(f"built {out}")
    return 0


def _cmd_run(args: argparse.Namespace) -> int:
    src = Path(args.source)
    with tempfile.TemporaryDirectory(prefix="midori-") as tmp:
        out = Path(tmp) / "program.exe"
        compile_file(src, out)
        proc = subprocess.run([str(out)], check=False)
        return proc.returncode


def _cmd_test(_args: argparse.Namespace) -> int:
    proc = subprocess.run(["py", "-m", "pytest", "-q"], check=False)
    return proc.returncode


def _cmd_fmt(args: argparse.Namespace) -> int:
    target = Path(args.path)
    original = target.read_text(encoding="utf-8")
    formatted = format_source(original)
    target.write_text(formatted, encoding="utf-8")
    print(f"formatted {target}")
    return 0


def _cmd_repl(_args: argparse.Namespace) -> int:
    print("midori repl (type `:quit` to exit)")
    while True:
        try:
            line = input("midori> ").strip()
        except EOFError:
            print()
            return 0
        if line in {":quit", ":q", "quit", "exit"}:
            return 0
        if not line:
            continue
        program = f"fn main() -> Int {{\n  print({line})\n  0\n}}\n"
        with tempfile.TemporaryDirectory(prefix="midori-repl-") as tmp:
            src = Path(tmp) / "repl.mdr"
            exe = Path(tmp) / "repl.exe"
            src.write_text(program, encoding="utf-8")
            try:
                compile_file(src, exe)
            except MidoriError as exc:
                print(exc)
                continue
            subprocess.run([str(exe)], check=False)


def main() -> None:
    parser = argparse.ArgumentParser(prog="midori")
    sub = parser.add_subparsers(dest="command", required=True)

    p_build = sub.add_parser("build", help="compile a .mdr file into an executable")
    p_build.add_argument("source")
    p_build.add_argument("-o", "--output", default=None)
    p_build.add_argument("--emit-llvm", action="store_true", help="write LLVM IR beside output")
    p_build.add_argument("--emit-asm", action="store_true", help="write assembly beside output")
    p_build.set_defaults(fn=_cmd_build)

    p_run = sub.add_parser("run", help="build and run a .mdr file")
    p_run.add_argument("source")
    p_run.set_defaults(fn=_cmd_run)

    p_test = sub.add_parser("test", help="run unit and integration tests")
    p_test.set_defaults(fn=_cmd_test)

    p_fmt = sub.add_parser("fmt", help="format a .mdr source file in-place")
    p_fmt.add_argument("path")
    p_fmt.set_defaults(fn=_cmd_fmt)

    p_repl = sub.add_parser("repl", help="run a minimal expression REPL")
    p_repl.set_defaults(fn=_cmd_repl)

    args = parser.parse_args()
    try:
        code = args.fn(args)
    except MidoriError as exc:
        print(exc)
        raise SystemExit(1) from exc
    raise SystemExit(code)


if __name__ == "__main__":
    main()
