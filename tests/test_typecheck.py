from __future__ import annotations

import pytest

from midori_compiler.parser import Parser
from midori_typecheck.checker import check_program
from midori_typecheck.resolver import resolve_names


def _check(source: str):
    program = Parser.from_source(source, "test.mdr").parse()
    return check_program(program, resolve_names(program))


def test_type_inference_for_coloneq() -> None:
    typed = _check(
        """
fn main() -> Int {
  let x := 3
  x
}
"""
    )
    assert typed.functions["main"].local_types["x"].name == "Int"


def test_type_mismatch_reports_error() -> None:
    with pytest.raises(Exception) as exc:
        _check(
            """
fn main() -> Int {
  let x: Int = \"hi\"
  x
}
"""
        )
    assert "type mismatch" in str(exc.value)


def test_result_try_requires_result_type() -> None:
    with pytest.raises(Exception) as exc:
        _check(
            """
fn main() -> Int {
  let x := 1?
  x
}
"""
        )
    assert "expects Result" in str(exc.value)
