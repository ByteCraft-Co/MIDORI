from __future__ import annotations


def format_source(source: str) -> str:
    lines = []
    indent = 0
    for raw in source.splitlines():
        stripped = raw.strip()
        if not stripped:
            lines.append("")
            continue
        if stripped.startswith("}"):
            indent = max(indent - 1, 0)
        lines.append(("  " * indent) + stripped)
        if stripped.endswith("{"):
            indent += 1
    return "\n".join(lines) + ("\n" if source.endswith("\n") else "")
