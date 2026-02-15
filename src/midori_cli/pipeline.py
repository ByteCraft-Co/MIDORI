from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from midori_codegen_llvm.codegen import LLVMCodegen, emit_assembly, link_executable
from midori_compiler.lexer import Lexer
from midori_compiler.parser import Parser
from midori_ir.borrow import run_borrow_check
from midori_ir.lowering import lower_typed_program
from midori_typecheck.checker import check_program
from midori_typecheck.resolver import resolve_names


@dataclass
class CompileResult:
    llvm_ir: str
    object_path: Path
    exe_path: Path


def compile_file(path: Path, out_exe: Path, emit_ir: bool = True) -> CompileResult:
    out_exe.parent.mkdir(parents=True, exist_ok=True)
    source = path.read_text(encoding="utf-8")
    tokens = Lexer(source, str(path)).tokenize()
    program = Parser(tokens).parse()
    resolution = resolve_names(program)
    typed = check_program(program, resolution)
    run_borrow_check(typed)
    mir = lower_typed_program(typed)
    codegen = LLVMCodegen()
    llvm_ir = codegen.emit_module(mir)

    obj = out_exe.with_suffix(".s")
    obj.parent.mkdir(parents=True, exist_ok=True)
    emit_assembly(llvm_ir, obj)
    link_executable(obj, out_exe)
    if emit_ir:
        out_exe.with_suffix(".ll").write_text(llvm_ir, encoding="utf-8")
    return CompileResult(llvm_ir=llvm_ir, object_path=obj, exe_path=out_exe)
