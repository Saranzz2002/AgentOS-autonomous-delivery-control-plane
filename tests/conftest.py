from __future__ import annotations

import pytest


@pytest.fixture
def python_repo(tmp_path):
    (tmp_path / "app").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "app" / "main.py").write_text(
        "from fastapi import FastAPI\napp = FastAPI()\n", encoding="utf-8"
    )
    (tmp_path / "tests" / "test_main.py").write_text(
        "def test_status():\n    assert True\n", encoding="utf-8"
    )
    (tmp_path / "requirements.txt").write_text("fastapi>=0.100\npytest\n", encoding="utf-8")
    (tmp_path / "README.md").write_text("# Demo FastAPI service\n", encoding="utf-8")
    return tmp_path
