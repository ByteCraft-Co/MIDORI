from __future__ import annotations

from midori_compiler.lexer import Lexer
from midori_compiler.token import TokenKind


def kinds(source: str) -> list[TokenKind]:
    return [t.kind for t in Lexer(source, "test.mdr").tokenize()]


def test_lex_tokens_and_keywords() -> None:
    src = "error Fail fn main() -> Int { let x := 1 + 2; raise Fail(\"boom\"); return x }"
    got = kinds(src)
    assert TokenKind.ERROR in got
    assert TokenKind.FN in got
    assert TokenKind.LET in got
    assert TokenKind.RAISE in got
    assert TokenKind.COLONEQ in got
    assert TokenKind.PLUS in got
    assert got[-1] is TokenKind.EOF


def test_lex_comments_and_newlines() -> None:
    src = "let x := 1 // c\n/* block */\nlet y := 2"
    got = kinds(src)
    assert got.count(TokenKind.LET) == 2
    assert got.count(TokenKind.NEWLINE) >= 2


def test_lex_span_location() -> None:
    tok = Lexer("\nlet name := 3", "sample.mdr").tokenize()[1]
    assert tok.lexeme == "let"
    assert tok.span.line == 2
    assert tok.span.col == 1


def test_lex_unterminated_string() -> None:
    try:
        Lexer('"oops', "bad.mdr").tokenize()
    except Exception as exc:  # noqa: BLE001
        msg = str(exc)
        assert "bad.mdr:1:1" in msg
        assert "unterminated string literal" in msg
    else:
        raise AssertionError("expected lexer error")
