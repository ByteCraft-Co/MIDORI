# MIDORI Language Tour

## Basics

```midori
fn main() -> Int {
  let score := 96
  let label = if score > 90 { "A" } else { "B" }
  print(label)
  0
}
```

## Variables

- `let x: Int = 10` declares immutable bindings.
- `var y := 20` declares mutable bindings with inferred type.

## Functions

```midori
fn add(a: Int, b: Int) -> Int {
  a + b
}
```

The last expression in a block is an implicit return.

## Structs and Enums

```midori
struct Point { x: Int y: Int }
enum Token { Int(value: Int) Plus }
```

Enums are lowered as tagged unions in LLVM IR.

```midori
fn value(t: Token) -> Int {
  match t {
    Int(v) => v,
    Plus => 0,
  }
}
```

## Option / Result

`Some`, `None`, `Ok`, and `Err` are constructor forms for `Option`/`Result`.

`?` is implemented for `Result[T, E]` with early-return semantics:

```midori
fn compute(flag: Bool) -> Result[Int, String] {
  let v := may_fail(flag)?
  Ok(v + 1)
}
```

## Borrowing and Moves

MIDORI MVP enforces:
- use-after-move rejection for non-`Copy` values
- no `&mut` when immutable borrows exist
- no immutable borrows when a mutable borrow exists
- branch-aware move state merging after `if`/`match`

## Concurrency Syntax

`task`, `spawn`, and `await` parse successfully. Lowering/runtime are intentionally not implemented in MVP yet.
