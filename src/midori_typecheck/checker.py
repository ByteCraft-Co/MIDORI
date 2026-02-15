from __future__ import annotations

from dataclasses import dataclass

from midori_compiler import ast
from midori_compiler.errors import MidoriError
from midori_typecheck.resolver import Resolution
from midori_typecheck.types import (
    BOOL,
    CHAR,
    FLOAT,
    INT,
    STRING,
    UNKNOWN,
    VOID,
    Type,
    option_type,
    result_type,
)


@dataclass
class FunctionType:
    params: list[Type]
    ret: Type


@dataclass
class TypedFunction:
    decl: ast.FunctionDecl
    fn_type: FunctionType
    expr_types: dict[int, Type]
    local_types: dict[str, Type]


@dataclass
class TypedProgram:
    program: ast.Program
    functions: dict[str, TypedFunction]


@dataclass
class _VarState:
    ty: Type
    mutable: bool


def check_program(program: ast.Program, resolution: Resolution) -> TypedProgram:
    fn_types: dict[str, FunctionType] = {}
    for name, sym in resolution.functions.items():
        params = [_type_from_ref(p.ty) for p in sym.decl.params]
        ret = _type_from_ref(sym.decl.return_type) if sym.decl.return_type else VOID
        fn_types[name] = FunctionType(params=params, ret=ret)

    typed_funcs: dict[str, TypedFunction] = {}
    for name, sym in resolution.functions.items():
        typed_funcs[name] = _check_function(sym.decl, fn_types)
    return TypedProgram(program=program, functions=typed_funcs)


