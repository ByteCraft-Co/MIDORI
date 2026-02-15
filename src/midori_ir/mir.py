from __future__ import annotations

from dataclasses import dataclass, field

from midori_typecheck.types import Type


@dataclass
class Instr:
    pass


@dataclass
class ConstInstr(Instr):
    target: str
    value: str
    ty: Type


@dataclass
class AliasInstr(Instr):
    target: str
    source: str


@dataclass
class BinOpInstr(Instr):
    target: str
    op: str
    left: str
    right: str
    ty: Type


@dataclass
class CallInstr(Instr):
    target: str | None
    name: str
    args: list[str]
    ret_ty: Type


@dataclass
class PhiInstr(Instr):
    target: str
    incomings: list[tuple[str, str]]
    ty: Type


@dataclass
class BranchInstr(Instr):
    target: str


@dataclass
class CondBranchInstr(Instr):
    cond: str
    then_bb: str
    else_bb: str


@dataclass
class ReturnInstr(Instr):
    value: str | None


@dataclass
class BasicBlock:
    name: str
    instructions: list[Instr] = field(default_factory=list)
    terminator: Instr | None = None


@dataclass
class FunctionIR:
    name: str
    params: list[tuple[str, Type]]
    return_type: Type
    blocks: dict[str, BasicBlock]
    entry: str


@dataclass
class ProgramIR:
    functions: dict[str, FunctionIR]
