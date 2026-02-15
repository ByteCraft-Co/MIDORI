# Agent Guide

## Commands
- Install: `python -m pip install -e .[dev]`
- Run tests: `pytest -q`
- Format/lint: `python -m ruff format . && python -m ruff check .`
- Run compiler tests via CLI: `midori test`

## Repo Map
- `src/midori_cli`: command-line interface (`build`, `run`, `test`, `fmt`, `repl`)
- `src/midori_compiler`: lexer, parser, AST, diagnostics
- `src/midori_typecheck`: name resolution, type checking, inference
- `src/midori_ir`: typed MIR and lowering from AST
- `src/midori_codegen_llvm`: LLVM IR emission and object/executable pipeline
- `src/midori_std`: Midori standard library stubs
- `tests`: unit, golden, type, and integration tests
- `docs`: language and architecture docs

## Adding Syntax Features
1. Add/adjust token in `src/midori_compiler/token.py`.
2. Extend lexing rules in `src/midori_compiler/lexer.py`.
3. Update AST nodes in `src/midori_compiler/ast.py` if needed.
4. Extend parser in `src/midori_compiler/parser.py`.
5. Update resolver/typechecker if semantics changed.
6. Add MIR lowering and codegen support or emit a clear diagnostic.
7. Add lexer/parser/type/integration tests.

## Conventions
- Keep diagnostics actionable with `file:line:col` and short hints.
- Preserve deterministic formatting output from `midori fmt`.
- Prefer explicit spans on all AST nodes.
- Keep feature work behind passing tests.
