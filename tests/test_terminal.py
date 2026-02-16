from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from midori_cli import terminal


def test_terminal_version_flag(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("sys.argv", ["midori-terminal", "--version"])
    with pytest.raises(SystemExit) as exc:
        terminal.main()
    assert exc.value.code == 0
    out = capsys.readouterr().out.strip()
    assert out.startswith("midori-terminal ")


def test_parse_build_args_defaults() -> None:
    parsed = terminal._parse_build_args(["examples/hello.mdr"])  # noqa: SLF001
    assert parsed is not None
    source, out, emit_llvm, emit_asm = parsed
    assert source == Path("examples/hello.mdr")
    assert out == Path("examples/hello.exe")
    assert not emit_llvm
    assert not emit_asm


def test_terminal_execute_quit() -> None:
    app = terminal.MidoriTerminal(show_banner=False)
    should_exit, status = app.execute_line(":quit")
    assert should_exit
    assert status == 0


def test_terminal_executes_single_command_and_exits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, str] = {}

    class FakeTerminal:
        def __init__(self, *, show_banner: bool = True) -> None:
            assert show_banner is False

        def execute_line(self, line: str) -> tuple[bool, int]:
            captured["line"] = line
            return False, 7

        def run(self) -> int:
            raise AssertionError("run() should not be used when --command is set")

    monkeypatch.setattr("midori_cli.terminal.MidoriTerminal", FakeTerminal)
    monkeypatch.setattr(
        "sys.argv",
        ["midori-terminal", "--no-banner", "--command", ":help"],
    )
    with pytest.raises(SystemExit) as exc:
        terminal.main()

    assert exc.value.code == 7
    assert captured["line"] == ":help"


def test_terminal_multiline_declaration_is_buffered_and_reused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    checked_sources: list[str] = []
    compiled_sources: list[str] = []

    def fake_check_file(path: Path) -> None:
        checked_sources.append(path.read_text(encoding="utf-8"))

    def fake_compile_file(path: Path, _out: Path, **_kwargs):
        compiled_sources.append(path.read_text(encoding="utf-8"))
        return SimpleNamespace()

    def fake_run(*_args, **_kwargs):
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr("midori_cli.terminal.check_file", fake_check_file)
    monkeypatch.setattr("midori_cli.terminal.compile_file", fake_compile_file)
    monkeypatch.setattr("midori_cli.terminal.subprocess.run", fake_run)

    app = terminal.MidoriTerminal(show_banner=False)
    should_exit, status = app.execute_line("error TooBig")
    assert not should_exit
    assert status == 0

    should_exit, status = app.execute_line("fn validate(n: Int) -> Result[Int, String] {")
    assert not should_exit
    assert status == 0
    should_exit, status = app.execute_line('  raise TooBig("nope")')
    assert not should_exit
    assert status == 0
    should_exit, status = app.execute_line("}")
    assert not should_exit
    assert status == 0

    should_exit, status = app.execute_line("validate(10)")
    assert not should_exit
    assert status == 0

    assert checked_sources
    assert "error TooBig" in checked_sources[-1]
    assert "fn validate" in checked_sources[-1]
    assert compiled_sources
    assert "print(validate(10))" in compiled_sources[-1]
    assert "error TooBig" in compiled_sources[-1]
    assert "fn validate" in compiled_sources[-1]


def test_terminal_declaring_main_runs_session_program(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    compiled_sources: list[str] = []

    def fake_check_file(_path: Path) -> None:
        return None

    def fake_compile_file(path: Path, _out: Path, **_kwargs):
        compiled_sources.append(path.read_text(encoding="utf-8"))
        return SimpleNamespace()

    def fake_run(*_args, **_kwargs):
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr("midori_cli.terminal.check_file", fake_check_file)
    monkeypatch.setattr("midori_cli.terminal.compile_file", fake_compile_file)
    monkeypatch.setattr("midori_cli.terminal.subprocess.run", fake_run)

    app = terminal.MidoriTerminal(show_banner=False)
    app.execute_line("fn main() -> Int {")
    app.execute_line("  print(1)")
    should_exit, status = app.execute_line("}")
    assert not should_exit
    assert status == 0
    assert compiled_sources
    assert "fn main() -> Int {" in compiled_sources[-1]
    assert "print(1)" in compiled_sources[-1]
