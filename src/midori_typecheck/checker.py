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
    generic_params: list[str]


@dataclass
class EnumVariantInfo:
    name: str
    index: int
    field_types: list[Type]


@dataclass
class EnumInfo:
    name: str
    variants: dict[str, EnumVariantInfo]


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
    enums: dict[str, EnumInfo]
    warnings: list[str]


@dataclass
class _VarState:
    ty: Type
    mutable: bool


@dataclass
class _PatternResult:
    kind: str
    variant_name: str | None = None
    literal_value: str | None = None


def check_program(program: ast.Program, resolution: Resolution) -> TypedProgram:
    enums: dict[str, EnumInfo] = {}
    for enum_name, sym in resolution.enums.items():
        variants: dict[str, EnumVariantInfo] = {}
        for var_name, variant in sym.variants.items():
            variants[var_name] = EnumVariantInfo(
                name=variant.name,
                index=variant.index,
                field_types=[_type_from_ref(f.ty) for f in variant.fields],
            )
        enums[enum_name] = EnumInfo(name=enum_name, variants=variants)

    fn_types: dict[str, FunctionType] = {}
    for name, sym in resolution.functions.items():
        params = [_type_from_ref(p.ty) for p in sym.decl.params]
        ret = _type_from_ref(sym.decl.return_type) if sym.decl.return_type else VOID
        fn_types[name] = FunctionType(
            params=params, ret=ret, generic_params=sym.decl.generic_params
        )

    warnings: list[str] = []
    typed_funcs: dict[str, TypedFunction] = {}
    for name, sym in resolution.functions.items():
        typed_funcs[name] = _check_function(
            decl=sym.decl,
            fn_types=fn_types,
            enums=enums,
            variants_by_name=resolution.variants_by_name,
            custom_errors=set(resolution.errors.keys()),
            warnings=warnings,
        )
    return TypedProgram(program=program, functions=typed_funcs, enums=enums, warnings=warnings)


