from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto

from midori_compiler.span import Span


class TokenKind(Enum):
    EOF = auto()
    NEWLINE = auto()

    IDENT = auto()
    INT = auto()
    FLOAT = auto()
    STRING = auto()
    CHAR = auto()

    FN = auto()
    LET = auto()
    VAR = auto()
    STRUCT = auto()
    ENUM = auto()
    TRAIT = auto()
    IMPL = auto()
    PUB = auto()
    USE = auto()
    MODULE = auto()
    IF = auto()
    ELSE = auto()
    MATCH = auto()
    FOR = auto()
    IN = auto()
    WHILE = auto()
    LOOP = auto()
    BREAK = auto()
    CONTINUE = auto()
    RETURN = auto()
    TASK = auto()
    SPAWN = auto()
    AWAIT = auto()
    UNSAFE = auto()
    EXTERN = auto()
    TRUE = auto()
    FALSE = auto()

    PLUS = auto()
    MINUS = auto()
    STAR = auto()
    SLASH = auto()
    PERCENT = auto()

    EQ = auto()
    EQEQ = auto()
    NE = auto()
    LT = auto()
    LE = auto()
    GT = auto()
    GE = auto()
    ANDAND = auto()
    OROR = auto()
    BANG = auto()

    PLUSEQ = auto()
    MINUSEQ = auto()
    STAREQ = auto()
    SLASHEQ = auto()
    PERCENTEQ = auto()
    COLONEQ = auto()

    DOTDOT = auto()
    DOTDOTEQ = auto()

    LBRACE = auto()
    RBRACE = auto()
    LPAREN = auto()
    RPAREN = auto()
    LBRACKET = auto()
    RBRACKET = auto()
    COMMA = auto()
    COLON = auto()
    SEMI = auto()
    DOT = auto()
    ARROW = auto()
    FATARROW = auto()
    QUESTION = auto()
    AMP = auto()


KEYWORDS: dict[str, TokenKind] = {
    "fn": TokenKind.FN,
    "let": TokenKind.LET,
    "var": TokenKind.VAR,
    "struct": TokenKind.STRUCT,
    "enum": TokenKind.ENUM,
    "trait": TokenKind.TRAIT,
    "impl": TokenKind.IMPL,
    "pub": TokenKind.PUB,
    "use": TokenKind.USE,
    "module": TokenKind.MODULE,
    "if": TokenKind.IF,
    "else": TokenKind.ELSE,
    "match": TokenKind.MATCH,
    "for": TokenKind.FOR,
    "in": TokenKind.IN,
    "while": TokenKind.WHILE,
    "loop": TokenKind.LOOP,
    "break": TokenKind.BREAK,
    "continue": TokenKind.CONTINUE,
    "return": TokenKind.RETURN,
    "task": TokenKind.TASK,
    "spawn": TokenKind.SPAWN,
    "await": TokenKind.AWAIT,
    "unsafe": TokenKind.UNSAFE,
    "extern": TokenKind.EXTERN,
    "true": TokenKind.TRUE,
    "false": TokenKind.FALSE,
}


@dataclass(frozen=True)
class Token:
    kind: TokenKind
    lexeme: str
    span: Span
