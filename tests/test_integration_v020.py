from __future__ import annotations

import subprocess
from pathlib import Path

from midori_cli.pipeline import compile_file


def _run_program(src_text: str, tmp_path: Path) -> subprocess.CompletedProcess[str]:
    src = tmp_path / "prog.mdr"
    src.write_text(src_text, encoding="utf-8")
    exe = tmp_path / "prog.exe"
    compile_file(src, exe)
    return subprocess.run([str(exe)], capture_output=True, text=True, check=False)


def test_match_enum_variant_payload_compile_run(tmp_path: Path) -> None:
    proc = _run_program(
        """
enum Token {
  Int(value: Int)
  Plus
}

fn value(t: Token) -> Int {
  match t {
    Int(v) => v,
    Plus => 0,
  }
}

fn main() -> Int {
  let t := Int(7)
  print(value(t))
  0
}
""",
        tmp_path,
    )
    assert proc.returncode == 0
    assert proc.stdout.strip() == "7"


def test_match_bool_literal_compile_run(tmp_path: Path) -> None:
    proc = _run_program(
        """
fn classify(v: Bool) -> Int {
  match v {
    true => 1,
    false => 0,
  }
}

fn main() -> Int {
  print(classify(true))
  print(classify(false))
  0
}
""",
        tmp_path,
    )
    assert proc.returncode == 0
    assert proc.stdout.splitlines() == ["1", "0"]


def test_result_try_success_and_error_paths(tmp_path: Path) -> None:
    proc = _run_program(
        """
fn may_fail(flag: Bool) -> Result[Int, String] {
  if flag { Ok(41) } else { Err(\"boom\") }
}

fn compute(flag: Bool) -> Result[Int, String] {
  let v := may_fail(flag)?
  Ok(v + 1)
}

fn main() -> Int {
  let good := compute(true)
  let bad := compute(false)
  match good {
    Ok(v) => print(v),
    Err(e) => print(e),
  }
  match bad {
    Ok(v) => print(v),
    Err(e) => print(e),
  }
  0
}
""",
        tmp_path,
    )
    assert proc.returncode == 0
    assert proc.stdout.splitlines() == ["42", "boom"]


def test_read_file_result_stub_runtime(tmp_path: Path) -> None:
    proc = _run_program(
        """
fn main() -> Int {
  let r := read_file(\"missing.txt\")
  match r {
    Ok(v) => print(v),
    Err(e) => print(e),
  }
  0
}
""",
        tmp_path,
    )
    assert proc.returncode == 0
    assert "read_file not implemented" in proc.stdout


def test_emit_outputs_deterministic(tmp_path: Path) -> None:
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

    out_a = tmp_path / "a.exe"
    out_b = tmp_path / "b.exe"

    compile_file(src, out_a, emit_llvm=True, emit_asm=True)
    compile_file(src, out_b, emit_llvm=True, emit_asm=True)

    ll_a = out_a.with_suffix(".ll").read_text(encoding="utf-8")
    ll_b = out_b.with_suffix(".ll").read_text(encoding="utf-8")
    asm_a = out_a.with_suffix(".s").read_text(encoding="utf-8")
    asm_b = out_b.with_suffix(".s").read_text(encoding="utf-8")

    assert ll_a == ll_b
    assert asm_a == asm_b
