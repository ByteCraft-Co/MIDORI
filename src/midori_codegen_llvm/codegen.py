from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

from llvmlite import binding as llvm
from llvmlite import ir

from midori_ir.mir import (
    AliasInstr,
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
from midori_typecheck.types import BOOL, FLOAT, INT, STRING, Type


@dataclass
class BuildArtifacts:
    llvm_ir: str
    object_path: Path
    exe_path: Path


class LLVMCodegen:
    def __init__(self) -> None:
        self.module = ir.Module(name="midori")
        self._string_counter = 0
        self._declare_runtime()
        self.fn_map: dict[str, ir.Function] = {}

    def emit_module(self, program: ProgramIR) -> str:
        self._declare_functions(program)
        for fn in program.functions.values():
            self._emit_function(fn)
        return str(self.module)

    def _declare_runtime(self) -> None:
        i8 = ir.IntType(8)
        i32 = ir.IntType(32)
        i8ptr = i8.as_pointer()
        self.printf = ir.Function(
            self.module, ir.FunctionType(i32, [i8ptr], var_arg=True), name="printf"
        )
        self.puts = ir.Function(self.module, ir.FunctionType(i32, [i8ptr]), name="puts")
        self.fmt_i64 = self._global_cstr("%lld\n", "fmt_i64")
        self.fmt_f64 = self._global_cstr("%f\n", "fmt_f64")
        self.true_s = self._global_cstr("true", "bool_true")
        self.false_s = self._global_cstr("false", "bool_false")

    def _declare_functions(self, program: ProgramIR) -> None:
        for fn in program.functions.values():
            arg_types = [self._ll_type(p[1]) for p in fn.params]
            ret_type = self._ll_ret_type(fn)
            ir_fn = ir.Function(self.module, ir.FunctionType(ret_type, arg_types), name=fn.name)
            self.fn_map[fn.name] = ir_fn

    def _emit_function(self, fn: FunctionIR) -> None:
        ir_fn = self.fn_map[fn.name]
        ll_blocks = {name: ir_fn.append_basic_block(name=name) for name in fn.blocks}
        for i, (name, _ty) in enumerate(fn.params):
            ir_fn.args[i].name = name

        values: dict[str, ir.Value] = {}
        for i, (_name, _ty) in enumerate(fn.params):
            values[f"%arg{i}"] = ir_fn.args[i]

        for bb_name, bb in fn.blocks.items():
            builder = ir.IRBuilder(ll_blocks[bb_name])
            for instr in bb.instructions:
                if isinstance(instr, ConstInstr):
                    values[instr.target] = self._const_from_literal(instr.value, instr.ty)
                elif isinstance(instr, AliasInstr):
                    values[instr.target] = values[instr.source]
                elif isinstance(instr, BinOpInstr):
                    left = values[instr.left]
                    right = values[instr.right]
                    values[instr.target] = self._emit_binop(
                        builder, instr.op, left, right, instr.ty
                    )
                elif isinstance(instr, CallInstr):
                    args = [values[x] for x in instr.args]
                    if instr.name == "print":
                        self._emit_print(builder, args[0], self._infer_value_type(args[0]))
                        if instr.target:
                            values[instr.target] = ir.Constant(self._ll_type(instr.ret_ty), None)
                    else:
                        call = builder.call(self.fn_map[instr.name], args)
                        if instr.target:
                            values[instr.target] = call
                elif isinstance(instr, PhiInstr):
                    phi = builder.phi(self._ll_type(instr.ty), name=instr.target[1:])
                    values[instr.target] = phi
                else:
                    raise RuntimeError(f"unsupported instruction {type(instr).__name__}")

            # Resolve phi incomings in a second pass per block.
            for instr in bb.instructions:
                if isinstance(instr, PhiInstr):
                    phi = values[instr.target]
                    for pred_name, value_name in instr.incomings:
                        if value_name:
                            phi.add_incoming(values[value_name], ll_blocks[pred_name])

            term = bb.terminator
            if isinstance(term, BranchInstr):
                builder.branch(ll_blocks[term.target])
            elif isinstance(term, CondBranchInstr):
                builder.cbranch(values[term.cond], ll_blocks[term.then_bb], ll_blocks[term.else_bb])
            elif isinstance(term, ReturnInstr):
                if term.value is None:
                    builder.ret_void()
                else:
                    val = values[term.value]
                    if fn.name == "main":
                        if isinstance(val.type, ir.IntType) and val.type.width != 32:
                            val = builder.trunc(val, ir.IntType(32))
                        builder.ret(val)
                    else:
                        builder.ret(val)
            else:
                builder.unreachable()

    def _ll_ret_type(self, fn: FunctionIR):
        if fn.name == "main":
            return ir.IntType(32)
        return self._ll_type(fn.return_type)

    def _ll_type(self, ty: Type):
        if ty.name == "Int":
            return ir.IntType(64)
        if ty.name == "Bool":
            return ir.IntType(1)
        if ty.name == "Char":
            return ir.IntType(8)
        if ty.name == "Float":
            return ir.DoubleType()
        if ty.name == "String":
            return ir.IntType(8).as_pointer()
        if ty.name == "Void":
            return ir.VoidType()
        return ir.IntType(64)

    def _const_from_literal(self, value: str, ty: Type):
        if ty == INT:
            return ir.Constant(ir.IntType(64), int(value))
        if ty == FLOAT:
            return ir.Constant(ir.DoubleType(), float(value))
        if ty == BOOL:
            return ir.Constant(ir.IntType(1), 1 if value == "true" else 0)
        if ty.name == "Char":
            v = value[1:-1]
            if v.startswith("\\"):
                ch = bytes(v, "utf-8").decode("unicode_escape")
            else:
                ch = v
            return ir.Constant(ir.IntType(8), ord(ch[0]))
        if ty == STRING:
            payload = value[1:-1].encode("utf-8").decode("unicode_escape")
            return self._global_cstr(payload, f"str_{self._next_string_id()}")
        return ir.Constant(self._ll_type(ty), 0)

    def _emit_binop(self, builder: ir.IRBuilder, op: str, left, right, ty: Type):
        is_float = isinstance(left.type, ir.DoubleType)
        if op == "+":
            return builder.fadd(left, right) if is_float else builder.add(left, right)
        if op == "-":
            return builder.fsub(left, right) if is_float else builder.sub(left, right)
        if op == "*":
            return builder.fmul(left, right) if is_float else builder.mul(left, right)
        if op == "/":
            return builder.fdiv(left, right) if is_float else builder.sdiv(left, right)
        if op == "%":
            return builder.frem(left, right) if is_float else builder.srem(left, right)
        if op == "==":
            return (
                builder.fcmp_ordered("==", left, right)
                if is_float
                else builder.icmp_signed("==", left, right)
            )
        if op == "!=":
            return (
                builder.fcmp_ordered("!=", left, right)
                if is_float
                else builder.icmp_signed("!=", left, right)
            )
        if op == "<":
            return (
                builder.fcmp_ordered("<", left, right)
                if is_float
                else builder.icmp_signed("<", left, right)
            )
        if op == "<=":
            return (
                builder.fcmp_ordered("<=", left, right)
                if is_float
                else builder.icmp_signed("<=", left, right)
            )
        if op == ">":
            return (
                builder.fcmp_ordered(">", left, right)
                if is_float
                else builder.icmp_signed(">", left, right)
            )
        if op == ">=":
            return (
                builder.fcmp_ordered(">=", left, right)
                if is_float
                else builder.icmp_signed(">=", left, right)
            )
        if op == "&&":
            return builder.and_(left, right)
        if op == "||":
            return builder.or_(left, right)
        if op == "^":
            return builder.xor(left, right)
        raise RuntimeError(f"unsupported op {op} for type {ty}")

    def _emit_print(self, builder: ir.IRBuilder, value: ir.Value, ty: Type) -> None:
        if ty == INT:
            builder.call(self.printf, [self.fmt_i64, value])
            return
        if ty == FLOAT:
            builder.call(self.printf, [self.fmt_f64, value])
            return
        if ty == BOOL:
            selected = builder.select(value, self.true_s, self.false_s)
            builder.call(self.puts, [selected])
            return
        builder.call(self.puts, [value])

    def _global_cstr(self, text: str, name: str):
        data = bytearray(text.encode("utf-8")) + b"\00"
        ty = ir.ArrayType(ir.IntType(8), len(data))
        global_var = ir.GlobalVariable(self.module, ty, name=name)
        global_var.linkage = "private"
        global_var.global_constant = True
        global_var.initializer = ir.Constant(ty, data)
        zero = ir.Constant(ir.IntType(32), 0)
        return global_var.gep((zero, zero))

    def _next_string_id(self) -> int:
        out = self._string_counter
        self._string_counter += 1
        return out

    def _infer_value_type(self, value: ir.Value) -> Type:
        t = value.type
        if isinstance(t, ir.IntType) and t.width == 1:
            return BOOL
        if isinstance(t, ir.IntType):
            return INT
        if isinstance(t, ir.DoubleType):
            return FLOAT
        return STRING


def emit_object(llvm_ir: str, output_obj: Path) -> None:
    llvm.initialize_native_target()
    llvm.initialize_native_asmprinter()
    mod = llvm.parse_assembly(llvm_ir)
    mod.verify()
    triple = _llvm_link_triple()
    mod.triple = triple
    target = llvm.Target.from_triple(triple)
    target_machine = target.create_target_machine(reloc="static", codemodel="small")
    obj = target_machine.emit_object(mod)
    output_obj.write_bytes(obj)


def emit_assembly(llvm_ir: str, output_asm: Path) -> None:
    llvm.initialize_native_target()
    llvm.initialize_native_asmprinter()
    mod = llvm.parse_assembly(llvm_ir)
    mod.verify()
    triple = _llvm_link_triple()
    mod.triple = triple
    target = llvm.Target.from_triple(triple)
    target_machine = target.create_target_machine(reloc="pic", codemodel="small")
    asm = target_machine.emit_assembly(mod)
    output_asm.write_text(asm, encoding="utf-8")


def link_executable(object_or_asm_path: Path, output_exe: Path) -> None:
    output_exe.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["gcc", str(object_or_asm_path), "-o", str(output_exe)], check=True)


def _llvm_link_triple() -> str:
    try:
        machine = subprocess.check_output(["gcc", "-dumpmachine"], text=True).strip()
    except Exception:
        return llvm.get_default_triple()
    if "mingw" in machine or "w64" in machine:
        return "x86_64-w64-windows-gnu"
    return llvm.get_default_triple()
