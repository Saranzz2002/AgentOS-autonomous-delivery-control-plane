from __future__ import annotations

import re
from pathlib import Path

from backend.tools.filesystem import IGNORED_NAMES, RepositoryFileError, get_repository_tree, read_file


def search_code(repo_path: str | Path, query: str, limit: int = 40) -> list[dict[str, str | int]]:
    """Search safe text files and return bounded filename/line matches."""
    return search_code_many(repo_path, [query], limit=limit)


def search_code_many(repo_path: str | Path, queries: list[str], limit: int = 40) -> list[dict[str, str | int]]:
    """Search for any of several terms while walking and reading each file once."""
    terms = list(dict.fromkeys(query.strip() for query in queries if query.strip() and len(query.strip()) <= 200))
    if not terms or limit <= 0:
        return []
    try:
        matcher = re.compile("(?:" + "|".join(re.escape(term) for term in terms) + ")", re.IGNORECASE)
    except re.error:
        return []
    results: list[dict[str, str | int]] = []
    tree = get_repository_tree(repo_path)
    code_suffixes = {".py", ".js", ".jsx", ".ts", ".tsx", ".java", ".go", ".rs"}
    tree.sort(key=lambda path: (Path(path).suffix.lower() not in code_suffixes, path.lower()))
    for relative_path in tree:
        if Path(relative_path).suffix.lower() not in {
            ".py", ".js", ".jsx", ".ts", ".tsx", ".json", ".toml", ".yaml",
            ".yml", ".md", ".html", ".css", ".java", ".go", ".rs", ".txt",
        }:
            continue
        if any(part in IGNORED_NAMES for part in Path(relative_path).parts):
            continue
        try:
            content = read_file(repo_path, relative_path, max_bytes=128_000)
        except RepositoryFileError:
            continue
        for line_number, line in enumerate(content.splitlines(), start=1):
            if matcher.search(line):
                results.append({"file": relative_path, "line": line_number, "content": line.strip()[:500]})
                if len(results) >= limit:
                    return results
    return results
