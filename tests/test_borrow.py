from __future__ import annotations

import pytest

from midori_compiler.parser import Parser
from midori_ir.borrow import run_borrow_check
from midori_typecheck.checker import check_program
from midori_typecheck.resolver import resolve_names


def _borrow_check(source: str) -> None:
    program = Parser.from_source(source, "borrow.mdr").parse()
    typed = check_program(program, resolve_names(program))
    run_borrow_check(typed)


def test_use_after_move_error() -> None:
    src = """
fn main() -> Int {
  let s: String = \"x\"
  let t := s
  print(s)
  0
}
"""
    with pytest.raises(Exception) as exc:
        _borrow_check(src)
    assert "use after move" in str(exc.value)


def test_aliasing_mut_and_immut_borrow_error() -> None:
    src = """
fn main() -> Int {
  let s: String = \"x\"
  let a := &s
  let b := &mut s
  0
}
"""
    with pytest.raises(Exception) as exc:
        _borrow_check(src)
    assert "cannot mutably borrow" in str(exc.value)
