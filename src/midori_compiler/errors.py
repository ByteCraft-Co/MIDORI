from __future__ import annotations

from dataclasses import dataclass

from midori_compiler.span import Span


@dataclass
class MidoriError(Exception):
    span: Span
    message: str
    hint: str | None = None

    def __str__(self) -> str:
        out = f"{self.span.format()}: error: {self.message}"
        if self.hint:
            out += f"\n  hint: {self.hint}"
        return out
