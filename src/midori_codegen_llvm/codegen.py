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
    EnumConstructInstr,
    EnumFieldInstr,
    EnumLayout,
    EnumTagInstr,
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
        self.enum_layouts: dict[str, EnumLayout] = {}
        self.enum_types: dict[str, ir.Type] = {}

    def emit_module(self, program: ProgramIR) -> str:
        self.enum_layouts = program.enums
        self._declare_enum_types(program.enums)
        self._declare_functions(program)
        for fn in program.functions.values():
            self._emit_function(fn)
        return str(self.module)

    def _declare_runtime(self) -> None:
        i8 = ir.IntType(8)
        i32 = ir.IntType(32)
        i64 = ir.IntType(64)
        i8ptr = i8.as_pointer()
        self.printf = ir.Function(
            self.module, ir.FunctionType(i32, [i8ptr], var_arg=True), name="printf"
        )
        self.puts = ir.Function(self.module, ir.FunctionType(i32, [i8ptr]), name="puts")
        self.malloc = ir.Function(self.module, ir.FunctionType(i8ptr, [i64]), name="malloc")
        self.fopen = ir.Function(self.module, ir.FunctionType(i8ptr, [i8ptr, i8ptr]), name="fopen")
        self.fseek = ir.Function(self.module, ir.FunctionType(i32, [i8ptr, i64, i32]), name="fseek")
        self.ftell = ir.Function(self.module, ir.FunctionType(i64, [i8ptr]), name="ftell")
        self.fread = ir.Function(
            self.module,
            ir.FunctionType(i64, [i8ptr, i64, i64, i8ptr]),
            name="fread",
        )
        self.fclose = ir.Function(self.module, ir.FunctionType(i32, [i8ptr]), name="fclose")
        self.fmt_i64 = self._global_cstr("%lld\n", "fmt_i64")
        self.fmt_f64 = self._global_cstr("%f\n", "fmt_f64")
        self.fmt_char = self._global_cstr("%c\n", "fmt_char")
        self.true_s = self._global_cstr("true", "bool_true")
        self.false_s = self._global_cstr("false", "bool_false")
        self.read_mode = self._global_cstr("rb", "read_mode_rb")
        self.read_err_open = self._global_cstr("read_file open failed", "read_err_open")
        self.read_err_stat = self._global_cstr("read_file stat failed", "read_err_stat")
        self.read_err_alloc = self._global_cstr("read_file alloc failed", "read_err_alloc")

    def _declare_functions(self, program: ProgramIR) -> None:
        for fn in program.functions.values():
            arg_types = [self._ll_type(p[1]) for p in fn.params]
            ret_type = self._ll_ret_type(fn)
            ir_fn = ir.Function(self.module, ir.FunctionType(ret_type, arg_types), name=fn.name)
            self.fn_map[fn.name] = ir_fn

    def _declare_enum_types(self, enums: dict[str, EnumLayout]) -> None:
        i32 = ir.IntType(32)
        i64 = ir.IntType(64)
        for key, layout in enums.items():
            type_name = self._sanitize_enum_name(key)
            enum_ty = self.module.context.get_identified_type(type_name)
            if enum_ty.is_opaque:
                body = [i32]
                body.extend(i64 for _ in range(layout.payload_slots))
                enum_ty.set_body(*body)
            self.enum_types[key] = enum_ty

    def _emit_function(self, fn: FunctionIR) -> None:
        ir_fn = self.fn_map[fn.name]
        ll_blocks = {name: ir_fn.append_basic_block(name=name) for name in fn.blocks}
        for i, (name, _ty) in enumerate(fn.params):
            ir_fn.args[i].name = name

        values: dict[str, ir.Value] = {}
        pending_phi_incomings: list[tuple[ir.instructions.PhiInstr, list[tuple[str, str]]]] = []
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
                    elif instr.name == "read_file":
                        if len(args) != 1:
                            raise RuntimeError("read_file expects one String argument")
                        agg = self._emit_read_file(builder, args[0], instr.ret_ty)
                        if instr.target:
                            values[instr.target] = agg
                    else:
                        call = builder.call(self.fn_map[instr.name], args)
                        if instr.target:
                            values[instr.target] = call
                elif isinstance(instr, EnumConstructInstr):
                    enum_ty = self.enum_types[instr.enum_key]
                    agg = ir.Constant(enum_ty, None)
                    agg = builder.insert_value(
                        agg, ir.Constant(ir.IntType(32), instr.variant_index), 0
                    )
                    for i, field_name in enumerate(instr.fields):
                        encoded = self._encode_payload(
                            builder, values[field_name], instr.field_types[i]
                        )
                        agg = builder.insert_value(agg, encoded, i + 1)
                    values[instr.target] = agg
                elif isinstance(instr, EnumTagInstr):
                    tag_i32 = builder.extract_value(values[instr.source], 0)
                    values[instr.target] = builder.zext(tag_i32, ir.IntType(64))
                elif isinstance(instr, EnumFieldInstr):
                    raw = builder.extract_value(values[instr.source], instr.field_index + 1)
                    values[instr.target] = self._decode_payload(builder, raw, instr.field_ty)
                elif isinstance(instr, PhiInstr):
                    phi = builder.phi(self._ll_type(instr.ty), name=instr.target[1:])
                    values[instr.target] = phi
                    pending_phi_incomings.append((phi, instr.incomings))
                else:
                    raise RuntimeError(f"unsupported instruction {type(instr).__name__}")

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

        # Resolve phi incomings after all blocks/instructions are materialized.
        for phi, incomings in pending_phi_incomings:
            for pred_name, value_name in incomings:
                phi.add_incoming(values[value_name], ll_blocks[pred_name])

    def _ll_ret_type(self, fn: FunctionIR):
        if fn.name == "main":
            return ir.IntType(32)
        return self._ll_type(fn.return_type)

    def _ll_type(self, ty: Type):
        enum_key = _enum_key_for_type(ty)
        if enum_key and enum_key in self.enum_types:
            return self.enum_types[enum_key]
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

    def _encode_payload(self, builder: ir.IRBuilder, value: ir.Value, ty: Type):
        i64 = ir.IntType(64)
        if ty.name == "Int":
            if isinstance(value.type, ir.IntType) and value.type.width == 64:
                return value
            if isinstance(value.type, ir.IntType):
                return builder.sext(value, i64)
        if ty.name == "Bool":
            return builder.zext(value, i64)
        if ty.name == "Char":
            return builder.zext(value, i64)
        if ty.name == "Float":
            return builder.bitcast(value, i64)
        if ty.name == "String":
            return builder.ptrtoint(value, i64)
        if isinstance(value.type, ir.IntType):
            if value.type.width == 64:
                return value
            return builder.sext(value, i64)
        raise RuntimeError(f"unsupported enum payload encode for {ty}")

    def _decode_payload(self, builder: ir.IRBuilder, raw: ir.Value, ty: Type):
        i8 = ir.IntType(8)
        i64 = ir.IntType(64)
        if ty.name == "Int":
            return raw if isinstance(raw.type, ir.IntType) and raw.type.width == 64 else raw
        if ty.name == "Bool":
            return builder.trunc(raw, ir.IntType(1))
        if ty.name == "Char":
            return builder.trunc(raw, i8)
        if ty.name == "Float":
            return builder.bitcast(raw, ir.DoubleType())
        if ty.name == "String":
            return builder.inttoptr(raw, i8.as_pointer())
        enum_key = _enum_key_for_type(ty)
        if enum_key and enum_key in self.enum_types:
            raise RuntimeError(f"unsupported nested enum payload decode for {ty}")
        return builder.trunc(raw, i64)

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
        i32 = ir.IntType(32)
        if ty == INT:
            builder.call(self.printf, [self.fmt_i64, value])
            return
        if ty == FLOAT:
            builder.call(self.printf, [self.fmt_f64, value])
            return
        if ty.name == "Char":
            if isinstance(value.type, ir.IntType) and value.type.width != 32:
                value = builder.zext(value, i32)
            builder.call(self.printf, [self.fmt_char, value])
            return
        if ty == BOOL:
            selected = builder.select(value, self.true_s, self.false_s)
            builder.call(self.puts, [selected])
            return
        if ty == STRING:
            if not isinstance(value.type, ir.PointerType):
                raise RuntimeError("print(String) expects pointer value")
            builder.call(self.puts, [value])
            return
        raise RuntimeError(f"unsupported print type {ty}")

    def _global_cstr(self, text: str, name: str):
        data = bytearray(text.encode("utf-8")) + b"\00"
        ty = ir.ArrayType(ir.IntType(8), len(data))
        global_var = ir.GlobalVariable(self.module, ty, name=name)
        global_var.linkage = "private"
        global_var.global_constant = True
        global_var.initializer = ir.Constant(ty, data)
        zero = ir.Constant(ir.IntType(32), 0)
        return global_var.gep((zero, zero))

    def _sanitize_enum_name(self, key: str) -> str:
        out = []
        for ch in key:
            if ch.isalnum() or ch == "_":
                out.append(ch)
            else:
                out.append("_")
        return "enum_" + "".join(out)

    def _next_string_id(self) -> int:
        out = self._string_counter
        self._string_counter += 1
        return out

    def _infer_value_type(self, value: ir.Value) -> Type:
        t = value.type
        if isinstance(t, ir.IntType) and t.width == 1:
            return BOOL
        if isinstance(t, ir.IntType) and t.width == 8:
            return Type("Char")
        if isinstance(t, ir.IntType):
            return INT
        if isinstance(t, ir.DoubleType):
            return FLOAT
        return STRING

    def _emit_read_file(self, builder: ir.IRBuilder, path_value: ir.Value, ret_ty: Type):
        i8 = ir.IntType(8)
        i32 = ir.IntType(32)
        i64 = ir.IntType(64)
        i8ptr = i8.as_pointer()
        result_ty = self._ll_type(ret_ty)
        if not isinstance(result_ty, ir.BaseStructType):
            raise RuntimeError("read_file return type must lower to enum Result[String, String]")

        result_ptr = builder.alloca(result_ty)
        builder.store(
            self._build_string_result(builder, result_ty, 1, self.read_err_open), result_ptr
        )

        file_handle = builder.call(self.fopen, [path_value, self.read_mode], name="rf_file")
        file_ok = builder.icmp_unsigned("!=", file_handle, ir.Constant(i8ptr, None))

        with builder.if_then(file_ok):
            builder.call(
                self.fseek,
                [file_handle, ir.Constant(i64, 0), ir.Constant(i32, 2)],
                name="rf_seek_end",
            )
            size = builder.call(self.ftell, [file_handle], name="rf_size")
            builder.call(
                self.fseek,
                [file_handle, ir.Constant(i64, 0), ir.Constant(i32, 0)],
                name="rf_seek_set",
            )

            size_ok = builder.icmp_signed(">=", size, ir.Constant(i64, 0))
            with builder.if_else(size_ok) as (size_then, size_else):
                with size_then:
                    size_plus_one = builder.add(size, ir.Constant(i64, 1), name="rf_alloc_size")
                    buffer = builder.call(self.malloc, [size_plus_one], name="rf_buf")
                    buffer_ok = builder.icmp_unsigned("!=", buffer, ir.Constant(i8ptr, None))

                    with builder.if_else(buffer_ok) as (buf_then, buf_else):
                        with buf_then:
                            bytes_read = builder.call(
                                self.fread,
                                [buffer, ir.Constant(i64, 1), size, file_handle],
                                name="rf_bytes",
                            )
                            term_ptr = builder.gep(buffer, [bytes_read], name="rf_term_ptr")
                            builder.store(ir.Constant(i8, 0), term_ptr)
                            builder.store(
                                self._build_string_result(builder, result_ty, 0, buffer), result_ptr
                            )
                        with buf_else:
                            builder.store(
                                self._build_string_result(
                                    builder, result_ty, 1, self.read_err_alloc
                                ),
                                result_ptr,
                            )
                with size_else:
                    builder.store(
                        self._build_string_result(builder, result_ty, 1, self.read_err_stat),
                        result_ptr,
                    )

            builder.call(self.fclose, [file_handle], name="rf_close")

        return builder.load(result_ptr, name="rf_result")

    def _build_string_result(self, builder: ir.IRBuilder, result_ty, tag: int, payload_ptr):
        agg = ir.Constant(result_ty, None)
        agg = builder.insert_value(agg, ir.Constant(ir.IntType(32), tag), 0)
        payload = builder.ptrtoint(payload_ptr, ir.IntType(64))
        return builder.insert_value(agg, payload, 1)


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
