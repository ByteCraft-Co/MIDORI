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
