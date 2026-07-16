"""Minimal TOML-subset reader — Python 3.9 has no tomllib and the harness is
dependency-free. Supports exactly what absoloop.toml documents: [table] and
[nested.table] headers, string / number / boolean values, flat arrays, and
comments. Anything fancier raises so config errors surface loudly.
"""
from __future__ import annotations

from typing import Any, Dict, List


class TomlError(Exception):
    pass


def loads(text: str) -> Dict[str, Any]:
    root: Dict[str, Any] = {}
    current = root
    for lineno, raw in enumerate(text.splitlines(), 1):
        line = _strip_comment(raw).strip()
        if not line:
            continue
        if line.startswith("["):
            if not line.endswith("]"):
                raise TomlError(f"line {lineno}: malformed table header")
            current = _descend(root, line[1:-1].strip(), lineno)
            continue
        if "=" not in line:
            raise TomlError(f"line {lineno}: expected key = value")
        key, _, value = line.partition("=")
        current[_key(key.strip(), lineno)] = _value(value.strip(), lineno)
    return root


def _strip_comment(line: str) -> str:
    out: List[str] = []
    in_string = False
    for ch in line:
        if ch == '"':
            in_string = not in_string
        if ch == "#" and not in_string:
            break
        out.append(ch)
    return "".join(out)


def _descend(root: Dict[str, Any], dotted: str, lineno: int) -> Dict[str, Any]:
    node = root
    for part in dotted.split("."):
        part = _key(part.strip(), lineno)
        node = node.setdefault(part, {})
        if not isinstance(node, dict):
            raise TomlError(f"line {lineno}: {part!r} is not a table")
    return node


def _key(token: str, lineno: int) -> str:
    if token.startswith('"') and token.endswith('"'):
        return token[1:-1]
    if not token or any(ch.isspace() for ch in token):
        raise TomlError(f"line {lineno}: bad key {token!r}")
    return token


def _value(token: str, lineno: int) -> Any:
    if token.startswith("[") and token.endswith("]"):
        inner = token[1:-1].strip()
        if not inner:
            return []
        return [_value(part.strip(), lineno) for part in _split_array(inner)]
    if token.startswith('"') and token.endswith('"') and len(token) >= 2:
        return token[1:-1].replace('\\"', '"').replace("\\\\", "\\")
    if token in ("true", "false"):
        return token == "true"
    try:
        return int(token)
    except ValueError:
        pass
    try:
        return float(token)
    except ValueError:
        pass
    raise TomlError(f"line {lineno}: unsupported value {token!r}")


def _split_array(inner: str) -> List[str]:
    parts: List[str] = []
    depth = 0
    in_string = False
    current: List[str] = []
    for ch in inner:
        if ch == '"':
            in_string = not in_string
        if not in_string:
            if ch == "[":
                depth += 1
            elif ch == "]":
                depth -= 1
            elif ch == "," and depth == 0:
                parts.append("".join(current))
                current = []
                continue
        current.append(ch)
    if "".join(current).strip():
        parts.append("".join(current))
    return parts
