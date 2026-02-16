from __future__ import annotations

from midori_cli.formatter import format_source


def test_formatter_idempotent_on_mixed_input() -> None:
    source = """
fn main() -> Int {
let x := 1;
let y := 2
if x < y {
print(x);
} else {
print(y)
}
x + y
}
""".lstrip("\n")
    once = format_source(source)
    twice = format_source(once)
    assert once == twice


def test_formatter_semicolon_and_newline_stability() -> None:
    source = """
fn calc() -> Int {
let a := 1;
let b := 2
let c := a + b;
c
}
""".lstrip("\n")
    formatted = format_source(source)
    assert formatted == (
        "fn calc() -> Int {\n  let a := 1;\n  let b := 2\n  let c := a + b;\n  c\n}\n"
    )
    assert formatted.count(";") == source.count(";")
    assert format_source(formatted) == formatted


def test_formatter_preserves_trailing_newline_contract() -> None:
    src_no_newline = "fn main() -> Int {\nlet x := 1\nx\n}"
    out = format_source(src_no_newline)
    assert not out.endswith("\n")
    assert format_source(out) == out