def _check_function(
    *,
    decl: ast.FunctionDecl,
    fn_types: dict[str, FunctionType],
    enums: dict[str, EnumInfo],
    variants_by_name: dict[str, list[tuple[str, object]]],
    custom_errors: set[str],
    warnings: list[str],
) -> TypedFunction:
    vars_map: dict[str, _VarState] = {}
    all_locals: dict[str, Type] = {}
    expr_types: dict[int, Type] = {}
    saw_explicit_return = False
    for i, p in enumerate(decl.params):
        vars_map[p.name] = _VarState(ty=fn_types[decl.name].params[i], mutable=False)
        all_locals[p.name] = fn_types[decl.name].params[i]

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
                    span=expr.span,
                    message=f"unknown name '{expr.name}'",
                    hint="declare it first",
                )
            return note(expr, vars_map[expr.name].ty)
        if isinstance(expr, ast.UnaryExpr):
            inner = infer(expr.expr)
            if expr.op == "-":
                if inner not in {INT, FLOAT}:
                    raise MidoriError(
                        span=expr.span,
                        message=f"type mismatch: expected Int or Float, got {inner}",
                    )
                return note(expr, inner)
            if expr.op == "!":
                _ensure_assignable(BOOL, inner, expr.span)
                return note(expr, BOOL)
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
            if not isinstance(expr.callee, ast.IdentifierExpr):
                raise MidoriError(
                    span=expr.span,
                    message="only direct function calls are supported",
                )
            name = expr.callee.name
            if name == "print":
                for arg in expr.args:
                    arg_ty = infer(arg)
                    if not _is_printable_type(arg_ty):
                        raise MidoriError(
                            span=arg.span,
                            message=f"unsupported print argument type {arg_ty}",
                            hint="print supports Int, Float, Bool, Char, and String",
                        )
                return note(expr, VOID)
            if name == "read_file":
                if len(expr.args) != 1:
                    raise MidoriError(span=expr.span, message="read_file expects one argument")
                _ensure_assignable(STRING, infer(expr.args[0]), expr.args[0].span)
                return note(expr, result_type(STRING, STRING))
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

            # User enum variant constructor by bare variant name.
            if name in variants_by_name:
                candidates = variants_by_name[name]
                if len(candidates) > 1:
                    enum_names = ", ".join(sorted(c[0] for c in candidates))
                    raise MidoriError(
                        span=expr.span,
                        message=f"ambiguous variant constructor '{name}'",
                        hint=f"rename variants to avoid ambiguity across enums: {enum_names}",
                    )
                enum_name = candidates[0][0]
                variant_info = enums[enum_name].variants[name]
                if len(expr.args) != len(variant_info.field_types):
                    raise MidoriError(
                        span=expr.span,
                        message=f"wrong number of arguments for variant '{name}': expected {len(variant_info.field_types)}, got {len(expr.args)}",
                    )
                for i, arg in enumerate(expr.args):
                    arg_ty = infer(arg)
                    _ensure_assignable(variant_info.field_types[i], arg_ty, arg.span)
                return note(expr, Type(enum_name))

            sig = fn_types.get(name)
            if not sig:
                raise MidoriError(span=expr.span, message=f"unknown function '{name}'")
            if sig.generic_params:
                # Monomorphization MVP: infer concrete call-site types and substitute return type.
                if len(expr.args) != len(sig.params):
                    raise MidoriError(
                        span=expr.span,
                        message=f"wrong number of arguments for '{name}': expected {len(sig.params)}, got {len(expr.args)}",
                    )
                subst: dict[str, Type] = {}
                for i, arg in enumerate(expr.args):
                    arg_ty = infer(arg)
                    _bind_generic(sig.params[i], arg_ty, subst, arg.span)
                for i, arg in enumerate(expr.args):
                    arg_ty = infer(arg)
                    exp_ty = _apply_subst(sig.params[i], subst)
                    _ensure_assignable(exp_ty, arg_ty, arg.span)
                return note(expr, _apply_subst(sig.ret, subst))

            if len(expr.args) != len(sig.params):
                raise MidoriError(
                    span=expr.span,
                    message=f"wrong number of arguments for '{name}': expected {len(sig.params)}, got {len(expr.args)}",
                )
            for i, arg in enumerate(expr.args):
                arg_ty = infer(arg)
                _ensure_assignable(sig.params[i], arg_ty, arg.span)
            return note(expr, sig.ret)

        if isinstance(expr, ast.IfExpr):
            cond = infer(expr.condition)
            _ensure_assignable(BOOL, cond, expr.condition.span)
            then_ty = infer_block(expr.then_block)
            else_ty = VOID
            if expr.else_branch:
                else_ty = infer(expr.else_branch)
            merged = _merge_branch_types(then_ty, else_ty, expr.span)
            if expr.then_block.tail is not None:
                expr_types[id(expr.then_block.tail)] = _coerce_unknown_type(merged, then_ty)
            if expr.else_branch is not None:
                coerced_else = _coerce_unknown_type(merged, else_ty)
                expr_types[id(expr.else_branch)] = coerced_else
                if (
                    isinstance(expr.else_branch, ast.BlockExpr)
                    and expr.else_branch.tail is not None
                ):
                    expr_types[id(expr.else_branch.tail)] = coerced_else
            return note(expr, merged)
        if isinstance(expr, ast.BlockExpr):
            return note(expr, infer_block(expr))
        if isinstance(expr, ast.RangeExpr):
            raise MidoriError(
                span=expr.span,
                message="unsupported range expression",
                hint="range lowering is not implemented yet",
            )
        if isinstance(expr, ast.PostfixTryExpr):
            inner = infer(expr.expr)
            if inner.name != "Result" or len(inner.args) != 2:
                raise MidoriError(span=expr.span, message="`?` expects Result[T, E]")
            fn_ret = fn_types[decl.name].ret
            if fn_ret.name != "Result" or len(fn_ret.args) != 2:
                raise MidoriError(
                    span=expr.span,
                    message="`?` can only be used in functions returning Result[T, E]",
                )
            _ensure_assignable(fn_ret.args[1], inner.args[1], expr.span)
            return note(expr, inner.args[0])
        if isinstance(expr, ast.RaiseExpr):
            if expr.kind not in custom_errors:
                raise MidoriError(
                    span=expr.span,
                    message=f"unknown custom error kind '{expr.kind}'",
                    hint=f"declare it first with `error {expr.kind}`",
                )
            fn_ret = fn_types[decl.name].ret
            if fn_ret.name != "Result" or len(fn_ret.args) != 2:
                raise MidoriError(
                    span=expr.span,
                    message="`raise` can only be used in functions returning Result[T, String]",
                )
            _ensure_assignable(STRING, fn_ret.args[1], expr.span)
            msg_ty = infer(expr.message)
            _ensure_assignable(STRING, msg_ty, expr.message.span)
            if not isinstance(expr.message, ast.LiteralExpr) or expr.message.kind != "string":
                raise MidoriError(
                    span=expr.message.span,
                    message="`raise` message must be a string literal",
                    hint='example: raise MyError("detail")',
                )
            return note(expr, UNKNOWN)
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
            target_ty = infer(expr.expr)
            seen_variants: set[str] = set()
            seen_bool_literals: set[str] = set()
            saw_catch_all = False

            arm_types: list[Type] = []
            for arm in expr.arms:
                old_scope = vars_map.copy()
                pat = check_pattern(arm.pattern, target_ty)
                if pat.kind == "variant" and pat.variant_name:
                    seen_variants.add(pat.variant_name)
                if pat.kind == "literal" and pat.literal_value in {"true", "false"}:
                    seen_bool_literals.add(pat.literal_value)
                if pat.kind in {"wildcard", "binding"}:
                    saw_catch_all = True
                arm_types.append(infer(arm.expr))
                vars_map.clear()
                vars_map.update(old_scope)

            arm_ty = arm_types[0]
            for got in arm_types[1:]:
                _ensure_assignable(arm_ty, got, expr.span)

            if not _is_exhaustive_match(
                target_ty, saw_catch_all, seen_variants, seen_bool_literals, enums
            ):
                raise MidoriError(
                    span=expr.span,
                    message=f"non-exhaustive match over type {target_ty}",
                    hint="add missing patterns or a trailing `_ => ...` arm",
                )
            return note(expr, arm_ty)
        if isinstance(expr, ast.StructInitExpr):
            raise MidoriError(
                span=expr.span,
                message="unsupported struct initialization expression",
                hint="struct initialization lowering is not implemented yet",
            )
        if isinstance(expr, ast.UnsafeExpr):
            return note(expr, infer_block(expr.block))
        raise MidoriError(span=expr.span, message=f"unsupported expression: {type(expr).__name__}")

    def check_pattern(pattern: ast.Pattern, target_ty: Type) -> _PatternResult:
        enum_variants = _enum_variants_for_type(target_ty, enums)
        if isinstance(pattern, ast.WildcardPattern):
            return _PatternResult(kind="wildcard")
        if isinstance(pattern, ast.LiteralPattern):
            lit_ty = _literal_pattern_type(pattern)
            _ensure_assignable(target_ty, lit_ty, pattern.span)
            return _PatternResult(kind="literal", literal_value=pattern.value)
        if isinstance(pattern, ast.VariantPattern):
            if enum_variants is None:
                raise MidoriError(
                    span=pattern.span,
                    message=f"variant pattern '{pattern.name}' requires enum target, got {target_ty}",
                )
            info = enum_variants.get(pattern.name)
            if not info:
                raise MidoriError(
                    span=pattern.span,
                    message=f"unknown variant '{pattern.name}' for enum '{target_ty.name}'",
                )
            if len(pattern.fields) != len(info.field_types):
                raise MidoriError(
                    span=pattern.span,
                    message=f"variant '{pattern.name}' expects {len(info.field_types)} bindings, got {len(pattern.fields)}",
                )
            for i, name in enumerate(pattern.fields):
                vars_map[name] = _VarState(ty=info.field_types[i], mutable=False)
            return _PatternResult(kind="variant", variant_name=pattern.name)
        if isinstance(pattern, ast.NamePattern):
            if enum_variants and pattern.name in enum_variants:
                info = enum_variants[pattern.name]
                if info.field_types:
                    raise MidoriError(
                        span=pattern.span,
                        message=f"variant '{pattern.name}' carries payload; use '{pattern.name}(...)' pattern",
                    )
                return _PatternResult(kind="variant", variant_name=pattern.name)
            vars_map[pattern.name] = _VarState(ty=target_ty, mutable=False)
            return _PatternResult(kind="binding")
        raise MidoriError(
            span=pattern.span, message=f"unsupported pattern: {type(pattern).__name__}"
        )

    def infer_stmt(stmt: ast.Stmt) -> None:
        nonlocal saw_explicit_return
        if isinstance(stmt, ast.LetStmt):
            val_ty = infer(stmt.expr)
            out_ty = val_ty if stmt.inferred else _type_from_ref(stmt.ty)
            _ensure_assignable(out_ty, val_ty, stmt.span)
            expr_types[id(stmt.expr)] = _coerce_unknown_type(out_ty, val_ty)
            vars_map[stmt.name] = _VarState(ty=out_ty, mutable=stmt.mutable)
            all_locals[stmt.name] = out_ty
            return
        if isinstance(stmt, ast.ReturnStmt):
            saw_explicit_return = True
            expected = fn_types[decl.name].ret
            actual = VOID if stmt.expr is None else infer(stmt.expr)
            _ensure_assignable(expected, actual, stmt.span)
            if stmt.expr is not None:
                expr_types[id(stmt.expr)] = _coerce_unknown_type(expected, actual)
            return
        if isinstance(stmt, ast.ExprStmt):
            infer(stmt.expr)
            return
        if isinstance(stmt, ast.BreakStmt):
            raise MidoriError(
                span=stmt.span,
                message="unsupported break statement",
                hint="loop lowering is not implemented yet",
            )
        if isinstance(stmt, ast.ContinueStmt):
            raise MidoriError(
                span=stmt.span,
                message="unsupported continue statement",
                hint="loop lowering is not implemented yet",
            )
        raise MidoriError(span=stmt.span, message=f"unsupported statement: {type(stmt).__name__}")

    def infer_block(block: ast.BlockExpr) -> Type:
        old_scope = vars_map.copy()
        for stmt in block.statements:
            infer_stmt(stmt)
        if block.tail:
            out = infer(block.tail)
            vars_map.clear()
            vars_map.update(old_scope)
            return out
        if saw_explicit_return:
            vars_map.clear()
            vars_map.update(old_scope)
            return fn_types[decl.name].ret
        vars_map.clear()
        vars_map.update(old_scope)
        return VOID

    body_ty = infer_block(decl.body)
    expected_ret = fn_types[decl.name].ret
    _ensure_assignable(expected_ret, body_ty, decl.body.span)
    if decl.body.tail is not None:
        coerced_tail = _coerce_unknown_type(expected_ret, body_ty)
        expr_types[id(decl.body.tail)] = coerced_tail
        if isinstance(decl.body.tail, ast.BlockExpr) and decl.body.tail.tail is not None:
            expr_types[id(decl.body.tail.tail)] = coerced_tail
    return TypedFunction(
        decl=decl,
        fn_type=fn_types[decl.name],
        expr_types=expr_types,
        local_types=all_locals,
    )


