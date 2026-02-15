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

Parsing works for enum/struct syntax; enum lowering is currently roadmap.

## Option / Result

`Some`, `None`, `Ok`, `Err` constructors are type-checked. The `?` operator is parsed and type-checked for `Result[T, E]`, with lowering planned.

## Borrowing and Moves

MIDORI MVP enforces:
- use-after-move rejection for non-`Copy` values
- no `&mut` when immutable borrows exist
- no immutable borrows when a mutable borrow exists

## Concurrency Syntax

`task`, `spawn`, and `await` parse successfully. Lowering/runtime are intentionally not implemented in MVP yet.
