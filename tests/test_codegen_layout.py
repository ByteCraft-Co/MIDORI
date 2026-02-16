from __future__ import annotations

import re
from pathlib import Path

from midori_codegen_llvm.codegen import LLVMCodegen
from midori_compiler.parser import Parser
from midori_ir.borrow import run_borrow_check
from midori_ir.lowering import lower_typed_program
from midori_typecheck.checker import check_program
from midori_typecheck.resolver import resolve_names

LAYOUT_SOURCE = """
enum Pair {
  Both(a: Int, b: Bool)
  One(v: Int)
  Empty
}

fn score(p: Pair) -> Int {
  match p {
    Both(x, y) => if y { x } else { 0 },
    One(v) => v,
    Empty => 0,
  }
}

fn may(flag: Bool) -> Result[Int, String] {
  if flag { Ok(10) } else { Err("bad") }
}

fn plus(flag: Bool) -> Result[Int, String] {
  let x := may(flag)?
  Ok(x + 1)
}

fn maybe(flag: Bool) -> Option[Int] {
  if flag { Some(3) } else { None() }
}

fn use_option(flag: Bool) -> Int {
  let v := maybe(flag)
  match v {
    Some(x) => x,
    None => 0,
  }
}

fn main() -> Int {
  let p := Both(4, true)
  print(score(p))
  print(use_option(true))
  print(use_option(false))
  let r := plus(true)
  match r {
    Ok(v) => print(v),
    Err(e) => print(e),
  }
  0
}
"""


def _emit_llvm(source: str, file: str = "layout.mdr") -> str:
    program = Parser.from_source(source, file).parse()
    typed = check_program(program, resolve_names(program))
    run_borrow_check(typed)
    mir = lower_typed_program(typed)
    return LLVMCodegen().emit_module(mir)


def _enum_layout_summary(llvm_ir: str) -> str:
    pattern = re.compile(r'^%"(?P<name>enum_[^"]+)" = type \{(?P<body>[^}]*)\}$', re.MULTILINE)
    rows: list[str] = []
    for match in sorted(pattern.finditer(llvm_ir), key=lambda m: m.group("name")):
        body = ", ".join(part.strip() for part in match.group("body").split(","))
        rows.append(f"{match.group('name')} = {{{body}}}")
    return "\n".join(rows) + "\n"


def _enum_abi_ops_summary(llvm_ir: str) -> str:
    counters: dict[str, int] = {}
    for line in llvm_ir.splitlines():
        text = line.strip()

        tag_set = re.search(r'insertvalue %"(?P<enum>enum_[^"]+)" .*?, i32 (?P<tag>\d+), 0', text)
        if tag_set:
            key = f"tag-set {tag_set.group('enum')} tag={tag_set.group('tag')}"
            counters[key] = counters.get(key, 0) + 1
            continue

        field_set = re.search(
            r'insertvalue %"(?P<enum>enum_[^"]+)" .*?, i64 .*?, (?P<field>\d+)',
            text,
        )
        if field_set:
            key = f"field-set {field_set.group('enum')} field={field_set.group('field')}"
            counters[key] = counters.get(key, 0) + 1
            continue

        field_get = re.search(r'extractvalue %"(?P<enum>enum_[^"]+)" .*?, (?P<field>\d+)', text)
        if field_get:
            key = f"field-get {field_get.group('enum')} field={field_get.group('field')}"
            counters[key] = counters.get(key, 0) + 1

    return "\n".join(f"{k} x{counters[k]}" for k in sorted(counters)) + "\n"


def _function_body(llvm_ir: str, fn_name: str) -> str:
    pattern = re.compile(
        rf'^define .*@"{re.escape(fn_name)}"\([^\n]*\)\n\{{(?P<body>.*?)^\}}',
        re.MULTILINE | re.DOTALL,
    )
    match = pattern.search(llvm_ir)
    if not match:
        raise AssertionError(f"missing function body for {fn_name}")
    return match.group("body")


def test_enum_tagged_union_layout_golden() -> None:
    llvm_ir = _emit_llvm(LAYOUT_SOURCE)
    summary = _enum_layout_summary(llvm_ir)
    golden_path = Path("tests/golden/llvm_enum_layout.txt")
    assert summary == golden_path.read_text(encoding="utf-8")


def test_enum_abi_ops_golden() -> None:
    llvm_ir = _emit_llvm(LAYOUT_SOURCE)
    summary = _enum_abi_ops_summary(llvm_ir)
    golden_path = Path("tests/golden/llvm_enum_abi_ops.txt")
    assert summary == golden_path.read_text(encoding="utf-8")


def test_try_lowering_has_explicit_ok_err_blocks() -> None:
    llvm_ir = _emit_llvm(LAYOUT_SOURCE)
    plus_body = _function_body(llvm_ir, "plus")
    assert re.search(r'br i1 .*label %"try_ok_\d+", label %"try_err_\d+"', plus_body)
    assert re.search(r"try_ok_\d+:", plus_body)
    assert re.search(r"try_err_\d+:", plus_body)
    assert re.search(
        r"try_ok_\d+:.*extractvalue %\"enum_Result_Int__String_\" .*?, 1",
        plus_body,
        re.DOTALL,
    )
    assert re.search(r"try_err_\d+:.*ret %\"enum_Result_Int__String_\" ", plus_body, re.DOTALL)


def test_match_lowering_checks_all_enum_tags() -> None:
    llvm_ir = _emit_llvm(LAYOUT_SOURCE)
    score_body = _function_body(llvm_ir, "score")
    for tag in ("0", "1", "2"):
        assert re.search(rf"icmp eq i64 .*?, {tag}", score_body)
    assert 'extractvalue %"enum_Pair" %"p", 1' in score_body
    assert 'extractvalue %"enum_Pair" %"p", 2' in score_body