def _literal_pattern_type(pattern: ast.LiteralPattern) -> Type:
    val = pattern.value
    if val in {"true", "false"}:
        return BOOL
    if val.startswith('"') and val.endswith('"'):
        return STRING
    if val.startswith("'") and val.endswith("'"):
        return CHAR
    if "." in val and val.replace(".", "", 1).isdigit():
        return FLOAT
    if val.isdigit():
        return INT
    return UNKNOWN


def _is_exhaustive_match(
    target_ty: Type,
    saw_catch_all: bool,
    seen_variants: set[str],
    seen_bool_literals: set[str],
    enums: dict[str, EnumInfo],
) -> bool:
    if saw_catch_all:
        return True
    if target_ty == BOOL:
        return seen_bool_literals == {"true", "false"}
    enum_variants = _enum_variants_for_type(target_ty, enums)
    if enum_variants:
        needed = set(enum_variants.keys())
        return needed.issubset(seen_variants)
    return False


def _enum_variants_for_type(
    ty: Type, enums: dict[str, EnumInfo]
) -> dict[str, EnumVariantInfo] | None:
    if ty.name in enums:
        return enums[ty.name].variants
    if ty.name == "Option" and len(ty.args) == 1:
        inner = ty.args[0]
        return {
            "Some": EnumVariantInfo(name="Some", index=0, field_types=[inner]),
            "None": EnumVariantInfo(name="None", index=1, field_types=[]),
        }
    if ty.name == "Result" and len(ty.args) == 2:
        ok_ty = ty.args[0]
        err_ty = ty.args[1]
        return {
            "Ok": EnumVariantInfo(name="Ok", index=0, field_types=[ok_ty]),
            "Err": EnumVariantInfo(name="Err", index=1, field_types=[err_ty]),
        }
    return None


