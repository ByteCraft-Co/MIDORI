from __future__ import annotations

import argparse
import importlib.metadata
import os
import re
import shlex
import subprocess
import sys
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


def _print_banner(version: str) -> None:
    print("+--------------------------------------------------------------+")
    print(f"| MIDORI Terminal v{version:<44}|")
    print("| Enter Midori expressions directly, or use :commands.        |")
    print("| Type :help for commands. Type :quit to exit.                |")
    print("+--------------------------------------------------------------+")


def _parse_words(payload: str) -> list[str] | None:
    try:
        return shlex.split(payload, posix=False)
    except ValueError as exc:
        print(f"command parse error: {exc}")
        return None


def _parse_build_args(args: list[str]) -> tuple[Path, Path, bool, bool] | None:
    source: str | None = None
    output: str | None = None
    emit_llvm = False
    emit_asm = False

    i = 0
    while i < len(args):
        token = args[i]
        if token == "--emit-llvm":
            emit_llvm = True
        elif token == "--emit-asm":
            emit_asm = True
        elif token in {"-o", "--output"}:
            i += 1
            if i >= len(args):
                print("missing value for -o/--output")
                return None
            output = args[i]
        elif token.startswith("-"):
            print(f"unknown build option: {token}")
            return None
        elif source is None:
            source = token
        else:
            print(f"unexpected build argument: {token}")
            return None
        i += 1

    if source is None:
        print("usage: :build <source> [-o output] [--emit-llvm] [--emit-asm]")
        return None

    src_path = Path(source)
    out_path = Path(output) if output else src_path.with_suffix(".exe")
    return src_path, out_path, emit_llvm, emit_asm


DECLARATION_START_RE = re.compile(r"^(error|fn|struct|enum|trait|extern)\b")
MAIN_FN_RE = re.compile(r"^\s*fn\s+main\s*\(", re.MULTILINE)


def _brace_delta(line: str) -> int:
    depth = 0
    in_string = False
    escaped = False
    for ch in line:
        if in_string:
            if escaped:
                escaped = False
                continue
            if ch == "\\":
                escaped = True
                continue
            if ch == '"':
                in_string = False
            continue

        if ch == '"':
            in_string = True
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
    return depth


def _looks_like_declaration_start(line: str) -> bool:
    return bool(DECLARATION_START_RE.match(line))


def _contains_main_fn(source: str) -> bool:
    return bool(MAIN_FN_RE.search(source))


def _scaffold_project(target: Path) -> int:
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


