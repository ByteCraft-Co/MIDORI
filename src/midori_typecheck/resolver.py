from __future__ import annotations

from dataclasses import dataclass

from midori_compiler import ast
from midori_compiler.errors import MidoriError


@dataclass(frozen=True)
class FunctionSymbol:
    name: str
    decl: ast.FunctionDecl


@dataclass(frozen=True)
class EnumVariantSymbol:
    name: str
    index: int
    fields: list[ast.StructField]


@dataclass(frozen=True)
class EnumSymbol:
    name: str
    decl: ast.EnumDecl
    variants: dict[str, EnumVariantSymbol]


@dataclass(frozen=True)
class ErrorSymbol:
    name: str
    decl: ast.ErrorDecl


@dataclass
class Resolution:
    functions: dict[str, FunctionSymbol]
    enums: dict[str, EnumSymbol]
    errors: dict[str, ErrorSymbol]
    variants_by_name: dict[str, list[tuple[str, EnumVariantSymbol]]]


def resolve_names(program: ast.Program) -> Resolution:
    functions: dict[str, FunctionSymbol] = {}
    enums: dict[str, EnumSymbol] = {}
    errors: dict[str, ErrorSymbol] = {}
    variants_by_name: dict[str, list[tuple[str, EnumVariantSymbol]]] = {}
    for item in program.items:
        if isinstance(item, ast.FunctionDecl):
            if item.name in functions:
                raise MidoriError(
                    span=item.span,
                    message=f"duplicate function '{item.name}'",
                    hint="rename one declaration",
                )
            functions[item.name] = FunctionSymbol(name=item.name, decl=item)
        if isinstance(item, ast.EnumDecl):
            if item.name in enums:
                raise MidoriError(
                    span=item.span,
                    message=f"duplicate enum '{item.name}'",
                    hint="rename one declaration",
                )
            variants: dict[str, EnumVariantSymbol] = {}
            for i, variant in enumerate(item.variants):
                if variant.name in variants:
                    raise MidoriError(
                        span=variant.span,
                        message=f"duplicate enum variant '{variant.name}' in enum '{item.name}'",
                        hint="rename one variant",
                    )
                sym = EnumVariantSymbol(name=variant.name, index=i, fields=variant.fields)
                variants[variant.name] = sym
                variants_by_name.setdefault(variant.name, []).append((item.name, sym))
            enums[item.name] = EnumSymbol(name=item.name, decl=item, variants=variants)
        if isinstance(item, ast.ErrorDecl):
            if item.name in errors:
                raise MidoriError(
                    span=item.span,
                    message=f"duplicate custom error '{item.name}'",
                    hint="rename one custom error declaration",
                )
            errors[item.name] = ErrorSymbol(name=item.name, decl=item)
    if "main" not in functions:
        raise MidoriError(
            span=program.span,
            message="missing entry point function 'main'",
            hint="add `fn main() -> Int { ... }`",
        )
    return Resolution(
        functions=functions, enums=enums, errors=errors, variants_by_name=variants_by_name
    )
