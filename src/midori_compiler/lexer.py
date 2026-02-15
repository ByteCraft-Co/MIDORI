from __future__ import annotations

from midori_compiler.errors import MidoriError
from midori_compiler.span import Span
from midori_compiler.token import KEYWORDS, Token, TokenKind


class Lexer:
    def __init__(self, source: str, file: str = "<input>") -> None:
        self.source = source
        self.file = file
        self.pos = 0
        self.line = 1
        self.col = 1

    def tokenize(self) -> list[Token]:
        out: list[Token] = []
        while not self._at_end():
            c = self._peek()
            if c in " \t\r":
                self._advance()
                continue
            if c == "\n":
                out.append(
                    self._token(
                        TokenKind.NEWLINE, "\n", self.pos, self.pos + 1, self.line, self.col
                    )
                )
                self._advance()
                continue
            if c == "/":
                if self._peek_next() == "/":
                    self._skip_line_comment()
                    continue
                if self._peek_next() == "*":
                    self._skip_block_comment()
                    continue
            if c.isalpha() or c == "_":
                out.append(self._identifier())
                continue
            if c.isdigit():
                out.append(self._number())
                continue
            if c == '"':
                out.append(self._string())
                continue
            if c == "'":
                out.append(self._char())
                continue
            out.append(self._symbol())

        out.append(self._token(TokenKind.EOF, "", self.pos, self.pos, self.line, self.col))
        return out

    def _symbol(self) -> Token:
        two = self.source[self.pos : self.pos + 2]
        three = self.source[self.pos : self.pos + 3]
        start = self.pos
        line = self.line
        col = self.col

        if three == "..=":
            self._advance_n(3)
            return self._token(TokenKind.DOTDOTEQ, three, start, self.pos, line, col)

        table2 = {
            "==": TokenKind.EQEQ,
            "!=": TokenKind.NE,
            "<=": TokenKind.LE,
            ">=": TokenKind.GE,
            "&&": TokenKind.ANDAND,
            "||": TokenKind.OROR,
            "+=": TokenKind.PLUSEQ,
            "-=": TokenKind.MINUSEQ,
            "*=": TokenKind.STAREQ,
            "/=": TokenKind.SLASHEQ,
            "%=": TokenKind.PERCENTEQ,
            ":=": TokenKind.COLONEQ,
            "..": TokenKind.DOTDOT,
            "->": TokenKind.ARROW,
            "=>": TokenKind.FATARROW,
        }
        if two in table2:
            self._advance_n(2)
            return self._token(table2[two], two, start, self.pos, line, col)

        one = self._advance()
        table1 = {
            "+": TokenKind.PLUS,
            "-": TokenKind.MINUS,
            "*": TokenKind.STAR,
            "/": TokenKind.SLASH,
            "%": TokenKind.PERCENT,
            "=": TokenKind.EQ,
            "<": TokenKind.LT,
            ">": TokenKind.GT,
            "!": TokenKind.BANG,
            "{": TokenKind.LBRACE,
            "}": TokenKind.RBRACE,
            "(": TokenKind.LPAREN,
            ")": TokenKind.RPAREN,
            "[": TokenKind.LBRACKET,
            "]": TokenKind.RBRACKET,
            ",": TokenKind.COMMA,
            ":": TokenKind.COLON,
            ";": TokenKind.SEMI,
            ".": TokenKind.DOT,
            "?": TokenKind.QUESTION,
            "&": TokenKind.AMP,
        }
        kind = table1.get(one)
        if not kind:
            raise MidoriError(
                span=Span(self.file, start, self.pos, line, col),
                message=f"invalid character {one!r}",
                hint="remove or escape the character",
            )
        return self._token(kind, one, start, self.pos, line, col)

    def _identifier(self) -> Token:
        start = self.pos
        line = self.line
        col = self.col
        while not self._at_end() and (self._peek().isalnum() or self._peek() == "_"):
            self._advance()
        text = self.source[start : self.pos]
        kind = KEYWORDS.get(text, TokenKind.IDENT)
        return self._token(kind, text, start, self.pos, line, col)

    def _number(self) -> Token:
        start = self.pos
        line = self.line
        col = self.col
        while not self._at_end() and self._peek().isdigit():
            self._advance()
        kind = TokenKind.INT
        if not self._at_end() and self._peek() == "." and self._peek_next().isdigit():
            kind = TokenKind.FLOAT
            self._advance()
            while not self._at_end() and self._peek().isdigit():
                self._advance()
        text = self.source[start : self.pos]
        return self._token(kind, text, start, self.pos, line, col)

    def _string(self) -> Token:
        start = self.pos
        line = self.line
        col = self.col
        self._advance()
        escaped = False
        while not self._at_end():
            ch = self._advance()
            if escaped:
                escaped = False
                continue
            if ch == "\\":
                escaped = True
                continue
            if ch == '"':
                lexeme = self.source[start : self.pos]
                return self._token(TokenKind.STRING, lexeme, start, self.pos, line, col)
        raise MidoriError(
            span=Span(self.file, start, self.pos, line, col),
            message="unterminated string literal",
            hint="add a closing quote",
        )

    def _char(self) -> Token:
        start = self.pos
        line = self.line
        col = self.col
        self._advance()
        if self._at_end() or self._peek() == "\n":
            raise MidoriError(
                span=Span(self.file, start, self.pos, line, col),
                message="unterminated char literal",
                hint="char literals must end with a single quote",
            )
        if self._peek() == "\\":
            self._advance_n(2)
        else:
            self._advance()
        if self._at_end() or self._peek() != "'":
            raise MidoriError(
                span=Span(self.file, start, self.pos, line, col),
                message="invalid char literal",
                hint="char literal must contain exactly one character",
            )
        self._advance()
        lexeme = self.source[start : self.pos]
        return self._token(TokenKind.CHAR, lexeme, start, self.pos, line, col)

    def _skip_line_comment(self) -> None:
        self._advance_n(2)
        while not self._at_end() and self._peek() != "\n":
            self._advance()

    def _skip_block_comment(self) -> None:
        start = self.pos
        line = self.line
        col = self.col
        self._advance_n(2)
        while not self._at_end():
            if self._peek() == "*" and self._peek_next() == "/":
                self._advance_n(2)
                return
            self._advance()
        raise MidoriError(
            span=Span(self.file, start, self.pos, line, col),
            message="unterminated block comment",
            hint="add closing */",
        )

    def _token(
        self, kind: TokenKind, lexeme: str, start: int, end: int, line: int, col: int
    ) -> Token:
        return Token(kind=kind, lexeme=lexeme, span=Span(self.file, start, end, line, col))

    def _at_end(self) -> bool:
        return self.pos >= len(self.source)

    def _peek(self) -> str:
        return self.source[self.pos]

    def _peek_next(self) -> str:
        i = self.pos + 1
        return self.source[i] if i < len(self.source) else "\0"

    def _advance(self) -> str:
        ch = self.source[self.pos]
        self.pos += 1
        if ch == "\n":
            self.line += 1
            self.col = 1
        else:
            self.col += 1
        return ch

    def _advance_n(self, n: int) -> None:
        for _ in range(n):
            self._advance()
