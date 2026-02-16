from __future__ import annotations

from dataclasses import dataclass, field

from midori_compiler.span import Span


@dataclass
class Node:
    span: Span


@dataclass
class TypeRef(Node):
    name: str
    args: list[TypeRef] = field(default_factory=list)
    is_ref: bool = False
    is_mut_ref: bool = False
    is_ptr: bool = False
    is_mut_ptr: bool = False


@dataclass
class Program(Node):
    items: list[Item]


@dataclass
class Param(Node):
    name: str
    ty: TypeRef


@dataclass
class FunctionDecl(Node):
    name: str
    generic_params: list[str]
    params: list[Param]
    return_type: TypeRef | None
    body: BlockExpr
    is_task: bool = False
    is_pub: bool = False


@dataclass
class ExternFunctionDecl(Node):
    abi: str
    name: str
    params: list[Param]
    return_type: TypeRef | None


@dataclass
class StructField(Node):
    name: str
    ty: TypeRef


@dataclass
class StructDecl(Node):
    name: str
    fields: list[StructField]


@dataclass
class EnumVariant(Node):
    name: str
    fields: list[StructField]


@dataclass
class EnumDecl(Node):
    name: str
    variants: list[EnumVariant]


@dataclass
class FunctionSig(Node):
    name: str
    generic_params: list[str]
    params: list[Param]
    return_type: TypeRef | None


@dataclass
class TraitDecl(Node):
    name: str
    methods: list[FunctionSig]


@dataclass
class ErrorDecl(Node):
    name: str


Item = FunctionDecl | ExternFunctionDecl | StructDecl | EnumDecl | TraitDecl | ErrorDecl


@dataclass
class Stmt(Node):
    pass


@dataclass
class LetStmt(Stmt):
    name: str
    ty: TypeRef | None
    expr: Expr
    mutable: bool
    inferred: bool


@dataclass
class ReturnStmt(Stmt):
    expr: Expr | None


@dataclass
class BreakStmt(Stmt):
    expr: Expr | None


@dataclass
class ContinueStmt(Stmt):
    pass


@dataclass
class ExprStmt(Stmt):
    expr: Expr


@dataclass
class Expr(Node):
    pass


@dataclass
class IdentifierExpr(Expr):
    name: str


@dataclass
class LiteralExpr(Expr):
    value: str
    kind: str


@dataclass
class UnaryExpr(Expr):
    op: str
    expr: Expr


@dataclass
class BinaryExpr(Expr):
    left: Expr
    op: str
    right: Expr


@dataclass
class CallExpr(Expr):
    callee: Expr
    args: list[Expr]


@dataclass
class AssignExpr(Expr):
    target: Expr
    op: str
    value: Expr


@dataclass
class IfExpr(Expr):
    condition: Expr
    then_block: BlockExpr
    else_branch: Expr | None


@dataclass
class MatchArm(Node):
    pattern: Pattern
    expr: Expr


@dataclass
class MatchExpr(Expr):
    expr: Expr
    arms: list[MatchArm]


@dataclass
class FieldInit(Node):
    name: str
    expr: Expr


@dataclass
class StructInitExpr(Expr):
    name: str
    fields: list[FieldInit]


@dataclass
class BlockExpr(Expr):
    statements: list[Stmt]
    tail: Expr | None


@dataclass
class RangeExpr(Expr):
    start: Expr
    end: Expr
    inclusive: bool


@dataclass
class PostfixTryExpr(Expr):
    expr: Expr


@dataclass
class UnsafeExpr(Expr):
    block: BlockExpr


@dataclass
class SpawnExpr(Expr):
    expr: Expr


@dataclass
class AwaitExpr(Expr):
    expr: Expr


@dataclass
class RaiseExpr(Expr):
    kind: str
    message: Expr


@dataclass
class Pattern(Node):
    pass


@dataclass
class WildcardPattern(Pattern):
    pass


@dataclass
class NamePattern(Pattern):
    name: str


@dataclass
class LiteralPattern(Pattern):
    value: str


@dataclass
class VariantPattern(Pattern):
    name: str
    fields: list[str]
