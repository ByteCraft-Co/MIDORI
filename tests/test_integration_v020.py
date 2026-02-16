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


def test_match_enum_multi_payload_compile_run(tmp_path: Path) -> None:
    proc = _run_program(
        """
enum Shape {
  Circle(radius: Int)
  Rect(width: Int, height: Int)
  Unit
}

fn area(s: Shape) -> Int {
  match s {
    Circle(r) => r * r,
    Rect(w, h) => w * h,
    Unit => 0,
  }
}

fn main() -> Int {
  print(area(Circle(3)))
  print(area(Rect(2, 5)))
  print(area(Unit()))
  0
}
""",
        tmp_path,
    )
    assert proc.returncode == 0
    assert proc.stdout.splitlines() == ["9", "10", "0"]


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


def test_result_try_early_return_skips_following_work(tmp_path: Path) -> None:
    proc = _run_program(
        """
fn fail() -> Result[Int, String] {
  Err("boom")
}

fn side_effect() -> Int {
  print("SHOULD_NOT_PRINT")
  99
}

fn compute() -> Result[Int, String] {
  let x := fail()?
  let y := side_effect()
  Ok(x + y)
}

fn main() -> Int {
  let r := compute()
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
    assert proc.stdout.splitlines() == ["boom"]


def test_result_try_nested_propagation_compile_run(tmp_path: Path) -> None:
    proc = _run_program(
        """
fn parse(flag: Bool) -> Result[Int, String] {
  if flag { Ok(5) } else { Err("nope") }
}

fn level2(flag: Bool) -> Result[Int, String] {
  let x := parse(flag)?
  Ok(x + 1)
}

fn level3(flag: Bool) -> Result[Int, String] {
  let y := level2(flag)?
  Ok(y + 1)
}

fn main() -> Int {
  let a := level3(true)
  let b := level3(false)
  match a {
    Ok(v) => print(v),
    Err(e) => print(e),
  }
  match b {
    Ok(v) => print(v),
    Err(e) => print(e),
  }
  0
}
""",
        tmp_path,
    )
    assert proc.returncode == 0
    assert proc.stdout.splitlines() == ["7", "nope"]


def test_read_file_runtime_success(tmp_path: Path) -> None:
    input_file = tmp_path / "input.txt"
    input_file.write_text("hello-from-disk", encoding="utf-8")
    input_path = input_file.as_posix()

    source = """
fn main() -> Int {
  let r := read_file("__PATH__")
  match r {
    Ok(v) => print(v),
    Err(e) => print(e),
  }
  0
}
""".replace("__PATH__", input_path)

    proc = _run_program(
        source,
        tmp_path,
    )
    assert proc.returncode == 0
    assert proc.stdout.strip() == "hello-from-disk"


def test_read_file_runtime_missing_file_error(tmp_path: Path) -> None:
    proc = _run_program(
        """
fn main() -> Int {
  let r := read_file("missing.txt")
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
    assert "read_file open failed" in proc.stdout


def test_if_expr_with_return_branch_compiles_and_runs(tmp_path: Path) -> None:
    proc = _run_program(
        """
fn pick(flag: Bool) -> Int {
  if flag {
    return 1
  } else {
    2
  }
}

fn main() -> Int {
  print(pick(true))
  print(pick(false))
  0
}
""",
        tmp_path,
    )
    assert proc.returncode == 0
    assert proc.stdout.splitlines() == ["1", "2"]


def test_custom_error_raise_and_formatting(tmp_path: Path) -> None:
    proc = _run_program(
        """
error ValidationError
error ZeroDivisionError

fn guarded_div(a: Int, b: Int) -> Result[Int, String] {
  if a < 0 {
    raise ValidationError("a must be non-negative")
  }
  if b == 0 {
    raise ZeroDivisionError("b cannot be zero")
  }
  Ok(a / b)
}

fn main() -> Int {
  let ok := guarded_div(12, 3)
  let bad_a := guarded_div(-1, 3)
  let bad_b := guarded_div(7, 0)

  match ok {
    Ok(v) => print(v),
    Err(e) => print(e),
  }
  match bad_a {
    Ok(v) => print(v),
    Err(e) => print(e),
  }
  match bad_b {
    Ok(v) => print(v),
    Err(e) => print(e),
  }
  0
}
""",
        tmp_path,
    )
    assert proc.returncode == 0
    out = proc.stdout
    assert out.splitlines()[0] == "4"
    assert out.count("[MIDORI RAISE]") == 2
    assert "kind   : ValidationError" in out
    assert "kind   : ZeroDivisionError" in out
    assert "in     : guarded_div" in out
    assert "source :" in out
    assert 'raise ValidationError("a must be non-negative")' in out
    assert 'raise ZeroDivisionError("b cannot be zero")' in out
    assert "raised here" in out
    assert "detail : a must be non-negative" in out
    assert "detail : b cannot be zero" in out


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