class MidoriTerminal:
    def __init__(self, *, show_banner: bool = True) -> None:
        self._show_banner = show_banner
        self._version = _resolve_version()
        self._session_declarations: list[str] = []
        self._pending_declaration: list[str] = []
        self._pending_brace_depth = 0

    def run(self) -> int:
        if self._show_banner:
            _print_banner(self._version)

        while True:
            try:
                raw_line = input(self._prompt())
            except EOFError:
                print()
                return 0
            except KeyboardInterrupt:
                print()
                continue

            should_exit, status = self.execute_line(raw_line)
            if should_exit:
                return status

    def execute_line(self, raw_line: str) -> tuple[bool, int]:
        stripped = raw_line.strip()

        if self._pending_declaration:
            return False, self._continue_declaration(raw_line)

        if not stripped:
            return False, 0

        if stripped.startswith(":"):
            return self._execute_command(stripped[1:].strip())

        if stripped.startswith("!"):
            return False, self._cmd_shell(stripped[1:].strip())

        if _looks_like_declaration_start(stripped):
            return False, self._begin_declaration(raw_line)

        return False, self._cmd_expr(stripped)

    def _prompt(self) -> str:
        if self._pending_declaration:
            return f"midori[{Path.cwd().name}]...> "
        return f"midori[{Path.cwd().name}]> "

    def _execute_command(self, payload: str) -> tuple[bool, int]:
        words = _parse_words(payload)
        if words is None:
            return False, 2
        if not words:
            return False, 0

        command = words[0].lower()
        args = words[1:]

        if command in {"quit", "q", "exit"}:
            return True, 0
        if command in {"help", "h", "?"}:
            self._print_help()
            return False, 0
        if command == "run":
            return False, self._cmd_run(args)
        if command == "check":
            return False, self._cmd_check(args)
        if command == "build":
            return False, self._cmd_build(args)
        if command == "fmt":
            return False, self._cmd_fmt(args)
        if command == "new":
            return False, self._cmd_new(args)
        if command == "test":
            return False, self._cmd_test(args)
        if command == "pwd":
            return False, self._cmd_pwd(args)
        if command == "cd":
            return False, self._cmd_cd(args)
        if command == "clear":
            return False, self._cmd_clear(args)
        if command == "reset":
            return False, self._cmd_reset(args)
        if command in {"cancel", "c"}:
            print("no active multiline declaration")
            return False, 0
        if command == "shell":
            shell_command = payload[len(words[0]) :].strip()
            return False, self._cmd_shell(shell_command)

        print(f"unknown command: :{command} (type :help)")
        return False, 2

    def _print_help(self) -> None:
        print("MIDORI terminal commands:")
        print("  :help                      Show this help")
        print("  :run <file.mdr>            Build and run a Midori file")
        print("  :check <file.mdr>          Run frontend checks")
        print("  :build <file.mdr> [opts]   Build executable")
        print("     options: -o <path> --emit-llvm --emit-asm")
        print("  :fmt <file.mdr>            Format a Midori source file")
        print("  :new <project_name>        Scaffold a new Midori project")
        print("  :test                      Run pytest test suite")
        print("  :pwd                       Print current directory")
        print("  :cd <path>                 Change current directory")
        print("  :clear                     Clear terminal screen")
        print("  :reset                     Clear session declarations")
        print("  :shell <command>           Run a shell command")
        print("  :cancel                    Cancel current multiline declaration")
        print("  !<command>                 Shortcut for :shell")
        print("  :quit                      Exit terminal")
        print("  error/fn/...               Top-level declarations support multiline input")
        print("  <expression>               Evaluate Midori expression")

    def _program_has_main(self, declarations: list[str]) -> bool:
        return any(_contains_main_fn(item) for item in declarations)

    def _build_program_source(self, declarations: list[str], *, with_stub_main: bool) -> str:
        parts = [item.rstrip() for item in declarations if item.strip()]
        if with_stub_main and not self._program_has_main(parts):
            parts.append("fn main() -> Int {\n  0\n}\n")
        return "\n\n".join(parts).rstrip() + "\n"

    def _check_source(self, source: str) -> int:
        with tempfile.TemporaryDirectory(prefix="midori-term-decl-check-") as tmp:
            src = Path(tmp) / "check.mdr"
            src.write_text(source, encoding="utf-8")
            try:
                check_file(src)
                return 0
            except MidoriError as exc:
                print(exc)
                return 1
            except Exception as exc:  # noqa: BLE001
                print(f"internal compiler error: {exc}")
                return 1

    def _run_source(self, source: str, *, prefix: str) -> int:
        with tempfile.TemporaryDirectory(prefix=prefix) as tmp:
            src = Path(tmp) / "program.mdr"
            exe = Path(tmp) / "program.exe"
            src.write_text(source, encoding="utf-8")
            try:
                compile_file(src, exe)
            except MidoriError as exc:
                print(exc)
                return 1
            except Exception as exc:  # noqa: BLE001
                print(f"internal compiler error: {exc}")
                return 1
            proc = subprocess.run([str(exe)], check=False)
            return proc.returncode

    def _begin_declaration(self, raw_line: str) -> int:
        self._pending_declaration = [raw_line.rstrip("\n")]
        self._pending_brace_depth = _brace_delta(raw_line)
        if self._pending_brace_depth <= 0:
            return self._finish_declaration()
        return 0

    def _continue_declaration(self, raw_line: str) -> int:
        stripped = raw_line.strip()
        if stripped in {":cancel", ":c"}:
            self._pending_declaration.clear()
            self._pending_brace_depth = 0
            print("multiline declaration canceled")
            return 0

        self._pending_declaration.append(raw_line.rstrip("\n"))
        self._pending_brace_depth += _brace_delta(raw_line)
        if self._pending_brace_depth > 0:
            return 0
        if self._pending_brace_depth < 0:
            self._pending_declaration.clear()
            self._pending_brace_depth = 0
            print("declaration parse error: unmatched closing brace")
            return 2
        return self._finish_declaration()

    def _finish_declaration(self) -> int:
        declaration = "\n".join(self._pending_declaration).strip()
        self._pending_declaration.clear()
        self._pending_brace_depth = 0
        if not declaration:
            return 0

        candidate = self._session_declarations + [declaration]
        source = self._build_program_source(candidate, with_stub_main=True)
        status = self._check_source(source)
        if status != 0:
            return status

        self._session_declarations = candidate
        if _contains_main_fn(declaration):
            print("running fn main() from session...")
            run_source = self._build_program_source(self._session_declarations, with_stub_main=False)
            return self._run_source(run_source, prefix="midori-term-session-main-")

        head = declaration.splitlines()[0].strip()
        print(f"added declaration: {head}")
        return 0

    def _validate_source_file(self, value: str) -> Path | None:
        source = Path(value)
        if not source.exists():
            print(f"source not found: {source}")
            return None
        if source.is_dir():
            print(f"expected source file, got directory: {source}")
            return None
        return source

    def _cmd_run(self, args: list[str]) -> int:
        if len(args) != 1:
            print("usage: :run <source.mdr>")
            return 2

        source = self._validate_source_file(args[0])
        if source is None:
            return 1

        with tempfile.TemporaryDirectory(prefix="midori-term-run-") as tmp:
            out = Path(tmp) / "program.exe"
            try:
                compile_file(source, out)
            except MidoriError as exc:
                print(exc)
                return 1
            except Exception as exc:  # noqa: BLE001
                print(f"internal compiler error: {exc}")
                return 1
            proc = subprocess.run([str(out)], check=False)
            return proc.returncode

    def _cmd_check(self, args: list[str]) -> int:
        if len(args) != 1:
            print("usage: :check <source.mdr>")
            return 2

        source = self._validate_source_file(args[0])
        if source is None:
            return 1

        try:
            check_file(source)
            print(f"checked {source}")
            return 0
        except MidoriError as exc:
            print(exc)
            return 1
        except Exception as exc:  # noqa: BLE001
            print(f"internal compiler error: {exc}")
            return 1

    def _cmd_build(self, args: list[str]) -> int:
        parsed = _parse_build_args(args)
        if parsed is None:
            return 2

        source, out, emit_llvm, emit_asm = parsed
        source_file = self._validate_source_file(str(source))
        if source_file is None:
            return 1

        try:
            compile_file(source_file, out, emit_llvm=emit_llvm, emit_asm=emit_asm)
            print(f"built {out}")
            return 0
        except MidoriError as exc:
            print(exc)
            return 1
        except Exception as exc:  # noqa: BLE001
            print(f"internal compiler error: {exc}")
            return 1

    def _cmd_fmt(self, args: list[str]) -> int:
        if len(args) != 1:
            print("usage: :fmt <source.mdr>")
            return 2

        target = Path(args[0])
        if not target.exists() or target.is_dir():
            print(f"target file not found: {target}")
            return 1

        try:
            original = target.read_text(encoding="utf-8")
            formatted = format_source(original)
            target.write_text(formatted, encoding="utf-8")
            print(f"formatted {target}")
            return 0
        except OSError as exc:
            print(f"file error: {exc}")
            return 1

    def _cmd_new(self, args: list[str]) -> int:
        if len(args) != 1:
            print("usage: :new <project_name>")
            return 2
        return _scaffold_project(Path(args[0]))

    def _cmd_test(self, args: list[str]) -> int:
        if args:
            print("usage: :test")
            return 2
        proc = subprocess.run([sys.executable, "-m", "pytest", "-q"], check=False)
        return proc.returncode

    def _cmd_pwd(self, args: list[str]) -> int:
        if args:
            print("usage: :pwd")
            return 2
        print(Path.cwd())
        return 0

    def _cmd_cd(self, args: list[str]) -> int:
        if len(args) != 1:
            print("usage: :cd <path>")
            return 2

        target = Path(args[0]).expanduser()
        if not target.exists() or not target.is_dir():
            print(f"directory not found: {target}")
            return 1

        os.chdir(target)
        print(Path.cwd())
        return 0

    def _cmd_clear(self, args: list[str]) -> int:
        if args:
            print("usage: :clear")
            return 2
        os.system("cls" if os.name == "nt" else "clear")
        return 0

    def _cmd_reset(self, args: list[str]) -> int:
        if args:
            print("usage: :reset")
            return 2
        self._session_declarations.clear()
        self._pending_declaration.clear()
        self._pending_brace_depth = 0
        print("session cleared")
        return 0

    def _cmd_shell(self, command: str) -> int:
        if not command:
            print("usage: :shell <command>")
            return 2
        proc = subprocess.run(command, shell=True, check=False)
        return proc.returncode

    def _cmd_expr(self, expr: str) -> int:
        if self._program_has_main(self._session_declarations):
            print("session already defines fn main(). use :reset before evaluating expressions.")
            return 2

        declarations = list(self._session_declarations)
        declarations.append(f"fn main() -> Int {{\n  print({expr})\n  0\n}}")
        source = self._build_program_source(declarations, with_stub_main=False)
        return self._run_source(source, prefix="midori-term-expr-")


def main() -> None:
    parser = argparse.ArgumentParser(prog="midori-terminal")
    parser.add_argument(
        "--version", action="version", version=f"midori-terminal {_resolve_version()}"
    )
    parser.add_argument("--no-banner", action="store_true", help="disable startup banner")
    parser.add_argument(
        "-c",
        "--command",
        default=None,
        help="execute a single command/expression and exit",
    )
    args = parser.parse_args()

    terminal = MidoriTerminal(show_banner=not args.no_banner)
    if args.command is not None:
        _should_exit, status = terminal.execute_line(args.command)
        raise SystemExit(status)

    raise SystemExit(terminal.run())


if __name__ == "__main__":
    main()
