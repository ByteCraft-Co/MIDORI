from __future__ import annotations

from pathlib import Path

from midori_compiler.parser import Parser

from .ast_dump import dump_node


def test_parser_function_and_if_expression_golden() -> None:
    src = """
fn score_label(score: Int) -> String {
  if score > 90 { \"A\" } else { \"B\" }
}
"""
    program = Parser.from_source(src, "golden.mdr").parse()
    dump = dump_node(program)
    golden = Path("tests/golden/parser_score_label.txt")
    if not golden.exists():
        golden.parent.mkdir(parents=True, exist_ok=True)
        golden.write_text(dump, encoding="utf-8")
    assert dump == golden.read_text(encoding="utf-8")


def test_parser_enum_and_match() -> None:
    src = """
enum Token { Int(value: Int), Plus }
fn main() -> Int {
  let x := 1
  match x { 1 => 10, _ => 0 }
}
"""
    program = Parser.from_source(src, "enum.mdr").parse()
    assert len(program.items) == 2


def test_parser_reports_error_with_span() -> None:
    src = "fn main( { 0 }"
    try:
        Parser.from_source(src, "bad_parse.mdr").parse()
    except Exception as exc:  # noqa: BLE001
        msg = str(exc)
        assert "bad_parse.mdr:1" in msg
        assert "expected parameter name" in msg or "expected ')'" in msg
    else:
        raise AssertionError("expected parser error")
