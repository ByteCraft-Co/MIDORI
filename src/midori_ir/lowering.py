from __future__ import annotations

from dataclasses import dataclass

from midori_compiler import ast
from midori_compiler.errors import MidoriError
from midori_ir.mir import (
    BasicBlock,
    BinOpInstr,
    BranchInstr,
    CallInstr,
    CondBranchInstr,
    ConstInstr,
    EnumConstructInstr,
    EnumFieldInstr,
    EnumLayout,
    EnumTagInstr,
    EnumVariantLayout,
    FunctionIR,
    PhiInstr,
    ProgramIR,
    ReturnInstr,
)
from midori_typecheck.checker import TypedProgram
from midori_typecheck.types import BOOL, FLOAT, INT, STRING, VOID, Type


@dataclass
class _Builder:
    fn_name: str
    fn_return_type: Type
    expr_types: dict[int, Type]
    enum_layouts: dict[str, EnumLayout]
    user_variant_constructors: dict[str, tuple[str, EnumVariantLayout]]

    def __post_init__(self) -> None:
        self.blocks: dict[str, BasicBlock] = {}
        self.block_index = 0
        self.temp_index = 0
        self.current = self.new_block("entry")
        self.entry = self.current.name
        self.env: dict[str, str] = {}

    def new_block(self, prefix: str) -> BasicBlock:
        name = f"{prefix}_{self.block_index}"
        self.block_index += 1
        bb = BasicBlock(name=name)
        self.blocks[name] = bb
        return bb

    def emit(self, instr) -> None:
        self.current.instructions.append(instr)

    def terminate(self, instr) -> None:
        self.current.terminator = instr

    def tmp(self) -> str:
        name = f"%t{self.temp_index}"
        self.temp_index += 1
        return name

    def lower_expr(self, expr: ast.Expr) -> str:
        if isinstance(expr, ast.LiteralExpr):
            out = self.tmp()
            self.emit(ConstInstr(target=out, value=expr.value, ty=self.expr_types[id(expr)]))
            return out
        if isinstance(expr, ast.IdentifierExpr):
            return self.env[expr.name]
        if isinstance(expr, ast.UnaryExpr):
            val = self.lower_expr(expr.expr)
            if expr.op == "-":
                zero = self.tmp()
                self.emit(ConstInstr(target=zero, value="0", ty=self.expr_types[id(expr)]))
                out = self.tmp()
                self.emit(
                    BinOpInstr(
                        target=out,
                        op="-",
                        left=zero,
                        right=val,
                        ty=self.expr_types[id(expr)],
                    )
                )
                return out
            if expr.op == "!":
                one = self.tmp()
                self.emit(ConstInstr(target=one, value="1", ty=BOOL))
                out = self.tmp()
                self.emit(BinOpInstr(target=out, op="^", left=val, right=one, ty=BOOL))
                return out
            # Borrow operators are for borrow-check diagnostics only.
            return val
        if isinstance(expr, ast.BinaryExpr):
            left = self.lower_expr(expr.left)
            right = self.lower_expr(expr.right)
            out = self.tmp()
            self.emit(
                BinOpInstr(
                    target=out,
                    op=expr.op,
                    left=left,
                    right=right,
                    ty=self.expr_types[id(expr)],
                )
            )
            return out
        if isinstance(expr, ast.AssignExpr):
            if not isinstance(expr.target, ast.IdentifierExpr):
                raise MidoriError(span=expr.span, message="assignment target must be an identifier")
            value = self.lower_expr(expr.value)
            self.env[expr.target.name] = value
            return value
        if isinstance(expr, ast.CallExpr):
            if not isinstance(expr.callee, ast.IdentifierExpr):
                raise MidoriError(
                    span=expr.span,
                    message="only direct function calls are supported in v0.2.0",
                )
            callee = expr.callee.name

            # Built-in Option/Result constructors are lowered to tagged-union values.
            if callee in {"Some", "None", "Ok", "Err"}:
                return self._lower_builtin_enum_constructor(callee, expr)

            # User enum variant constructors by bare variant name.
            constructor = self.user_variant_constructors.get(callee)
            if constructor is not None:
                enum_key, variant = constructor
                args = [self.lower_expr(a) for a in expr.args]
                out = self.tmp()
                self.emit(
                    EnumConstructInstr(
                        target=out,
                        enum_key=enum_key,
                        variant_index=variant.index,
                        fields=args,
                        field_types=variant.field_types,
                    )
                )
                return out

            args = [self.lower_expr(a) for a in expr.args]
            ret_ty = self.expr_types[id(expr)]
            target = None if ret_ty == VOID else self.tmp()
            self.emit(CallInstr(target=target, name=callee, args=args, ret_ty=ret_ty))
            return target or ""
        if isinstance(expr, ast.BlockExpr):
            return self.lower_block(expr)
        if isinstance(expr, ast.IfExpr):
            cond = self.lower_expr(expr.condition)
            then_bb = self.new_block("then")
            else_bb = self.new_block("else")
            join_bb = self.new_block("join")
            self.terminate(CondBranchInstr(cond=cond, then_bb=then_bb.name, else_bb=else_bb.name))

            old_env = self.env.copy()
            self.current = then_bb
            self.env = old_env.copy()
            then_val = self.lower_block(expr.then_block)
            then_end = self.current.name
            if self.current.terminator is None:
                self.terminate(BranchInstr(target=join_bb.name))

            self.current = else_bb
            self.env = old_env.copy()
            else_val = ""
            if expr.else_branch:
                else_val = self.lower_expr(expr.else_branch)
            else_end = self.current.name
            if self.current.terminator is None:
                self.terminate(BranchInstr(target=join_bb.name))

            self.current = join_bb
            self.env = old_env
            ty = self.expr_types[id(expr)]
            if ty == VOID:
                return ""
            out = self.tmp()
            self.emit(
                PhiInstr(target=out, incomings=[(then_end, then_val), (else_end, else_val)], ty=ty)
            )
            return out
        if isinstance(expr, ast.PostfixTryExpr):
            return self._lower_try_expr(expr)
        if isinstance(expr, ast.MatchExpr):
            return self._lower_match_expr(expr)
        if isinstance(expr, ast.UnsafeExpr):
            return self.lower_block(expr.block)
        if isinstance(expr, ast.RangeExpr):
            raise MidoriError(span=expr.span, message="range lowering is not implemented yet")
        if isinstance(expr, ast.StructInitExpr):
            raise MidoriError(
                span=expr.span,
                message="struct initialization lowering is not implemented yet",
            )
        if isinstance(expr, (ast.SpawnExpr, ast.AwaitExpr)):
            raise MidoriError(span=expr.span, message="concurrency lowering is not implemented yet")
        raise MidoriError(
            span=expr.span,
            message=f"unsupported expression in lowering: {type(expr).__name__}",
        )

    def _lower_builtin_enum_constructor(self, name: str, expr: ast.CallExpr) -> str:
        out_ty = self.expr_types[id(expr)]
        enum_key = _enum_key_for_type(out_ty)
        if enum_key is None:
            raise MidoriError(
                span=expr.span, message=f"cannot construct enum value for type {out_ty}"
            )
        if enum_key not in self.enum_layouts:
            raise MidoriError(
                span=expr.span, message=f"internal error: missing enum layout '{enum_key}'"
            )

        layout = self.enum_layouts[enum_key]
        variant_name = name
        if name == "Some":
            variant_name = "Some"
        if name == "None":
            variant_name = "None"
        if name == "Ok":
            variant_name = "Ok"
        if name == "Err":
            variant_name = "Err"

        variant = next((v for v in layout.variants if v.name == variant_name), None)
        if variant is None:
            raise MidoriError(
                span=expr.span,
                message=f"internal error: unknown variant '{variant_name}' for enum '{enum_key}'",
            )
        args = [self.lower_expr(a) for a in expr.args]
        out = self.tmp()
        self.emit(
            EnumConstructInstr(
                target=out,
                enum_key=enum_key,
                variant_index=variant.index,
                fields=args,
                field_types=variant.field_types,
            )
        )
        return out

    def _lower_try_expr(self, expr: ast.PostfixTryExpr) -> str:
        inner_ty = self.expr_types[id(expr.expr)]
        if inner_ty.name != "Result" or len(inner_ty.args) != 2:
            raise MidoriError(span=expr.span, message="`?` lowering expects Result[T, E]")
        if self.fn_return_type.name != "Result":
            raise MidoriError(
                span=expr.span,
                message="`?` can only be used in functions returning Result[T, E]",
            )
        enum_key = _enum_key_for_type(inner_ty)
        if enum_key is None:
            raise MidoriError(span=expr.span, message=f"missing enum key for {inner_ty}")

        result_val = self.lower_expr(expr.expr)
        tag_val = self.tmp()
        self.emit(EnumTagInstr(target=tag_val, source=result_val, enum_key=enum_key))

        ok_tag = self.tmp()
        self.emit(ConstInstr(target=ok_tag, value="0", ty=INT))
        is_ok = self.tmp()
        self.emit(BinOpInstr(target=is_ok, op="==", left=tag_val, right=ok_tag, ty=BOOL))

        ok_bb = self.new_block("try_ok")
        err_bb = self.new_block("try_err")
        self.terminate(CondBranchInstr(cond=is_ok, then_bb=ok_bb.name, else_bb=err_bb.name))

        self.current = err_bb
        self.terminate(ReturnInstr(value=result_val))

        self.current = ok_bb
        out = self.tmp()
        self.emit(
            EnumFieldInstr(
                target=out,
                source=result_val,
                enum_key=enum_key,
                field_index=0,
                field_ty=inner_ty.args[0],
            )
        )
        return out

    def _lower_match_expr(self, expr: ast.MatchExpr) -> str:
        target_val = self.lower_expr(expr.expr)
        target_ty = self.expr_types[id(expr.expr)]
        out_ty = self.expr_types[id(expr)]
        end_bb = self.new_block("match_end")
        incoming: list[tuple[str, str]] = []

        base_env = self.env.copy()
        test_bb = self.current
        remaining_arms = list(expr.arms)
        while remaining_arms:
            arm = remaining_arms.pop(0)
            arm_bb = self.new_block("match_arm")

            self.current = test_bb
            cond = self._lower_pattern_condition(arm.pattern, target_val, target_ty)
            if cond is None:
                self.terminate(BranchInstr(target=arm_bb.name))
                test_bb = self.new_block("match_dead")
                remaining_arms.clear()
            else:
                next_bb = self.new_block("match_next")
                self.terminate(
                    CondBranchInstr(cond=cond, then_bb=arm_bb.name, else_bb=next_bb.name)
                )
                test_bb = next_bb

            self.current = arm_bb
            self.env = base_env.copy()
            self._bind_pattern(arm.pattern, target_val, target_ty)
            arm_val = self.lower_expr(arm.expr)
            arm_end = self.current.name
            if self.current.terminator is None:
                self.terminate(BranchInstr(target=end_bb.name))
                if out_ty != VOID:
                    incoming.append((arm_end, arm_val))

        self.current = test_bb
        if self.current.terminator is None:
            # Non-exhaustive runtime fallback for v0.2.0: synthesize default value.
            default_val = ""
            if out_ty != VOID:
                default_val = self._emit_default_value(out_ty)
            self.terminate(BranchInstr(target=end_bb.name))
            if out_ty != VOID:
                incoming.append((self.current.name, default_val))

        self.current = end_bb
        self.env = base_env
        if out_ty == VOID:
            return ""
        out = self.tmp()
        self.emit(PhiInstr(target=out, incomings=incoming, ty=out_ty))
        return out

    def _lower_pattern_condition(
        self, pattern: ast.Pattern, target_val: str, target_ty: Type
    ) -> str | None:
        if isinstance(pattern, ast.WildcardPattern):
            return None
        if isinstance(pattern, ast.NamePattern):
            enum_key = _enum_key_for_type(target_ty)
            if enum_key and enum_key in self.enum_layouts:
                variant = self._lookup_variant(enum_key, pattern.name)
                if variant and not variant.field_types:
                    return self._emit_variant_cond(enum_key, target_val, variant.index)
            return None
        if isinstance(pattern, ast.LiteralPattern):
            lit_temp = self.tmp()
            self.emit(ConstInstr(target=lit_temp, value=pattern.value, ty=target_ty))
            cond = self.tmp()
            self.emit(BinOpInstr(target=cond, op="==", left=target_val, right=lit_temp, ty=BOOL))
            return cond
        if isinstance(pattern, ast.VariantPattern):
            enum_key = _enum_key_for_type(target_ty)
            if not enum_key:
                raise MidoriError(span=pattern.span, message="variant pattern expects enum target")
            variant = self._lookup_variant(enum_key, pattern.name)
            if variant is None:
                raise MidoriError(
                    span=pattern.span,
                    message=f"unknown variant '{pattern.name}' for enum '{enum_key}'",
                )
            return self._emit_variant_cond(enum_key, target_val, variant.index)
        raise MidoriError(
            span=pattern.span, message=f"unsupported pattern {type(pattern).__name__}"
        )

    def _emit_variant_cond(self, enum_key: str, target_val: str, variant_index: int) -> str:
        tag = self.tmp()
        self.emit(EnumTagInstr(target=tag, source=target_val, enum_key=enum_key))
        wanted = self.tmp()
        self.emit(ConstInstr(target=wanted, value=str(variant_index), ty=INT))
        cond = self.tmp()
        self.emit(BinOpInstr(target=cond, op="==", left=tag, right=wanted, ty=BOOL))
        return cond

    def _bind_pattern(self, pattern: ast.Pattern, target_val: str, target_ty: Type) -> None:
        if isinstance(pattern, ast.NamePattern):
            enum_key = _enum_key_for_type(target_ty)
            if enum_key and enum_key in self.enum_layouts:
                variant = self._lookup_variant(enum_key, pattern.name)
                if variant and not variant.field_types:
                    return
            self.env[pattern.name] = target_val
            return
        if isinstance(pattern, ast.VariantPattern):
            enum_key = _enum_key_for_type(target_ty)
            if not enum_key:
                return
            variant = self._lookup_variant(enum_key, pattern.name)
            if variant is None:
                return
            for i, bind_name in enumerate(pattern.fields):
                temp = self.tmp()
                self.emit(
                    EnumFieldInstr(
                        target=temp,
                        source=target_val,
                        enum_key=enum_key,
                        field_index=i,
                        field_ty=variant.field_types[i],
                    )
                )
                self.env[bind_name] = temp

    def _lookup_variant(self, enum_key: str, variant_name: str) -> EnumVariantLayout | None:
        layout = self.enum_layouts.get(enum_key)
        if not layout:
            return None
        for variant in layout.variants:
            if variant.name == variant_name:
                return variant
        return None

    def _emit_default_value(self, ty: Type) -> str:
        if ty == VOID:
            return ""
        if ty == INT:
            out = self.tmp()
            self.emit(ConstInstr(target=out, value="0", ty=INT))
            return out
        if ty == FLOAT:
            out = self.tmp()
            self.emit(ConstInstr(target=out, value="0.0", ty=FLOAT))
            return out
        if ty == BOOL:
            out = self.tmp()
            self.emit(ConstInstr(target=out, value="false", ty=BOOL))
            return out
        if ty == STRING:
            out = self.tmp()
            self.emit(ConstInstr(target=out, value='""', ty=STRING))
            return out
        enum_key = _enum_key_for_type(ty)
        if enum_key and enum_key in self.enum_layouts:
            layout = self.enum_layouts[enum_key]
            first = layout.variants[0]
            field_vals: list[str] = []
            for f_ty in first.field_types:
                field_vals.append(self._emit_default_value(f_ty))
            out = self.tmp()
            self.emit(
                EnumConstructInstr(
                    target=out,
                    enum_key=enum_key,
                    variant_index=first.index,
                    fields=field_vals,
                    field_types=first.field_types,
                )
            )
            return out
        out = self.tmp()
        self.emit(ConstInstr(target=out, value="0", ty=INT))
        return out

    def lower_stmt(self, stmt: ast.Stmt) -> None:
        if isinstance(stmt, ast.LetStmt):
            value = self.lower_expr(stmt.expr)
            self.env[stmt.name] = value
            return
        if isinstance(stmt, ast.ReturnStmt):
            value = self.lower_expr(stmt.expr) if stmt.expr else None
            self.terminate(ReturnInstr(value=value))
            self.current = self.new_block("dead")
            return
        if isinstance(stmt, ast.ExprStmt):
            self.lower_expr(stmt.expr)
            return
        if isinstance(stmt, (ast.BreakStmt, ast.ContinueStmt)):
            raise MidoriError(
                span=stmt.span,
                message=f"{type(stmt).__name__} lowering is not implemented yet",
            )
        raise MidoriError(
            span=stmt.span,
            message=f"unsupported statement in lowering: {type(stmt).__name__}",
        )

    def lower_block(self, block: ast.BlockExpr) -> str:
        old_env = self.env.copy()
        for stmt in block.statements:
            self.lower_stmt(stmt)
        if block.tail:
            out = self.lower_expr(block.tail)
            self.env = old_env
            return out
        self.env = old_env
        return ""


