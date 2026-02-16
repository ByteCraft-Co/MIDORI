from __future__ import annotations

import argparse
import importlib.metadata
import subprocess
import tempfile
import textwrap
import tomllib
from pathlib import Path

from midori_cli.formatter import format_source
from midori_cli.pipeline import check_file, compile_file
from midori_compiler.errors import MidoriError


def _resolve_version() -> str:
    try:
        return importlib.metadata.version("midori")
    except importlib.metadata.PackageNotFoundError:
        pyproject = Path(__file__).resolve().parents[2] / "pyproject.toml"
        try:
            data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
            return str(data["project"]["version"])
        except (FileNotFoundError, KeyError, OSError, tomllib.TOMLDecodeError):
            return "0.0.0-dev"


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


def _cmd_check(args: argparse.Namespace) -> int:
    src = Path(args.source)
    check_file(src)
    print(f"checked {src}")
    return 0


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


def _cmd_new(args: argparse.Namespace) -> int:
    target = Path(args.name)
    if target.exists():
        if not target.is_dir():
            print(f"target path exists and is not a directory: {target}")
            return 1
        if any(target.iterdir()):
            print(f"project directory is not empty: {target}")
            return 1

    tests_dir = target / "tests"
    tests_dir.mkdir(parents=True, exist_ok=True)

    main_src = textwrap.dedent(
        f"""\
        fn main() -> Int {{
          print("hello from {target.name}")
          0
        }}
        """
    )
    smoke_test = textwrap.dedent(
        """\
        fn main() -> Int {
          let value := 21 + 21
          if value == 42 {
            print("ok")
          } else {
            print("fail")
          }
          0
        }
        """
    )

    (target / "main.mdr").write_text(main_src, encoding="utf-8")
    (tests_dir / "smoke_test.mdr").write_text(smoke_test, encoding="utf-8")
    print(f"created project {target}")
    print(f"  - {target / 'main.mdr'}")
    print(f"  - {tests_dir / 'smoke_test.mdr'}")
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
            except Exception as exc:  # noqa: BLE001
                print(f"internal compiler error: {exc}")
                continue
            subprocess.run([str(exe)], check=False)


def main() -> None:
    parser = argparse.ArgumentParser(prog="midori")
    parser.add_argument("--version", action="version", version=f"midori {_resolve_version()}")
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

    p_check = sub.add_parser("check", help="run frontend checks without building an executable")
    p_check.add_argument("source")
    p_check.set_defaults(fn=_cmd_check)

    p_test = sub.add_parser("test", help="run unit and integration tests")
    p_test.set_defaults(fn=_cmd_test)

    p_fmt = sub.add_parser("fmt", help="format a .mdr source file in-place")
    p_fmt.add_argument("path")
    p_fmt.set_defaults(fn=_cmd_fmt)

    p_new = sub.add_parser("new", help="create a new MIDORI starter project")
    p_new.add_argument("name")
    p_new.set_defaults(fn=_cmd_new)

    p_repl = sub.add_parser("repl", help="run a minimal expression REPL")
    p_repl.set_defaults(fn=_cmd_repl)

    args = parser.parse_args()
    try:
        code = args.fn(args)
    except MidoriError as exc:
        print(exc)
        raise SystemExit(1) from exc
    except Exception as exc:  # noqa: BLE001
        print(f"internal compiler error: {exc}")
        raise SystemExit(1) from exc
    raise SystemExit(code)


if __name__ == "__main__":
    main()
