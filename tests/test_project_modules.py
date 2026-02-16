from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from midori_cli.pipeline import compile_file, write_lockfile


def test_imports_across_files_compile_and_run(tmp_path: Path) -> None:
    entry = tmp_path / "main.mdr"
    util = tmp_path / "math.mdr"
    util.write_text(
        """
fn inc(v: Int) -> Int {
  v + 1
}
""",
        encoding="utf-8",
    )
    entry.write_text(
        """
import "./math.mdr"

fn main() -> Int {
  print(inc(41))
  0
}
""",
        encoding="utf-8",
    )

    exe = tmp_path / "program.exe"
    compile_file(entry, exe)
    proc = subprocess.run([str(exe)], capture_output=True, text=True, check=False)
    assert proc.returncode == 0
    assert proc.stdout.strip() == "42"


def test_import_cycle_reports_error(tmp_path: Path) -> None:
    a = tmp_path / "a.mdr"
    b = tmp_path / "b.mdr"

    a.write_text('import "./b.mdr"\nfn main() -> Int { from_b() }\n', encoding="utf-8")
    b.write_text('import "./a.mdr"\nfn from_b() -> Int { 0 }\n', encoding="utf-8")

    with pytest.raises(Exception) as exc:
        compile_file(a, tmp_path / "cycle.exe")
    assert "import cycle detected" in str(exc.value)


def test_lockfile_is_deterministic(tmp_path: Path) -> None:
    (tmp_path / "midori.toml").write_text(
        """
[package]
name = "demo"
version = "0.3.0"

[build]
entry = "main.mdr"
""",
        encoding="utf-8",
    )
    (tmp_path / "util.mdr").write_text("fn value() -> Int { 7 }\n", encoding="utf-8")
    entry = tmp_path / "main.mdr"
    entry.write_text(
        """
import "./util.mdr"
fn main() -> Int {
  value()
}
""",
        encoding="utf-8",
    )

    first = write_lockfile(entry).read_text(encoding="utf-8")
    second = write_lockfile(entry).read_text(encoding="utf-8")

    assert first == second
    assert 'entry = "main.mdr"' in first
    assert 'name = "demo"' in first
    assert "[[sources]]" in first
