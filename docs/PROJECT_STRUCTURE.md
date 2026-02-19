# Project Structure

MIDORI is organized by compiler pipeline stage plus tooling surfaces.

## Core Compiler

- `src/midori_compiler`: lexer, parser, AST, diagnostics.
- `src/midori_typecheck`: name resolution, type checking, inference.
- `src/midori_ir`: MIR model + lowering + borrow checks.
- `src/midori_codegen_llvm`: LLVM IR/codegen/link pipeline.
- `src/midori_std`: standard-library stubs and modules.

## Tooling

- `src/midori_cli`: CLI commands (`build`, `run`, `check`, `test`, `fmt`, `new`, `repl`).
- `vscode-extension`: VS Code language extension + language server.
- `installer/windows`: Inno Setup specs and installer build scripts.

## Quality Gates

- `tests`: unit and integration tests.
- `.github/workflows/ci.yml`: Python + extension validation gates.

## Docs And Policy

- `README.md`: usage and current feature surface.
- `docs/BRANCHING.md`: branch/release hygiene model.
- `AGENTS.md`: contributor workflow and conventions.
