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
    block: ast.BlockExpr,
    states: dict[str, _State],
    expr_types: dict[int, Type],
) -> None:
    release_ops: list[tuple[str, str]] = []
    shadowed: dict[str, _State | None] = {}
    locals_defined: set[str] = set()

    for stmt in block.statements:
        if isinstance(stmt, ast.LetStmt):
            _visit_expr(stmt.expr, states, expr_types, release_ops)
            if isinstance(stmt.expr, ast.IdentifierExpr):
                src = stmt.expr.name
                src_state = states.get(src)
                src_ty = expr_types.get(id(stmt.expr))
                if src_state and src_ty and not src_ty.is_copy:
                    src_state.moved = True
            if stmt.name not in shadowed:
                shadowed[stmt.name] = states.get(stmt.name)
            states[stmt.name] = _State(ty=expr_types.get(id(stmt.expr)))
            locals_defined.add(stmt.name)
            continue
        if isinstance(stmt, ast.ExprStmt):
            _visit_expr(stmt.expr, states, expr_types, release_ops)
            continue
        if isinstance(stmt, ast.ReturnStmt) and stmt.expr:
            _visit_expr(stmt.expr, states, expr_types, release_ops)
            continue

    if block.tail:
        _visit_expr(block.tail, states, expr_types, release_ops)

    for name, kind in release_ops:
        s = states.get(name)
        if s is None:
            continue
        if kind == "imm":
            s.imm_borrows = max(0, s.imm_borrows - 1)
        else:
            s.mut_borrow = False

    # Restore shadowed/lexical locals on block exit.
    for local in locals_defined:
        old = shadowed.get(local)
        if old is None:
            states.pop(local, None)
        else:
            states[local] = old


def _visit_expr(
    expr: ast.Expr,
    states: dict[str, _State],
    expr_types: dict[int, Type],
    release_ops: list[tuple[str, str]],
) -> None:
    if isinstance(expr, ast.IdentifierExpr):
        s = states.get(expr.name)
        if s and s.moved:
            raise MidoriError(span=expr.span, message=f"use after move of '{expr.name}'")
        if s and s.mut_borrow:
            raise MidoriError(
                span=expr.span,
                message=f"cannot use '{expr.name}' while mutably borrowed",
            )
        return

    if isinstance(expr, ast.UnaryExpr) and expr.op in {"&", "&mut"}:
        if not isinstance(expr.expr, ast.IdentifierExpr):
            _visit_expr(expr.expr, states, expr_types, release_ops)
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
            return
        if s.mut_borrow or s.imm_borrows > 0:
            raise MidoriError(
                span=expr.span,
                message=f"cannot mutably borrow '{name}' while already borrowed",
            )
        s.mut_borrow = True
        release_ops.append((name, "mut"))
        return

    if isinstance(expr, ast.IfExpr):
        _visit_expr(expr.condition, states, expr_types, release_ops)
        base = _clone_states(states)

        then_states = _clone_states(base)
        _check_block(expr.then_block, then_states, expr_types)

        else_states = _clone_states(base)
        if expr.else_branch:
            _visit_expr(expr.else_branch, else_states, expr_types, [])

        _merge_branch_states(states, base, [then_states, else_states])
        return

    if isinstance(expr, ast.MatchExpr):
        _visit_expr(expr.expr, states, expr_types, release_ops)
        base = _clone_states(states)
        branch_states: list[dict[str, _State]] = []
        for arm in expr.arms:
            arm_states = _clone_states(base)
            _bind_pattern_names(arm.pattern, arm_states, expr_types, expr)
            _visit_expr(arm.expr, arm_states, expr_types, [])
            branch_states.append(arm_states)
        if branch_states:
            _merge_branch_states(states, base, branch_states)
        return

    if isinstance(expr, ast.BlockExpr):
        _check_block(expr, states, expr_types)
        return

    for child in _children(expr):
        _visit_expr(child, states, expr_types, release_ops)


def _bind_pattern_names(
    pattern: ast.Pattern,
    states: dict[str, _State],
    expr_types: dict[int, Type],
    match_expr: ast.MatchExpr,
) -> None:
    target_ty = expr_types.get(id(match_expr.expr))
    if isinstance(pattern, ast.NamePattern):
        # For enum-variant shorthand in match, the typechecker already validated variant names.
        # We conservatively bind only non-variant names as locals.
        if target_ty and target_ty.name not in {"Result", "Option"} and target_ty.name[0].isupper():
            # Likely enum type; avoid accidentally shadowing variant names.
            return
        states[pattern.name] = _State(ty=target_ty)
        return
    if isinstance(pattern, ast.VariantPattern):
        for bind_name in pattern.fields:
            states[bind_name] = _State(ty=Type("Unknown"))


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
    if isinstance(expr, ast.RangeExpr):
        return [expr.start, expr.end]
    if isinstance(expr, ast.PostfixTryExpr):
        return [expr.expr]
    if isinstance(expr, ast.UnsafeExpr):
        return [expr.block]
    if isinstance(expr, (ast.SpawnExpr, ast.AwaitExpr)):
        return [expr.expr]
    if isinstance(expr, ast.StructInitExpr):
        return [f.expr for f in expr.fields]
    return []


def _clone_states(states: dict[str, _State]) -> dict[str, _State]:
    return {
        name: _State(
            moved=state.moved,
            imm_borrows=state.imm_borrows,
            mut_borrow=state.mut_borrow,
            ty=state.ty,
        )
        for name, state in states.items()
    }


def _merge_branch_states(
    states: dict[str, _State],
    base: dict[str, _State],
    branches: list[dict[str, _State]],
) -> None:
    for name in base:
        base_state = base[name]
        merged = _State(
            moved=base_state.moved,
            imm_borrows=base_state.imm_borrows,
            mut_borrow=base_state.mut_borrow,
            ty=base_state.ty,
        )
        for branch in branches:
            b = branch.get(name)
            if not b:
                continue
            merged.moved = merged.moved or b.moved
            merged.imm_borrows = max(merged.imm_borrows, b.imm_borrows)
            merged.mut_borrow = merged.mut_borrow or b.mut_borrow
        states[name] = merged
