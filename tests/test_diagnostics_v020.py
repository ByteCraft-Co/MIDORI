from __future__ import annotations

import pytest

from midori_cli.pipeline import compile_file
from midori_compiler.parser import Parser
from midori_ir.borrow import run_borrow_check
from midori_typecheck.checker import check_program
from midori_typecheck.resolver import resolve_names


def _check(source: str):
    program = Parser.from_source(source, "diag.mdr").parse()
    return check_program(program, resolve_names(program))


def _borrow(source: str) -> None:
    typed = _check(source)
    run_borrow_check(typed)


def test_diag_unknown_name() -> None:
    with pytest.raises(Exception) as exc:
        _check("fn main() -> Int { x }")
    msg = str(exc.value)
    assert "diag.mdr:1" in msg
    assert "unknown name" in msg


def test_diag_immutable_assignment() -> None:
    with pytest.raises(Exception) as exc:
        _check("fn main() -> Int { let x := 1; x = 2; x }")
    assert "cannot assign to immutable variable" in str(exc.value)


def test_diag_wrong_argument_count() -> None:
    with pytest.raises(Exception) as exc:
        _check("fn f(x: Int) -> Int { x } fn main() -> Int { f() }")
    assert "wrong number of arguments" in str(exc.value)


def test_diag_try_on_non_result() -> None:
    with pytest.raises(Exception) as exc:
        _check("fn main() -> Int { let x := 1? x }")
    assert "expects Result" in str(exc.value)


def test_diag_try_outside_result_function() -> None:
    with pytest.raises(Exception) as exc:
        _check("fn f() -> Result[Int, String] { Ok(1) } fn main() -> Int { let v := f()? v }")
    assert "functions returning Result" in str(exc.value)


def test_diag_variant_pattern_on_non_enum() -> None:
    with pytest.raises(Exception) as exc:
        _check("fn main() -> Int { match 1 { Ok(v) => v } }")
    assert "requires enum target" in str(exc.value)


def test_diag_unknown_variant_for_enum() -> None:
    with pytest.raises(Exception) as exc:
        _check("enum T { A } fn main() -> Int { let t := A(); match t { B(v) => 0 } }")
    assert "unknown variant" in str(exc.value)


def test_diag_ambiguous_variant_constructor() -> None:
    with pytest.raises(Exception) as exc:
        _check("enum A { V } enum B { V } fn main() -> Int { let x := V() 0 }")
    assert "ambiguous variant constructor" in str(exc.value)


def test_diag_use_after_move_nested_scope() -> None:
    with pytest.raises(Exception) as exc:
        _borrow(
            """
fn main() -> Int {
  let s: String = \"x\"
  if true {
    let t := s
    print(t)
    0
  } else {
    0
  }
  print(s)
  0
}
"""
        )
    assert "use after move" in str(exc.value)


def test_diag_borrow_after_branch_move() -> None:
    with pytest.raises(Exception) as exc:
        _borrow(
            """
fn main() -> Int {
  let s: String = \"x\"
  if true {
    let a := s
    0
  } else {
    0
  }
  let b := &mut s
  0
}
"""
        )
    assert "moved value" in str(exc.value)


def test_cli_compile_error_contains_location(tmp_path):
    src = tmp_path / "bad.mdr"
    src.write_text("fn main() -> Int { let x := 1? x }", encoding="utf-8")
    with pytest.raises(Exception) as exc:
        compile_file(src, tmp_path / "bad.exe")
    assert "bad.mdr:1" in str(exc.value)
