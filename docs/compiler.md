# MIDORI Compiler Architecture

Pipeline stages:

1. Lexer (`midori_compiler.lexer`)
2. Parser + AST (`midori_compiler.parser`, `midori_compiler.ast`)
3. Name resolution (`midori_typecheck.resolver`)
4. Type checking + local inference (`midori_typecheck.checker`)
5. MIR lowering with explicit basic blocks (`midori_ir.lowering`, `midori_ir.mir`)
6. Borrow checker MVP (`midori_ir.borrow`)
7. LLVM emission (`midori_codegen_llvm.codegen`)
8. Native link (`gcc`) and execution (`midori_cli.pipeline`)

## MIR Shape

- `FunctionIR` stores `BasicBlock`s keyed by label
- instructions include constants, binops, calls, phi nodes
- terminators are explicit (`branch`, `condbranch`, `return`)

This keeps control flow explicit and prepares for future optimizations.

## Codegen Notes

- Runtime calls use `printf`/`puts`
- Int is lowered to `i64` (main return adjusted to `i32` for platform ABI)
- String literals become private global constants

## Extending the Compiler

To add a language feature:
- extend lexer tokenization
- add AST nodes + parser rules
- add type rules
- lower to MIR
- either implement LLVM emission or emit `not implemented` diagnostic
- add unit and integration tests
