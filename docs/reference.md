# MIDORI Reference

## Grammar Sketch

```text
item        := fn_decl | struct_decl | enum_decl | trait_decl | extern_decl
fn_decl     := [pub] [task] "fn" IDENT [generic_params] "(" params ")" ["->" type] block
stmt        := let_stmt | return_stmt | expr_stmt
let_stmt    := ("let"|"var") IDENT ([":" type "=" ] | [":="]) expr
expr        := assignment
assignment  := range_expr [("="|"+="|"-="|"*="|"/="|"%=") assignment]
range_expr  := logic_or [(".."|"..=") logic_or]
```

## Keywords

`fn let var struct enum trait impl pub use module if else match for in while loop break continue return task spawn await unsafe extern`

## Types

- Primitive: `Int`, `Float`, `Bool`, `Char`, `String`
- Parametric nominal forms: `Option[T]`, `Result[T, E]`
- Borrow/pointer forms parse: `&T`, `&mut T`, `*T`, `*mut T`

## Match Support

`match` supports:
- integer literal patterns
- boolean literal patterns
- enum variant patterns (payload and zero-field variants)
- `_` wildcard and name bindings

Exhaustiveness is currently warning-only.

## Result `?` Support

`?` is supported for `Result[T, E]` and lowers to explicit early-return control flow.

Constraints:
- enclosing function must return `Result[_, E]`
- error type must be assignable to the function error type

## Safety Defaults

- No null literal
- Option/Result-centric flow
- Borrow checker (lexical) rejects use-after-move and invalid aliasing
- `unsafe { ... }` syntax supported in parser/type layer

## Diagnostics

Errors carry file/line/col:

```text
file.mdr:line:col: error: message
  hint: optional suggestion
```

## LLVM Contract

IR must satisfy LLVM LangRef semantics:
https://llvm.org/docs/LangRef.html
