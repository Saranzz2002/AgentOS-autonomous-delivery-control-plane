from __future__ import annotations

import pytest

from backend.tools.filesystem import RepositoryFileError, get_repository_tree, important_files, read_file
from backend.tools.repository import analyze_repository, validate_repository_url
from backend.tools.search import search_code, search_code_many


def test_tree_ignores_generated_directories(python_repo):
    (python_repo / "node_modules").mkdir()
    (python_repo / "node_modules" / "generated.js").write_text("secret", encoding="utf-8")
    (python_repo / "app" / "__pycache__").mkdir()
    tree = get_repository_tree(python_repo)
    assert "app/main.py" in tree
    assert "tests/test_main.py" in tree
    assert not any("node_modules" in path or "__pycache__" in path for path in tree)


def test_read_file_blocks_traversal_secrets_and_binary(python_repo, tmp_path):
    outside = tmp_path.parent / "outside-secret.txt"
    outside.write_text("outside", encoding="utf-8")
    with pytest.raises(RepositoryFileError):
        read_file(python_repo, "../outside-secret.txt")
    (python_repo / ".env").write_text("SECRET=hidden", encoding="utf-8")
    with pytest.raises(RepositoryFileError):
        read_file(python_repo, ".env")
    (python_repo / "image.bin").write_bytes(b"\x00\x01")
    with pytest.raises(RepositoryFileError):
        read_file(python_repo, "image.bin")


def test_read_file_rejects_symlink_outside_repository(python_repo, tmp_path):
    outside = tmp_path.parent / "outside.py"
    outside.write_text("do not read", encoding="utf-8")
    link = python_repo / "app" / "outside.py"
    try:
        link.symlink_to(outside)
    except (OSError, NotImplementedError):
        pytest.skip("Symlink creation is not available on this system.")
    with pytest.raises(RepositoryFileError):
        read_file(python_repo, "app/outside.py")


def test_important_files_and_code_search(python_repo):
    tree = get_repository_tree(python_repo)
    important = important_files(tree)
    assert "app/main.py" in important["entry_points"]
    assert "requirements.txt" in important["configuration_files"]
    assert important["documentation"] == ["README.md"]
    hits = search_code(python_repo, "FastAPI")
    assert hits[0]["file"] == "app/main.py"
    assert hits[0]["line"] == 1


def test_multi_term_search_finds_matches_in_one_pass(python_repo):
    hits = search_code_many(python_repo, ["FastAPI", "test_status"], limit=10)
    assert {"app/main.py", "tests/test_main.py"} <= {hit["file"] for hit in hits}


def test_detect_python_fastapi_project(python_repo):
    metadata = analyze_repository(python_repo, "https://github.com/example/demo")
    assert metadata["language"] == "Python"
    assert metadata["framework"] == "FastAPI"
    assert metadata["test_framework"] == "pytest"
    assert metadata["source_file_count"] == 2
    assert metadata["test_file_count"] == 1


def test_detect_node_next_project(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "index.ts").write_text("export const app = true;\n", encoding="utf-8")
    (tmp_path / "package.json").write_text('{"dependencies":{"next":"15.0.0","react":"19.0.0"}}', encoding="utf-8")
    (tmp_path / "pnpm-lock.yaml").write_text("lockfileVersion: '9.0'\n", encoding="utf-8")
    metadata = analyze_repository(tmp_path)
    assert metadata["language"] == "TypeScript"
    assert metadata["framework"] == "Next.js"
    assert metadata["package_manager"] == "pnpm"


@pytest.mark.parametrize("url", [
    "http://github.com/owner/repo",
    "https://github.com/owner/repo/tree/main",
    "https://user:token@github.com/owner/repo",
    "https://github.com:444/owner/repo",
    "https://github.com/owner/repo?token=x",
    "https://github.com/owner:bad/repo",
])
def test_github_url_validation_rejects_unsafe_urls(url):
    with pytest.raises(ValueError):
        validate_repository_url(url)


def test_github_url_validation_accepts_public_repo():
    assert validate_repository_url("https://github.com/example/repo.git") == (
        "https://github.com/example/repo.git", "example", "repo"
    )