def _check_function(decl: ast.FunctionDecl, fn_types: dict[str, FunctionType]) -> TypedFunction:
    if decl.generic_params:
        raise MidoriError(
            span=decl.span,
            message=f"generic function '{decl.name}' is parsed but not typechecked in MVP",
            hint="remove generic parameters for now",
        )
    vars_map: dict[str, _VarState] = {}
    expr_types: dict[int, Type] = {}
    saw_explicit_return = False
    for i, p in enumerate(decl.params):
        vars_map[p.name] = _VarState(ty=fn_types[decl.name].params[i], mutable=False)

    def note(expr: ast.Expr, ty: Type) -> Type:
        expr_types[id(expr)] = ty
        return ty

    def infer(expr: ast.Expr) -> Type:
        if isinstance(expr, ast.LiteralExpr):
            if expr.kind == "int":
                return note(expr, INT)
            if expr.kind == "float":
                return note(expr, FLOAT)
            if expr.kind == "char":
                return note(expr, CHAR)
            if expr.kind in {"true", "false"}:
                return note(expr, BOOL)
            return note(expr, STRING)
        if isinstance(expr, ast.IdentifierExpr):
            if expr.name not in vars_map:
                raise MidoriError(
                    span=expr.span, message=f"unknown name '{expr.name}'", hint="declare it first"
                )
            return note(expr, vars_map[expr.name].ty)
        if isinstance(expr, ast.UnaryExpr):
            inner = infer(expr.expr)
            if expr.op in {"-", "!"}:
                return note(expr, BOOL if expr.op == "!" else inner)
            if expr.op in {"&", "&mut"}:
                return note(expr, Type("Ref", (inner,)))
            raise MidoriError(span=expr.span, message=f"unsupported unary operator '{expr.op}'")
        if isinstance(expr, ast.BinaryExpr):
            left = infer(expr.left)
            right = infer(expr.right)
            if left != right:
                raise MidoriError(span=expr.span, message=f"type mismatch: {left} vs {right}")
            if expr.op in {"+", "-", "*", "/", "%"}:
                return note(expr, left)
            if expr.op in {"==", "!=", "<", "<=", ">", ">=", "&&", "||"}:
                return note(expr, BOOL)
            raise MidoriError(span=expr.span, message=f"unsupported binary operator '{expr.op}'")
        if isinstance(expr, ast.AssignExpr):
            if not isinstance(expr.target, ast.IdentifierExpr):
                raise MidoriError(span=expr.span, message="assignment target must be an identifier")
            if expr.target.name not in vars_map:
                raise MidoriError(span=expr.span, message=f"unknown name '{expr.target.name}'")
            state = vars_map[expr.target.name]
            if not state.mutable:
                raise MidoriError(
                    span=expr.span,
                    message=f"cannot assign to immutable variable '{expr.target.name}'",
                )
            value_ty = infer(expr.value)
            _ensure_assignable(state.ty, value_ty, expr.span)
            return note(expr, state.ty)
        if isinstance(expr, ast.CallExpr):
            if isinstance(expr.callee, ast.IdentifierExpr):
                name = expr.callee.name
                if name == "print":
                    for arg in expr.args:
                        infer(arg)
                    return note(expr, VOID)
                if name == "Some":
                    if len(expr.args) != 1:
                        raise MidoriError(span=expr.span, message="Some expects one argument")
                    return note(expr, option_type(infer(expr.args[0])))
                if name == "None":
                    return note(expr, option_type(UNKNOWN))
                if name == "Ok":
                    if len(expr.args) != 1:
                        raise MidoriError(span=expr.span, message="Ok expects one argument")
                    return note(expr, result_type(infer(expr.args[0]), UNKNOWN))
                if name == "Err":
                    if len(expr.args) != 1:
                        raise MidoriError(span=expr.span, message="Err expects one argument")
                    return note(expr, result_type(UNKNOWN, infer(expr.args[0])))
                sig = fn_types.get(name)
                if not sig:
                    raise MidoriError(span=expr.span, message=f"unknown function '{name}'")
                if len(expr.args) != len(sig.params):
                    raise MidoriError(
                        span=expr.span,
                        message=f"wrong number of arguments for '{name}': expected {len(sig.params)}, got {len(expr.args)}",
                    )
                for i, arg in enumerate(expr.args):
                    arg_ty = infer(arg)
                    _ensure_assignable(sig.params[i], arg_ty, arg.span)
                return note(expr, sig.ret)
            raise MidoriError(
                span=expr.span, message="only direct function calls are supported in MVP"
            )
        if isinstance(expr, ast.IfExpr):
            cond = infer(expr.condition)
            _ensure_assignable(BOOL, cond, expr.condition.span)
            then_ty = infer_block(expr.then_block)
            else_ty = VOID
            if expr.else_branch:
                else_ty = infer(expr.else_branch)
            if then_ty != else_ty:
                raise MidoriError(
                    span=expr.span, message=f"if branches type mismatch: {then_ty} vs {else_ty}"
                )
            return note(expr, then_ty)
        if isinstance(expr, ast.BlockExpr):
            return note(expr, infer_block(expr))
        if isinstance(expr, ast.RangeExpr):
            _ensure_assignable(INT, infer(expr.start), expr.start.span)
            _ensure_assignable(INT, infer(expr.end), expr.end.span)
            return note(expr, Type("Range"))
        if isinstance(expr, ast.PostfixTryExpr):
            inner = infer(expr.expr)
            if inner.name != "Result" or len(inner.args) != 2:
                raise MidoriError(span=expr.span, message="`?` expects Result[T, E]")
            return note(expr, inner.args[0])
        if isinstance(expr, ast.AwaitExpr):
            raise MidoriError(
                span=expr.span,
                message="await codegen is not implemented yet",
                hint="track roadmap in docs",
            )
        if isinstance(expr, ast.SpawnExpr):
            raise MidoriError(
                span=expr.span,
                message="spawn codegen is not implemented yet",
                hint="track roadmap in docs",
            )
        if isinstance(expr, ast.MatchExpr):
            if not expr.arms:
                raise MidoriError(span=expr.span, message="empty match expression")
            infer(expr.expr)
            arm_ty = infer(expr.arms[0].expr)
            for arm in expr.arms[1:]:
                _ensure_assignable(arm_ty, infer(arm.expr), arm.expr.span)
            return note(expr, arm_ty)
        if isinstance(expr, ast.StructInitExpr):
            for field in expr.fields:
                infer(field.expr)
            return note(expr, Type(expr.name))
        if isinstance(expr, ast.UnsafeExpr):
            return note(expr, infer_block(expr.block))
        raise MidoriError(span=expr.span, message=f"unsupported expression: {type(expr).__name__}")

    def infer_stmt(stmt: ast.Stmt) -> None:
        nonlocal saw_explicit_return
        if isinstance(stmt, ast.LetStmt):
            val_ty = infer(stmt.expr)
            out_ty = val_ty if stmt.inferred else _type_from_ref(stmt.ty)
            _ensure_assignable(out_ty, val_ty, stmt.span)
            vars_map[stmt.name] = _VarState(ty=out_ty, mutable=stmt.mutable)
            return
        if isinstance(stmt, ast.ReturnStmt):
            saw_explicit_return = True
            expected = fn_types[decl.name].ret
            actual = VOID if stmt.expr is None else infer(stmt.expr)
            _ensure_assignable(expected, actual, stmt.span)
            return
        if isinstance(stmt, ast.ExprStmt):
            infer(stmt.expr)
            return
        if isinstance(stmt, (ast.BreakStmt, ast.ContinueStmt)):
            return
        raise MidoriError(span=stmt.span, message=f"unsupported statement: {type(stmt).__name__}")

    def infer_block(block: ast.BlockExpr) -> Type:
        for stmt in block.statements:
            infer_stmt(stmt)
        if block.tail:
            return infer(block.tail)
        if saw_explicit_return:
            return fn_types[decl.name].ret
        return VOID

    body_ty = infer_block(decl.body)
    expected_ret = fn_types[decl.name].ret
    _ensure_assignable(expected_ret, body_ty, decl.body.span)
    return TypedFunction(
        decl=decl,
        fn_type=fn_types[decl.name],
        expr_types=expr_types,
        local_types={k: v.ty for k, v in vars_map.items()},
    )


def _type_from_ref(ref: ast.TypeRef | None) -> Type:
    if ref is None:
        return VOID
    args = tuple(_type_from_ref(x) for x in ref.args)
    if ref.is_ref or ref.is_mut_ref:
        return Type("Ref", (Type(ref.name, args),))
    if ref.is_ptr or ref.is_mut_ptr:
        return Type("Ptr", (Type(ref.name, args),))
    return Type(ref.name, args)


def _ensure_assignable(expected: Type, actual: Type, span) -> None:
    if expected == actual:
        return
    # Allow unknown placeholders in Option/Result constructors.
    if expected.name == actual.name and len(expected.args) == len(actual.args):
        for exp_arg, got_arg in zip(expected.args, actual.args, strict=True):
            if exp_arg.name == "Unknown" or got_arg.name == "Unknown":
                continue
            if exp_arg != got_arg:
                break
        else:
            return
    if expected.name == "Unknown" or actual.name == "Unknown":
        return
    raise MidoriError(span=span, message=f"type mismatch: expected {expected}, got {actual}")
