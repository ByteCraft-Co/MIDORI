# Midori

MIDORI is an experimental, safe-by-default language with an LLVM-backed compiler pipeline implemented in Python (`llvmlite`).

## Website

- Docs/Web: https://midori-docs.vercel.app/


## Requirements

- Python 3.11+
- `gcc` on PATH (used for final executable linking)

## Install

```bash
py -m pip install -e .[dev]
```

This installs both CLI entry points:

- `midori`
- `midori-terminal`

## CLI Quick Start

```bash
midori --version
midori build examples/hello.mdr -o hello.exe
midori build examples/hello.mdr -o hello.exe --emit-llvm --emit-asm
midori run examples/hello.mdr
midori check examples/hello.mdr
midori fmt examples/hello.mdr
midori lock examples/hello.mdr
midori test
midori new my_app
midori repl
```

`--emit-llvm` writes a `.ll` file and `--emit-asm` writes a `.s` file next to the output executable.

If `midori` is not on PATH, use `py -m midori_cli.main ...`.

## Project Mode (`midori.toml` + imports + lockfile)

You can run `check`, `run`, `build`, and `lock` without a source argument when `midori.toml` exists in the current project.

`midori.toml`:

```toml
[package]
name = "demo"
version = "0.1.0"

[build]
entry = "src/main.mdr"
```

`src/main.mdr`:

```midori
import "./math.mdr"

fn main() -> Int {
  print(plus_one(41))
  0
}
```

`src/math.mdr`:

```midori
fn plus_one(v: Int) -> Int {
  v + 1
}
```

Run:

```bash
midori check
midori run
midori lock
```

`midori lock` writes a deterministic `midori.lock` including source file hashes.

## MIDORI Terminal

Launch:

```bash
midori-terminal
```

Terminal supports:

- Expression evaluation (`1 + 2`, `fib(10)`, etc.)
- Session declarations (`import`, `error`, `fn`, `struct`, `enum`, `trait`, `extern`)
- Multiline declaration input with continuation prompt (`...>`)
- Commands like `:run`, `:check`, `:build`, `:fmt`, `:new`, `:test`, `:cd`, `:reset`, `:cancel`, `:quit`
- Shell passthrough with `:shell <command>` or `!<command>`

## Hello World

```midori
fn main() -> Int {
  print("hello from midori")
  0
}
```

## Implemented Language Surface

- Lexer with source spans and diagnostics
- Parser for functions, structs, enums, traits, extern declarations, `if`, `match`, ranges, borrow syntax (`&`, `&mut`), and `?`
- Top-level file imports with cycle detection
- Name resolution and duplicate checks
- Type checking with local inference for `:=`
- Option/Result constructor typing (`Some/None/Ok/Err`) and `?` early-return lowering
- Custom error declarations (`error Name`) and explicit raising (`raise Name("message")`)
- Exhaustive `match` checking for implemented pattern shapes
- MIR lowering with explicit basic blocks and phi nodes
- Borrow checker v2 (lexical + branch-aware merge checks)
- LLVM codegen for core scalar/string operations, control flow, recursion, and enum payload extraction
- Runtime `read_file(path: String) -> Result[String, String]`

## Current Limitations

- Trait bounds and full trait solving are not implemented
- Generics use minimal call-site substitution (no stable ABI guarantees)
- Async runtime (`spawn`/`await`) and full `Vec` runtime are pending
- Enum payload fields currently support `Int`, `Float`, `Bool`, `Char`, and `String`
- Nested enum payloads (for example `Option[Option[Int]]`) are not lowered in codegen yet
- `raise` currently targets `Result[T, String]` flows with string-literal payloads
- Extern parsing exists; safe extern pointer codegen is still incomplete
- Dependency registry commands (`midori add/remove/update`) are not implemented yet

## Development

```bash
python -m ruff format .
python -m ruff check .
pytest -q
midori test
```

See `AGENTS.md` for contributor conventions and feature workflow.
Branch/release guidance: `docs/BRANCHING.md`.
Repository layout guide: `docs/PROJECT_STRUCTURE.md`.

## Legal

- License: `LICENSE`
- Legal overview: `LEGAL.md`
- Terms of use: `TERMS-OF-USE.md`
- Privacy: `PRIVACY.md`
- Trademark policy: `TRADEMARKS.md`

## VS Code

The experimental extension lives in `vscode-extension/`.

- README: `vscode-extension/README.md`
- Manifest: `vscode-extension/package.json`
- Language server: `vscode-extension/src/server.js`
