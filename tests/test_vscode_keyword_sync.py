from __future__ import annotations

import json
import re
from pathlib import Path

from midori_compiler.token import KEYWORDS as COMPILER_KEYWORDS

ROOT = Path(__file__).resolve().parents[1]
KEYWORD_JSON_PATH = ROOT / "vscode-extension" / "src" / "lsp" / "data" / "compiler-keywords.json"
GRAMMAR_PATH = ROOT / "vscode-extension" / "syntaxes" / "midori.tmLanguage.json"


def _load_json_keywords() -> list[str]:
    payload = json.loads(KEYWORD_JSON_PATH.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    keywords = payload.get("keywords")
    assert isinstance(keywords, list)
    return [str(item) for item in keywords]


def test_vscode_keyword_json_matches_compiler_lexer_keywords() -> None:
    expected = sorted(COMPILER_KEYWORDS.keys())
    actual = sorted(_load_json_keywords())
    assert actual == expected


def test_vscode_grammar_covers_all_canonical_keywords() -> None:
    grammar = json.loads(GRAMMAR_PATH.read_text(encoding="utf-8"))
    assert isinstance(grammar, dict)

    repository = grammar.get("repository", {})
    assert isinstance(repository, dict)

    keywords_repo = repository.get("keywords", {})
    assert isinstance(keywords_repo, dict)

    patterns = keywords_repo.get("patterns", [])
    assert isinstance(patterns, list)

    regexes = []
    for item in patterns:
        if not isinstance(item, dict):
            continue
        match = item.get("match")
        if isinstance(match, str) and match:
            regexes.append(re.compile(match))

    missing: list[str] = []
    for keyword in _load_json_keywords():
        if not any(regex.search(keyword) for regex in regexes):
            missing.append(keyword)

    assert not missing, f"grammar missing canonical keywords: {', '.join(sorted(missing))}"