from __future__ import annotations

from dataclasses import dataclass

from midori_compiler import ast
from midori_compiler.errors import MidoriError
from midori_typecheck.checker import TypedProgram
from midori_typecheck.types import Type


@dataclass
class _State:
    moved: bool = False
    imm_borrows: int = 0
    mut_borrow: bool = False
    ty: Type | None = None


def run_borrow_check(typed: TypedProgram) -> None:
    for fn in typed.functions.values():
        states: dict[str, _State] = {}
        for name, ty in fn.local_types.items():
            states[name] = _State(ty=ty)
        for i, p in enumerate(fn.decl.params):
            states[p.name] = _State(ty=fn.fn_type.params[i])
        _check_block(fn.decl.body, states, fn.expr_types)


def _check_block(
    block: ast.BlockExpr, states: dict[str, _State], expr_types: dict[int, Type]
) -> None:
    release_ops: list[tuple[str, str]] = []

    def visit_expr(expr: ast.Expr) -> None:
        if isinstance(expr, ast.IdentifierExpr):
            s = states.get(expr.name)
            if s and s.moved:
                raise MidoriError(span=expr.span, message=f"use after move of '{expr.name}'")
            if s and s.mut_borrow:
                raise MidoriError(
                    span=expr.span, message=f"cannot use '{expr.name}' while mutably borrowed"
                )
            return
        if isinstance(expr, ast.UnaryExpr) and expr.op in {"&", "&mut"}:
            if not isinstance(expr.expr, ast.IdentifierExpr):
                return
            name = expr.expr.name
            s = states.get(name)
            if not s:
                return
            if s.moved:
                raise MidoriError(span=expr.span, message=f"cannot borrow moved value '{name}'")
            if expr.op == "&":
                if s.mut_borrow:
                    raise MidoriError(
                        span=expr.span,
                        message=f"cannot immutably borrow '{name}' while mutably borrowed",
                    )
                s.imm_borrows += 1
                release_ops.append((name, "imm"))
            else:
                if s.mut_borrow or s.imm_borrows > 0:
                    raise MidoriError(
                        span=expr.span,
                        message=f"cannot mutably borrow '{name}' while already borrowed",
                    )
                s.mut_borrow = True
                release_ops.append((name, "mut"))
            return

        for child in _children(expr):
            visit_expr(child)

    for stmt in block.statements:
        if isinstance(stmt, ast.LetStmt):
            visit_expr(stmt.expr)
            if isinstance(stmt.expr, ast.IdentifierExpr):
                src = stmt.expr.name
                src_state = states.get(src)
                src_ty = expr_types.get(id(stmt.expr))
                if src_state and src_ty and not src_ty.is_copy:
                    src_state.moved = True
            states.setdefault(stmt.name, _State(ty=expr_types.get(id(stmt.expr))))
            continue
        if isinstance(stmt, ast.ExprStmt):
            visit_expr(stmt.expr)
            continue
        if isinstance(stmt, ast.ReturnStmt) and stmt.expr:
            visit_expr(stmt.expr)
            continue
    if block.tail:
        visit_expr(block.tail)

    for name, kind in release_ops:
        s = states[name]
        if kind == "imm":
            s.imm_borrows -= 1
        else:
            s.mut_borrow = False


def _children(expr: ast.Expr) -> list[ast.Expr]:
    if isinstance(expr, ast.UnaryExpr):
        return [expr.expr]
    if isinstance(expr, ast.BinaryExpr):
        return [expr.left, expr.right]
    if isinstance(expr, ast.AssignExpr):
        return [expr.target, expr.value]
    if isinstance(expr, ast.CallExpr):
        out = [expr.callee]
        out.extend(expr.args)
        return out
    if isinstance(expr, ast.IfExpr):
        out = [expr.condition, expr.then_block]
        if expr.else_branch:
            out.append(expr.else_branch)
        return out
    if isinstance(expr, ast.BlockExpr):
        out: list[ast.Expr] = []
        for stmt in expr.statements:
            if isinstance(stmt, ast.ExprStmt):
                out.append(stmt.expr)
            if isinstance(stmt, ast.LetStmt):
                out.append(stmt.expr)
            if isinstance(stmt, ast.ReturnStmt) and stmt.expr:
                out.append(stmt.expr)
        if expr.tail:
            out.append(expr.tail)
        return out
    if isinstance(expr, ast.MatchExpr):
        out = [expr.expr]
        out.extend(arm.expr for arm in expr.arms)
        return out
    if isinstance(expr, ast.StructInitExpr):
        return [f.expr for f in expr.fields]
    if isinstance(expr, ast.RangeExpr):
        return [expr.start, expr.end]
    if isinstance(expr, ast.PostfixTryExpr):
        return [expr.expr]
    if isinstance(expr, ast.UnsafeExpr):
        return [expr.block]
    if isinstance(expr, (ast.SpawnExpr, ast.AwaitExpr)):
        return [expr.expr]
    return []
