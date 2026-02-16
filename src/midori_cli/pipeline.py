from __future__ import annotations

import hashlib
import sys
import tempfile
import tomllib
from dataclasses import dataclass
from pathlib import Path

from midori_codegen_llvm.codegen import LLVMCodegen, emit_assembly, link_executable
from midori_compiler import ast
from midori_compiler.errors import MidoriError
from midori_compiler.lexer import Lexer
from midori_compiler.parser import Parser
from midori_compiler.span import Span
from midori_ir.borrow import run_borrow_check
from midori_ir.lowering import lower_typed_program
from midori_ir.mir import ProgramIR
from midori_typecheck.checker import TypedProgram, check_program
from midori_typecheck.resolver import resolve_names

MANIFEST_NAME = "midori.toml"


@dataclass(frozen=True)
class ProjectConfig:
    root: Path
    package_name: str
    package_version: str
    dependencies: dict[str, str]
    entry: Path


@dataclass(frozen=True)
class LoadedProgram:
    program: ast.Program
    entry: Path
    sources: list[Path]
    project: ProjectConfig | None


@dataclass
class CompileResult:
    llvm_ir: str
    asm_path: Path
    exe_path: Path


@dataclass
class CheckResult:
    typed: TypedProgram
    mir: ProgramIR


def _error_at(path: Path, message: str, hint: str | None = None) -> MidoriError:
    return MidoriError(span=Span(str(path), 0, 0, 1, 1), message=message, hint=hint)


def _normalize(path: Path) -> Path:
    return path.expanduser().resolve()


