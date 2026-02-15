from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Type:
    name: str
    args: tuple[Type, ...] = field(default_factory=tuple)

    def __str__(self) -> str:
        if not self.args:
            return self.name
        inner = ", ".join(str(a) for a in self.args)
        return f"{self.name}[{inner}]"

    @property
    def is_copy(self) -> bool:
        return self.name in {"Int", "Float", "Bool", "Char"}


INT = Type("Int")
FLOAT = Type("Float")
BOOL = Type("Bool")
CHAR = Type("Char")
STRING = Type("String")
VOID = Type("Void")
UNKNOWN = Type("Unknown")


def result_type(ok: Type, err: Type) -> Type:
    return Type("Result", (ok, err))


def option_type(inner: Type) -> Type:
    return Type("Option", (inner,))
