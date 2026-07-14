"""Parser für den CI-VARS-Deklarationsblock (durch Raute deaktiviert).

Syntax in der .gitlab-ci.yml:

    # CI-VARS: NAME1 NAME2 NAME3=default        (einzeilig)   oder
    # CI-VARS:
    #   NAME1   Beschreibung/Hinweis            (Pflicht)
    #   NAME2 = defaultwert                     (optional mit Default)
    # CI-VARS-END
"""

from __future__ import annotations

import re

VAR_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_HEADER_RE = re.compile(r"#\s*CI-VARS\s*:\s*(.*)$", re.I)
_END_RE = re.compile(r"#\s*CI-VARS-END", re.I)
_ENTRY_RE = re.compile(r"#\s*([A-Za-z_][A-Za-z0-9_]*)\s*(=)?\s*(.*)$")


def parse_required_vars(content: str) -> list[dict]:
    out: list[dict] = []
    seen: set[str] = set()
    in_block = False

    def add(name: str, hint: str = "", default: str | None = None) -> None:
        if name.upper() != "CI-VARS" and name not in seen:
            seen.add(name)
            out.append({"name": name, "hint": hint, "default": default})

    for line in content.splitlines():
        stripped = line.strip()
        if in_block:
            if _END_RE.match(stripped) or not stripped.startswith("#"):
                in_block = False
                continue
            m = _ENTRY_RE.match(stripped)
            if not m:
                in_block = False
                continue
            name, is_default, rest = m.group(1), m.group(2) == "=", m.group(3).strip(" -–#")
            add(name, hint="" if is_default else rest,
                default=rest if is_default else None)
            continue
        m = _HEADER_RE.match(stripped)
        if m:
            rest = m.group(1).strip()
            if not rest:
                in_block = True
                continue
            for token in re.split(r"[,\s]+", rest):
                name, _, default = token.partition("=")
                if VAR_NAME_RE.match(name):
                    add(name, default=default if default else None)
    return out
