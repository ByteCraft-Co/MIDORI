# Midori

MIDORI is a safe-by-default language with an LLVM-backed compiler pipeline implemented in Python (`llvmlite`).

## Website

- Docs/Web: https://midori-docs.vercel.app/

## Stack Decision

This repository uses **Python + llvmlite** because this environment does not provide Rust/clang toolchains. `llvmlite` gives fast LLVM IR generation and verification with a small setup footprint.

## Install

```bash
py -m pip install -e .[dev]
```

## CLI

```bash
py -m midori_cli.main build examples/hello.mdr -o hello.exe
py -m midori_cli.main build examples/hello.mdr -o hello.exe --emit-llvm --emit-asm
py -m midori_cli.main run examples/hello.mdr
py -m midori_cli.main test
py -m midori_cli.main fmt examples/hello.mdr
py -m midori_cli.main repl
```

If `midori` is on PATH, the same commands work as `midori ...`.

## Hello World

```midori
fn main() -> Int {
  print("hello from midori")
  0
}
```

## LLVM Notes

- Emitted IR is validated via `llvmlite.binding.parse_assembly(...).verify()`.
- LangRef reference: https://llvm.org/docs/LangRef.html
- `build` also writes a `.ll` file next to the executable.

## Supported MIDORI Subset

- Lexer with spans and diagnostics
- Parser for functions, structs, enums, traits, extern declarations, if/match expressions, ranges, borrow syntax (`&`, `&mut`), and `?`
- Name resolution and duplicate checks
- Type checking and local inference for `:=`
- Option/Result constructor typing (`Some/None/Ok/Err`) and `?` early-return lowering
- Enum lowering with tagged-union representation (`tag + payload slots`)
- `match` lowering for integer literals, boolean literals, and enum variants
- MIR lowering with explicit basic blocks, conditional branches, and phi nodes
- Borrow checker v2 (lexical): nested use-after-move and branch-aware merge checks
- LLVM codegen for Int/Float/Bool/String operations, calls, if/match lowering, recursion, and enum payload extraction
- Native executable build via LLVM assembly + `gcc` link

## Current Limitations

- Trait bounds and full trait solving are not implemented.
- Generics use a minimal call-site substitution model (no stable ABI and no cross-module specialization guarantees).
- `match` exhaustiveness is warning-only.
- Async runtime (`spawn`/`await`) and full Vec runtime are still pending.
- `read_file` currently returns a structured `Err` stub in codegen.
- FFI syntax parses; safe codegen for extern pointers is pending.

## Development

```bash
py -m ruff format .
py -m ruff check .
py -m pytest -q
```

See `AGENTS.md` for contributor conventions and feature workflow.

## VS Code Extension Scaffold (Not Published)

A local extension scaffold is available in `vscode-extension/` and is intentionally not released yet.

- Extension manifest: `vscode-extension/package.json`
- Grammar: `vscode-extension/syntaxes/midori.tmLanguage.json`
- Snippets: `vscode-extension/snippets/midori.json`
- Placeholder logo: `vscode-extension/assets/midori-logo.png`

To test locally:
1. Open `vscode-extension/` in VS Code.
2. Press `F5` to run Extension Development Host.
3. Open a `.mdr` file and verify syntax highlighting/snippets.
