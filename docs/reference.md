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
- Parametric nominal forms parse: `Option[T]`, `Result[T, E]`
- Borrow/pointer forms parse: `&T`, `&mut T`, `*T`, `*mut T`

## Safety Defaults

- No null literal
- Option/Result-centric flow
- Borrow checker MVP rejects use-after-move and invalid aliasing
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
