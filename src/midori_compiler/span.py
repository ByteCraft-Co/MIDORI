from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Span:
    file: str
    start: int
    end: int
    line: int
    col: int

    def format(self) -> str:
        return f"{self.file}:{self.line}:{self.col}"
