from __future__ import annotations

import sys
from dataclasses import dataclass

from midori_compiler.span import Span


@dataclass
class MidoriError(Exception):
    span: Span
    message: str
    hint: str | None = None
    code: str | None = None

    def __post_init__(self) -> None:
        if self.code is None:
            module = _caller_module()
            self.code = _infer_error_code(module, self.message)

    def __str__(self) -> str:
        code = self.code or "MD0001"
        out = f"{self.span.format()}: error[{code}]: {self.message}"
        if self.hint:
            out += f"\n  hint: {self.hint}"
        return out


def _caller_module() -> str:
    frame = sys._getframe(2)
    while frame is not None:
        module = frame.f_globals.get("__name__", "")
        if module != __name__:
            return str(module)
        frame = frame.f_back
    return ""


def _infer_error_code(module: str, message: str) -> str:
    lower = message.lower()

    if module.startswith("midori_compiler.lexer"):
        if "invalid character" in lower:
            return "MD1001"
        if "unterminated string literal" in lower:
            return "MD1002"
        if "unterminated char literal" in lower:
            return "MD1003"
        if "invalid char literal" in lower:
            return "MD1004"
        if "unterminated block comment" in lower:
            return "MD1005"
        return "MD1000"

    if module.startswith("midori_compiler.parser"):
        if lower.startswith("expected "):
            return "MD2001"
        return "MD2000"

    if module.startswith("midori_typecheck.resolver"):
        if "duplicate function" in lower:
            return "MD3001"
        if "duplicate enum" in lower:
            return "MD3002"
        if "duplicate enum variant" in lower:
            return "MD3003"
        if "missing entry point function" in lower:
            return "MD3004"
        if "duplicate custom error" in lower:
            return "MD3005"
        return "MD3000"

    if module.startswith("midori_typecheck.checker"):
        if "unknown name" in lower:
            return "MD3101"
        if "type mismatch" in lower:
            return "MD3102"
        if "cannot assign to immutable variable" in lower:
            return "MD3103"
        if "wrong number of arguments" in lower:
            return "MD3104"
        if "`?` expects result" in lower:
            return "MD3105"
        if "`?` can only be used" in lower:
            return "MD3106"
        if "variant pattern" in lower and "requires enum target" in lower:
            return "MD3107"
        if "unknown variant" in lower:
            return "MD3108"
        if "ambiguous variant constructor" in lower:
            return "MD3109"
        if "unsupported" in lower:
            return "MD3110"
        if "unknown custom error kind" in lower:
            return "MD3111"
        if "`raise`" in lower:
            return "MD3112"
        return "MD3100"

    if module.startswith("midori_ir.borrow"):
        if "use after move" in lower:
            return "MD4001"
        if "cannot mutably borrow" in lower:
            return "MD4002"
        if "cannot immutably borrow" in lower:
            return "MD4003"
        if "cannot borrow moved value" in lower:
            return "MD4004"
        if "while mutably borrowed" in lower:
            return "MD4005"
        return "MD4000"

    if module.startswith("midori_ir.lowering"):
        if "not implemented yet" in lower:
            return "MD5001"
        if "expects result" in lower:
            return "MD5002"
        return "MD5000"

    if module.startswith("midori_codegen_llvm"):
        return "MD6000"

    if module.startswith("midori_cli"):
        return "MD7000"

    return "MD0001"
