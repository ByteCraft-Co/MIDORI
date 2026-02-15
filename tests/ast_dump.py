from __future__ import annotations

from dataclasses import is_dataclass


def dump_node(node, indent: int = 0) -> str:
    pad = "  " * indent
    if isinstance(node, list):
        return "\n".join(dump_node(x, indent) for x in node)
    if not is_dataclass(node):
        return f"{pad}{node!r}"

    cls = type(node).__name__
    out = [f"{pad}{cls}"]
    for k, v in node.__dict__.items():
        if k == "span":
            continue
        if isinstance(v, (str, int, bool)) or v is None:
            out.append(f"{pad}  {k}={v!r}")
        elif isinstance(v, list):
            out.append(f"{pad}  {k}=[")
            for item in v:
                out.append(dump_node(item, indent + 2))
            out.append(f"{pad}  ]")
        else:
            out.append(f"{pad}  {k}:")
            out.append(dump_node(v, indent + 2))
    return "\n".join(out)
