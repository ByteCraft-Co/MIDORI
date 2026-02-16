from __future__ import annotations

import pytest

from midori_cli.main import main


def test_cli_version_flag(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("sys.argv", ["midori", "--version"])
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 0
    out = capsys.readouterr().out.strip()
    assert out.startswith("midori ")
    assert len(out.split(maxsplit=1)) == 2


def test_cli_check_command(
    tmp_path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    src = tmp_path / "ok.mdr"
    src.write_text(
        "fn main() -> Int {\n  let x := 1\n  x\n}\n",
        encoding="utf-8",
    )
    monkeypatch.setattr("sys.argv", ["midori", "check", str(src)])
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 0
    assert f"checked {src}" in capsys.readouterr().out


def test_cli_new_scaffolds_project(
    tmp_path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("sys.argv", ["midori", "new", "demo"])
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 0

    project = tmp_path / "demo"
    assert (project / "main.mdr").exists()
    assert (project / "tests" / "smoke_test.mdr").exists()
    main_text = (project / "main.mdr").read_text(encoding="utf-8")
    assert "hello from demo" in main_text
    assert "created project demo" in capsys.readouterr().out


def test_cli_new_rejects_nonempty_directory(
    tmp_path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    project = tmp_path / "demo"
    project.mkdir()
    (project / "existing.txt").write_text("x", encoding="utf-8")

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("sys.argv", ["midori", "new", "demo"])
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 1
    assert "project directory is not empty" in capsys.readouterr().out


def test_cli_new_rejects_existing_file(
    tmp_path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "demo"
    target.write_text("x", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("sys.argv", ["midori", "new", "demo"])
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 1
    assert "is not a directory" in capsys.readouterr().out


def test_cli_internal_error_boundary(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    def _boom(*_args, **_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr("midori_cli.main.compile_file", _boom)
    monkeypatch.setattr("sys.argv", ["midori", "build", "x.mdr", "-o", "x.exe"])
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 1
    assert "internal compiler error: boom" in capsys.readouterr().out
