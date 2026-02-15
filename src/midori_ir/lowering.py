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
    FunctionIR,
    PhiInstr,
    ProgramIR,
    ReturnInstr,
)
from midori_typecheck.checker import TypedProgram
from midori_typecheck.types import BOOL, INT, STRING, VOID, Type


@dataclass
class _Builder:
    fn_name: str
    expr_types: dict[int, Type]

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
            ty = self.expr_types[id(expr)]
            self.emit(ConstInstr(target=out, value=expr.value, ty=ty))
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
            # Borrow ops are carried for borrow checker only.
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
                    span=expr.span, message="only direct function calls are supported in MVP"
                )
            args = [self.lower_expr(a) for a in expr.args]
            ret_ty = self.expr_types[id(expr)]
            target = None if ret_ty == VOID else self.tmp()
            self.emit(CallInstr(target=target, name=expr.callee.name, args=args, ret_ty=ret_ty))
            return target or ""
        if isinstance(expr, ast.BlockExpr):
            return self.lower_block(expr)
        if isinstance(expr, ast.IfExpr):
            cond = self.lower_expr(expr.condition)
            then_bb = self.new_block("then")
            else_bb = self.new_block("else")
            join_bb = self.new_block("join")
            self.terminate(CondBranchInstr(cond=cond, then_bb=then_bb.name, else_bb=else_bb.name))

            self.current = then_bb
            then_val = self.lower_block(expr.then_block)
            if self.current.terminator is None:
                self.terminate(BranchInstr(target=join_bb.name))
            then_end = self.current.name

            self.current = else_bb
            else_val = ""
            if expr.else_branch:
                else_val = self.lower_expr(expr.else_branch)
            if self.current.terminator is None:
                self.terminate(BranchInstr(target=join_bb.name))
            else_end = self.current.name

            self.current = join_bb
            ty = self.expr_types[id(expr)]
            if ty == VOID:
                return ""
            out = self.tmp()
            self.emit(
                PhiInstr(target=out, incomings=[(then_end, then_val), (else_end, else_val)], ty=ty)
            )
            return out
        if isinstance(expr, ast.RangeExpr):
            # Range is parsed/type-checked but not lowered in MVP codegen.
            raise MidoriError(span=expr.span, message="range lowering is not implemented yet")
        if isinstance(expr, ast.PostfixTryExpr):
            raise MidoriError(span=expr.span, message="`?` lowering is not implemented yet")
        if isinstance(expr, ast.MatchExpr):
            raise MidoriError(span=expr.span, message="match lowering is not implemented yet")
        if isinstance(expr, ast.StructInitExpr):
            raise MidoriError(
                span=expr.span, message="struct initialization lowering is not implemented yet"
            )
        if isinstance(expr, ast.UnsafeExpr):
            return self.lower_block(expr.block)
        if isinstance(expr, (ast.SpawnExpr, ast.AwaitExpr)):
            raise MidoriError(span=expr.span, message="concurrency lowering is not implemented yet")
        raise MidoriError(
            span=expr.span, message=f"unsupported expression in lowering: {type(expr).__name__}"
        )

    def lower_stmt(self, stmt: ast.Stmt) -> None:
        if isinstance(stmt, ast.LetStmt):
            value = self.lower_expr(stmt.expr)
            self.env[stmt.name] = value
            return
        if isinstance(stmt, ast.ReturnStmt):
            value = self.lower_expr(stmt.expr) if stmt.expr else None
            self.terminate(ReturnInstr(value=value))
            # Keep lowering in a fresh unreachable block to preserve builder invariants.
            self.current = self.new_block("dead")
            return
        if isinstance(stmt, ast.ExprStmt):
            self.lower_expr(stmt.expr)
            return
        if isinstance(stmt, (ast.BreakStmt, ast.ContinueStmt)):
            raise MidoriError(
                span=stmt.span, message=f"{type(stmt).__name__} lowering is not implemented yet"
            )
        raise MidoriError(
            span=stmt.span, message=f"unsupported statement in lowering: {type(stmt).__name__}"
        )

    def lower_block(self, block: ast.BlockExpr) -> str:
        for stmt in block.statements:
            self.lower_stmt(stmt)
        if block.tail:
            return self.lower_expr(block.tail)
        return ""


def lower_typed_program(typed: TypedProgram) -> ProgramIR:
    functions: dict[str, FunctionIR] = {}
    for name, typed_fn in typed.functions.items():
        builder = _Builder(fn_name=name, expr_types=typed_fn.expr_types)
        for i, param in enumerate(typed_fn.decl.params):
            temp = f"%arg{i}"
            builder.env[param.name] = temp
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
    return ProgramIR(functions=functions)


def is_codegen_supported_type(ty: Type) -> bool:
    return ty in {INT, BOOL, STRING, VOID} or ty.name in {"Int", "Bool", "String", "Float"}