def _safe_relative(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def _find_project_root(start: Path) -> Path | None:
    current = _normalize(start)
    if current.is_file():
        current = current.parent

    while True:
        if (current / MANIFEST_NAME).exists():
            return current
        if current.parent == current:
            return None
        current = current.parent


def _parse_project_config(root: Path) -> ProjectConfig:
    manifest_path = root / MANIFEST_NAME
    try:
        data = tomllib.loads(manifest_path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise _error_at(manifest_path, f"unable to read {MANIFEST_NAME}: {exc}") from exc
    except tomllib.TOMLDecodeError as exc:
        raise _error_at(manifest_path, f"invalid {MANIFEST_NAME}: {exc}") from exc

    package_raw = data.get("package")
    if package_raw is not None and not isinstance(package_raw, dict):
        raise _error_at(manifest_path, "[package] must be a table")
    package_data = package_raw if isinstance(package_raw, dict) else {}

    package_name = str(package_data.get("name", root.name))
    package_version = str(package_data.get("version", "0.1.0"))

    build_raw = data.get("build")
    if build_raw is not None and not isinstance(build_raw, dict):
        raise _error_at(manifest_path, "[build] must be a table")
    build_data = build_raw if isinstance(build_raw, dict) else {}
    entry_value = build_data.get("entry")
    if entry_value is None:
        entry_value = "src/main.mdr" if (root / "src" / "main.mdr").exists() else "main.mdr"
    if not isinstance(entry_value, str):
        raise _error_at(manifest_path, "[build].entry must be a string path")
    entry = _normalize(root / entry_value)
    if not entry.exists():
        raise _error_at(
            manifest_path,
            f"project entry not found: {entry_value}",
            hint="set [build].entry in midori.toml to an existing .mdr file",
        )

    deps_raw = data.get("dependencies")
    if deps_raw is not None and not isinstance(deps_raw, dict):
        raise _error_at(manifest_path, "[dependencies] must be a table")
    dependencies: dict[str, str] = {}
    if isinstance(deps_raw, dict):
        for key in sorted(deps_raw.keys()):
            dependencies[str(key)] = str(deps_raw[key])

    return ProjectConfig(
        root=root,
        package_name=package_name,
        package_version=package_version,
        dependencies=dependencies,
        entry=entry,
    )


def _resolve_entry_and_project(path: Path | None) -> tuple[Path, ProjectConfig | None]:
    if path is None:
        root = _find_project_root(Path.cwd())
        if root is None:
            raise _error_at(
                Path.cwd(),
                f"no source provided and no {MANIFEST_NAME} found",
                hint="pass a .mdr source path or run inside a MIDORI project",
            )
        project = _parse_project_config(root)
        return project.entry, project

    target = path.expanduser()
    if target.exists() and target.is_dir():
        root = _find_project_root(target)
        if root is None:
            raise _error_at(
                target,
                f"directory does not contain {MANIFEST_NAME}",
                hint="create midori.toml or pass a .mdr source path",
            )
        project = _parse_project_config(root)
        return project.entry, project

    entry = _normalize(target)
    if not entry.exists():
        raise _error_at(entry, f"source file not found: {entry}")

    root = _find_project_root(entry)
    project = _parse_project_config(root) if root is not None else None
    return entry, project


def resolve_entry_file(path: Path | None = None) -> Path:
    entry, _project = _resolve_entry_and_project(path)
    return entry


def _resolve_import_path(owner: Path, import_path: str) -> Path:
    target = Path(import_path)
    if target.suffix == "":
        target = target.with_suffix(".mdr")
    if not target.is_absolute():
        target = owner.parent / target
    return _normalize(target)


def _parse_file(path: Path) -> ast.Program:
    source = path.read_text(encoding="utf-8")
    tokens = Lexer(source, str(path)).tokenize()
    return Parser(tokens).parse()


def _load_program(entry: Path) -> tuple[ast.Program, list[Path]]:
    parsed: dict[Path, ast.Program] = {}
    ordered_sources: list[Path] = []
    merged_items: list[ast.Item] = []
    visiting: list[Path] = []

    def visit(path: Path) -> None:
        path = _normalize(path)
        if path in parsed:
            return
        if path in visiting:
            cycle = " -> ".join(p.name for p in [*visiting, path])
            raise _error_at(path, f"import cycle detected: {cycle}")
        if not path.exists():
            raise _error_at(path, f"import file not found: {path}")

        program = _parse_file(path)
        visiting.append(path)
        for item in program.items:
            if isinstance(item, ast.ImportDecl):
                visit(_resolve_import_path(path, item.path))
        visiting.pop()

        parsed[path] = program
        ordered_sources.append(path)
        for item in program.items:
            if not isinstance(item, ast.ImportDecl):
                merged_items.append(item)

    visit(entry)
    if merged_items:
        span = merged_items[0].span
    else:
        span = Span(str(entry), 0, 0, 1, 1)
    return ast.Program(span=span, items=merged_items), ordered_sources


def load_program(path: Path | None = None) -> LoadedProgram:
    entry, project = _resolve_entry_and_project(path)
    program, sources = _load_program(entry)
    return LoadedProgram(program=program, entry=entry, sources=sources, project=project)


def _analyze_file(path: Path | None) -> CheckResult:
    loaded = load_program(path)
    resolution = resolve_names(loaded.program)
    typed = check_program(loaded.program, resolution)
    run_borrow_check(typed)
    mir = lower_typed_program(typed)
    return CheckResult(typed=typed, mir=mir)


def check_file(path: Path | None) -> CheckResult:
    result = _analyze_file(path)
    for warning in result.typed.warnings:
        print(warning, file=sys.stderr)
    return result


def compile_file(
    path: Path | None,
    out_exe: Path,
    *,
    emit_llvm: bool = False,
    emit_asm: bool = False,
) -> CompileResult:
    out_exe.parent.mkdir(parents=True, exist_ok=True)
    checked = _analyze_file(path)
    for warning in checked.typed.warnings:
        print(warning, file=sys.stderr)
    codegen = LLVMCodegen()
    llvm_ir = codegen.emit_module(checked.mir)

    if emit_asm:
        asm_path = out_exe.with_suffix(".s")
        asm_path.parent.mkdir(parents=True, exist_ok=True)
    else:
        with tempfile.NamedTemporaryFile(prefix="midori-", suffix=".s", delete=False) as tmp:
            asm_path = Path(tmp.name)
    emit_assembly(llvm_ir, asm_path)
    link_executable(asm_path, out_exe)
    if emit_llvm:
        out_exe.with_suffix(".ll").write_text(llvm_ir, encoding="utf-8")
    if not emit_asm:
        try:
            asm_path.unlink(missing_ok=True)
        except TypeError:
            if asm_path.exists():
                asm_path.unlink()
    return CompileResult(llvm_ir=llvm_ir, asm_path=asm_path, exe_path=out_exe)


def write_lockfile(path: Path | None = None, *, output: Path | None = None) -> Path:
    loaded = load_program(path)
    root = loaded.project.root if loaded.project is not None else loaded.entry.parent
    package_name = loaded.project.package_name if loaded.project is not None else loaded.entry.stem
    package_version = loaded.project.package_version if loaded.project is not None else "0.1.0"

    sources: list[tuple[str, str]] = []
    for src in loaded.sources:
        rel = _safe_relative(src, root)
        digest = hashlib.sha256(src.read_bytes()).hexdigest()
        sources.append((rel, digest))
    sources.sort(key=lambda row: row[0])

    lock_path = output if output is not None else (root / "midori.lock")
    lock_path = _normalize(lock_path)

    lines: list[str] = [
        "version = 1",
        f'entry = "{_safe_relative(loaded.entry, root)}"',
        "",
        "[package]",
        f'name = "{package_name}"',
        f'version = "{package_version}"',
    ]

    dependencies = loaded.project.dependencies if loaded.project is not None else {}
    if dependencies:
        lines.append("")
        lines.append("[dependencies]")
        for dep_name in sorted(dependencies.keys()):
            lines.append(f'{dep_name} = "{dependencies[dep_name]}"')

    for rel, digest in sources:
        lines.extend(["", "[[sources]]", f'path = "{rel}"', f'sha256 = "{digest}"'])

    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return lock_path
