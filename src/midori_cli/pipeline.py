from __future__ import annotations

import sys
import tempfile
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
    asm_path: Path
    exe_path: Path


def compile_file(
    path: Path,
    out_exe: Path,
    *,
    emit_llvm: bool = False,
    emit_asm: bool = False,
) -> CompileResult:
    out_exe.parent.mkdir(parents=True, exist_ok=True)
    source = path.read_text(encoding="utf-8")
    tokens = Lexer(source, str(path)).tokenize()
    program = Parser(tokens).parse()
    resolution = resolve_names(program)
    typed = check_program(program, resolution)
    for warning in typed.warnings:
        print(warning, file=sys.stderr)
    run_borrow_check(typed)
    mir = lower_typed_program(typed)
    codegen = LLVMCodegen()
    llvm_ir = codegen.emit_module(mir)

    if emit_asm:
        asm_path = out_exe.with_suffix(".s")
        asm_path.parent.mkdir(parents=True, exist_ok=True)
    else:
        with tempfile.NamedTemporaryFile(prefix="midori-", suffix=".s", delete=False) as tmp:
            asm_path = Path(tmp.name)
    emit_assembly(llvm_ir, asm_path)
    link_executable(asm_path, out_exe)
    if emit_llvm:
        out_exe.with_suffix(".ll").write_text(llvm_ir, encoding="utf-8")
    if not emit_asm:
        try:
            asm_path.unlink(missing_ok=True)
        except TypeError:
            if asm_path.exists():
                asm_path.unlink()
    return CompileResult(llvm_ir=llvm_ir, asm_path=asm_path, exe_path=out_exe)