def _enum_key_for_type(ty: Type) -> str | None:
    if ty.name in {"Option", "Result"} and ty.args:
        return str(ty)
    if ty.name in {
        "Int",
        "Float",
        "Bool",
        "Char",
        "String",
        "Void",
        "Range",
        "Ref",
        "Ptr",
        "Unknown",
    }:
        return None
    return ty.name


def _collect_type_enums(ty: Type, typed: TypedProgram, out: set[str]) -> None:
    key = _enum_key_for_type(ty)
    if key is not None:
        if ty.name in typed.enums or ty.name in {"Option", "Result"}:
            out.add(key)
    for arg in ty.args:
        _collect_type_enums(arg, typed, out)


def _layout_for_enum_key(enum_key: str, typed: TypedProgram) -> EnumLayout:
    if enum_key in typed.enums:
        enum_info = typed.enums[enum_key]
        variants = [
            EnumVariantLayout(name=v.name, index=v.index, field_types=v.field_types)
            for v in sorted(enum_info.variants.values(), key=lambda x: x.index)
        ]
        payload_slots = max((len(v.field_types) for v in variants), default=0)
        return EnumLayout(key=enum_key, variants=variants, payload_slots=payload_slots)

    if enum_key.startswith("Option["):
        # Option[T] -> tag 0 = Some(T), tag 1 = None
        # Parse T from the encoded type string by round-tripping through known type map is unnecessary;
        # we derive the field type from runtime use-site when constructing/enforcing through expr types.
        inner = enum_key[len("Option[") : -1]
        ty = Type(inner) if "," not in inner and "[" not in inner else Type("Unknown")
        variants = [
            EnumVariantLayout(name="Some", index=0, field_types=[ty]),
            EnumVariantLayout(name="None", index=1, field_types=[]),
        ]
        return EnumLayout(key=enum_key, variants=variants, payload_slots=1)

    if enum_key.startswith("Result["):
        # Result[T, E] parsing (best-effort for current v0.2.0 type rendering).
        inside = enum_key[len("Result[") : -1]
        split = inside.split(",")
        ok_ty = Type(split[0].strip()) if split else Type("Unknown")
        err_ty = Type(split[1].strip()) if len(split) > 1 else Type("Unknown")
        variants = [
            EnumVariantLayout(name="Ok", index=0, field_types=[ok_ty]),
            EnumVariantLayout(name="Err", index=1, field_types=[err_ty]),
        ]
        return EnumLayout(key=enum_key, variants=variants, payload_slots=1)

    raise RuntimeError(f"missing enum layout for '{enum_key}'")


