from __future__ import annotations

from dataclasses import dataclass

from midori_compiler import ast
from midori_compiler.errors import MidoriError


@dataclass(frozen=True)
class FunctionSymbol:
    name: str
    decl: ast.FunctionDecl


@dataclass
class Resolution:
    functions: dict[str, FunctionSymbol]


def resolve_names(program: ast.Program) -> Resolution:
    functions: dict[str, FunctionSymbol] = {}
    for item in program.items:
        if isinstance(item, ast.FunctionDecl):
            if item.name in functions:
                raise MidoriError(
                    span=item.span,
                    message=f"duplicate function '{item.name}'",
                    hint="rename one declaration",
                )
            functions[item.name] = FunctionSymbol(name=item.name, decl=item)
    if "main" not in functions:
        raise MidoriError(
            span=program.span,
            message="missing entry point function 'main'",
            hint="add `fn main() -> Int { ... }`",
        )
    return Resolution(functions=functions)
