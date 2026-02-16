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
    assert "error[MD3101]" in msg
    assert "unknown name" in msg


def test_diag_duplicate_custom_error_decl() -> None:
    with pytest.raises(Exception) as exc:
        _check("error Boom error Boom fn main() -> Int { 0 }")
    msg = str(exc.value)
    assert "error[MD3005]" in msg
    assert "duplicate custom error" in msg


def test_diag_immutable_assignment() -> None:
    with pytest.raises(Exception) as exc:
        _check("fn main() -> Int { let x := 1; x = 2; x }")
    msg = str(exc.value)
    assert "error[MD3103]" in msg
    assert "cannot assign to immutable variable" in msg


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


def test_diag_unary_not_requires_bool() -> None:
    with pytest.raises(Exception) as exc:
        _check("fn main() -> Int { let x := !1 x }")
    msg = str(exc.value)
    assert "error[MD3102]" in msg
    assert "expected Bool" in msg


def test_diag_print_rejects_enum_values() -> None:
    with pytest.raises(Exception) as exc:
        _check("enum E { A } fn main() -> Int { print(A()); 0 }")
    msg = str(exc.value)
    assert "error[MD3110]" in msg
    assert "unsupported print argument type" in msg


def test_diag_non_exhaustive_match_is_error() -> None:
    with pytest.raises(Exception) as exc:
        _check("fn main() -> Int { let b := true; match b { true => 1 } }")
    msg = str(exc.value)
    assert "non-exhaustive match" in msg
    assert "error[MD3100]" in msg


def test_diag_nested_enum_payload_is_rejected(tmp_path) -> None:
    src = tmp_path / "nested.mdr"
    src.write_text(
        """
fn wrap(v: Int) -> Option[Option[Int]] {
  Some(Some(v))
}

fn main() -> Int {
  let x := wrap(1)
  match x {
    Some(y) => 0,
    None => 0,
  }
}
""",
        encoding="utf-8",
    )
    with pytest.raises(Exception) as exc:
        compile_file(src, tmp_path / "nested.exe")
    msg = str(exc.value)
    assert "unsupported enum payload type Option[Int]" in msg


def test_diag_raise_unknown_custom_error() -> None:
    with pytest.raises(Exception) as exc:
        _check(
            """
fn main() -> Result[Int, String] {
  raise MissingKind("boom")
}
"""
        )
    msg = str(exc.value)
    assert "error[MD3111]" in msg
    assert "unknown custom error kind" in msg


def test_diag_raise_requires_result_string_return() -> None:
    with pytest.raises(Exception) as exc:
        _check(
            """
error Oops
fn main() -> Int {
  raise Oops("boom")
}
"""
        )
    msg = str(exc.value)
    assert "error[MD3112]" in msg
    assert "functions returning Result" in msg or "`raise` can only be used" in msg


def test_diag_raise_requires_string_literal_message() -> None:
    with pytest.raises(Exception) as exc:
        _check(
            """
error Oops
fn main() -> Result[Int, String] {
  let msg := "boom"
  raise Oops(msg)
}
"""
        )
    msg = str(exc.value)
    assert "error[MD3112]" in msg
    assert "string literal" in msg


def test_diag_raise_requires_result_error_type_string() -> None:
    with pytest.raises(Exception) as exc:
        _check(
            """
error Oops
fn main() -> Result[Int, Int] {
  raise Oops("boom")
}
"""
        )
    msg = str(exc.value)
    assert "error[MD3102]" in msg or "error[MD3112]" in msg
    assert "expected String" in msg or "Result[T, String]" in msg


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
    msg = str(exc.value)
    assert "error[MD4001]" in msg
    assert "use after move" in msg


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