def lower_typed_program(typed: TypedProgram) -> ProgramIR:
    enum_keys: set[str] = set()
    for fn in typed.functions.values():
        _collect_type_enums(fn.fn_type.ret, typed, enum_keys)
        for p_ty in fn.fn_type.params:
            _collect_type_enums(p_ty, typed, enum_keys)
        for expr_ty in fn.expr_types.values():
            _collect_type_enums(expr_ty, typed, enum_keys)

    enum_layouts = {key: _layout_for_enum_key(key, typed) for key in enum_keys}

    user_variant_constructors: dict[str, tuple[str, EnumVariantLayout]] = {}
    ambiguous: set[str] = set()
    for key, layout in enum_layouts.items():
        if key not in typed.enums:
            continue
        for variant in layout.variants:
            if variant.name in user_variant_constructors:
                ambiguous.add(variant.name)
                continue
            user_variant_constructors[variant.name] = (key, variant)
    for name in ambiguous:
        user_variant_constructors.pop(name, None)

    functions: dict[str, FunctionIR] = {}
    for name, typed_fn in typed.functions.items():
        builder = _Builder(
            fn_name=name,
            fn_return_type=typed_fn.fn_type.ret,
            expr_types=typed_fn.expr_types,
            enum_layouts=enum_layouts,
            user_variant_constructors=user_variant_constructors,
        )
        for i, param in enumerate(typed_fn.decl.params):
            builder.env[param.name] = f"%arg{i}"
        tail = builder.lower_block(typed_fn.decl.body)
        if builder.current.terminator is None:
            if typed_fn.fn_type.ret == VOID:
                builder.terminate(ReturnInstr(value=None))
            else:
                builder.terminate(ReturnInstr(value=tail))
        functions[name] = FunctionIR(
            name=name,
            params=[
                (p.name, typed_fn.fn_type.params[i]) for i, p in enumerate(typed_fn.decl.params)
            ],
            return_type=typed_fn.fn_type.ret,
            blocks=builder.blocks,
            entry=builder.entry,
        )
    return ProgramIR(functions=functions, enums=enum_layouts)


def is_codegen_supported_type(ty: Type) -> bool:
    return ty in {INT, BOOL, STRING, VOID, FLOAT} or _enum_key_for_type(ty) is not None
