from __future__ import annotations

import subprocess
from pathlib import Path

from midori_cli.pipeline import compile_file


def test_compile_and_run_hello(tmp_path: Path) -> None:
    src = tmp_path / "hello.mdr"
    src.write_text(
        """
fn main() -> Int {
  print(\"hello\")
  0
}
""",
        encoding="utf-8",
    )
    exe = tmp_path / "hello.exe"
    result = compile_file(src, exe)
    assert 'define i32 @"main"' in result.llvm_ir
    proc = subprocess.run([str(exe)], capture_output=True, text=True, check=False)
    assert proc.returncode == 0
    assert "hello" in proc.stdout
