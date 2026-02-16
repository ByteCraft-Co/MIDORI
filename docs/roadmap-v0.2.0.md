# MIDORI v0.2.0 Roadmap (Completed)

Goal: deliver the first cohesive, compiler-first release where control flow, enums, and Result propagation work end-to-end.

## Release Definition

- [x] `match` works end-to-end (parse -> typecheck -> MIR -> LLVM -> run)
- [x] `?` works end-to-end for `Result[T, E]` with early return
- [x] enums are lowered as tagged unions in LLVM codegen
- [x] borrow checker catches common ownership errors with actionable diagnostics
- [x] runtime primitives are usable for small programs (`print`, `read_file` Result stub, enum/Result values)
- [x] tooling/docs are stable for external contributors

## Scope Delivery

### Control Flow
- [x] `match` lowering for integer literals
- [x] `match` lowering for boolean literals
- [x] `match` lowering for enum variant patterns
- [x] non-exhaustive `match` surfaced as warning

### Result Flow (`?`)
- [x] MIR lowering emits explicit early-return blocks
- [x] LLVM lowering preserves control-flow correctness with block dominance
- [x] `?` constrained to `Result[T, E]` and `Result`-returning functions

### Enums
- [x] explicit discriminant + payload slot layout in LLVM
- [x] enum constructors lowered consistently through MIR/codegen
- [x] ABI instability documented

### Type System
- [x] generics parsing retained
- [x] minimal generic call-site substitution (traitless MVP)
- [x] no advanced inference beyond local/contextual coercion

### Borrow Checker v2 (Lexical)
- [x] nested-scope use-after-move detection
- [x] branch-aware state merge for `if`/`match`
- [x] diagnostics-first behavior

### Runtime
- [x] `read_file(path)` shape implemented as `Result[String, String]` runtime stub
- [ ] full `Vec` allocation/append/index runtime (deferred)

### Tooling
- [x] `midori build --emit-llvm`
- [x] `midori build --emit-asm`
- [x] deterministic LLVM/ASM output tests for same source/toolchain
- [x] formatter idempotence preserved

## Non-Goals (Deferred)

- full trait solving
- async runtime / executor
- package manager / registry
- advanced LLVM optimizations
- stable ABI guarantee

## Verification Targets

- [x] `examples/match_enum.mdr` compile+run success
- [x] `examples/option_result.mdr` exercises `?` success and error paths
- [x] 5+ new compile-run integration tests
- [x] 10+ new diagnostics tests
- [x] `py -m pytest -q` green
- [x] docs updated for supported match patterns and known limitations
- [x] deterministic `--emit-llvm` / `--emit-asm` outputs validated