def _bind_generic(expected: Type, actual: Type, subst: dict[str, Type], span) -> None:
    # A generic parameter is represented as a bare type name in function signatures.
    if (
        not expected.args
        and expected.name
        and expected.name[0].isupper()
        and expected.name
        not in {
            "Int",
            "Float",
            "Bool",
            "Char",
            "String",
            "Void",
            "Result",
            "Option",
            "Ref",
            "Ptr",
            "Unknown",
        }
    ):
        prev = subst.get(expected.name)
        if prev is None:
            subst[expected.name] = actual
            return
        _ensure_assignable(prev, actual, span)
        return
    if expected.name != actual.name or len(expected.args) != len(actual.args):
        raise MidoriError(span=span, message=f"type mismatch: expected {expected}, got {actual}")
    for exp_arg, got_arg in zip(expected.args, actual.args, strict=True):
        _bind_generic(exp_arg, got_arg, subst, span)


def _apply_subst(ty: Type, subst: dict[str, Type]) -> Type:
    if (
        not ty.args
        and ty.name in subst
        and ty.name
        not in {
            "Int",
            "Float",
            "Bool",
            "Char",
            "String",
            "Void",
            "Result",
            "Option",
            "Ref",
            "Ptr",
            "Unknown",
        }
    ):
        return subst[ty.name]
    if not ty.args:
        return ty
    return Type(ty.name, tuple(_apply_subst(a, subst) for a in ty.args))


def _coerce_unknown_type(expected: Type, actual: Type) -> Type:
    if expected.name == actual.name and len(expected.args) == len(actual.args):
        merged_args: list[Type] = []
        for i, exp_arg in enumerate(expected.args):
            got = actual.args[i]
            if got.name == "Unknown":
                merged_args.append(exp_arg)
            elif exp_arg.name == "Unknown":
                merged_args.append(got)
            else:
                merged_args.append(_coerce_unknown_type(exp_arg, got))
        return Type(expected.name, tuple(merged_args))
    if actual.name == "Unknown":
        return expected
    return actual


def _is_printable_type(ty: Type) -> bool:
    return ty in {INT, FLOAT, BOOL, CHAR, STRING}


def _merge_branch_types(left: Type, right: Type, span) -> Type:
    if left == right:
        return left
    try:
        _ensure_assignable(left, right, span)
        return _coerce_unknown_type(left, right)
    except MidoriError:
        pass
    try:
        _ensure_assignable(right, left, span)
        return _coerce_unknown_type(right, left)
    except MidoriError:
        pass
    raise MidoriError(span=span, message=f"if branches type mismatch: {left} vs {right}")


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
