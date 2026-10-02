"""Tests for the content validator.

Each test assembles a throwaway repo under tmp_path: the real `_schemas/` and
`_example/` folders for every content type, plus a named fixture case from
tests/fixtures/<content_type>/<case>/ overlaid onto that content type. Because the
base repo is valid, an overlaid fixture case trips exactly the one rule it targets.
One test points the validator at the actual checked-in content so the shipped
files stay valid.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from validate_content import CONTENT_TYPES, main, run

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURES_ROOT = Path(__file__).resolve().parent / "fixtures"


def build_repo(tmp_path: Path, *, personas: str | None = None, goals: str | None = None) -> Path:
    """Assemble a repo root: real _schemas + _example for each type, plus named fixture cases."""
    for content_type in CONTENT_TYPES:
        source = REPO_ROOT / content_type.directory
        shutil.copytree(source / "_schemas", tmp_path / content_type.directory / "_schemas")
        shutil.copytree(source / "_example", tmp_path / content_type.directory / "_example")

    overlay(tmp_path, "personas", personas)
    overlay(tmp_path, "goals", goals)
    return tmp_path


def overlay(tmp_path: Path, directory: str, case: str | None) -> None:
    if case is None:
        return
    source = FIXTURES_ROOT / directory / case
    shutil.copytree(source, tmp_path / directory, dirs_exist_ok=True)


def assert_problem(report, code: str, path_fragment: str) -> None:
    rendered = [p.render() for p in report.problems]
    assert report.has_problem(code=code, path_fragment=path_fragment), rendered


def test_real_repo_passes():
    report = run(REPO_ROOT)
    assert report.ok, [p.render() for p in report.problems]


def test_valid_minimal_repo_passes(tmp_path):
    root = build_repo(tmp_path)
    report = run(root)
    assert report.ok, [p.render() for p in report.problems]


def test_valid_persona_case_passes(tmp_path):
    root = build_repo(tmp_path, personas="valid")
    report = run(root)
    assert report.ok, [p.render() for p in report.problems]


def test_valid_goal_case_passes(tmp_path):
    root = build_repo(tmp_path, goals="valid")
    report = run(root)
    assert report.ok, [p.render() for p in report.problems]


def test_bad_slug(tmp_path):
    root = build_repo(tmp_path, personas="bad_slug")
    report = run(root)
    assert_problem(report, "invalid_slug", "BadSlug")


def test_missing_main_file(tmp_path):
    root = build_repo(tmp_path, personas="missing_persona")
    report = run(root)
    assert_problem(report, "missing_main_file", "no_persona")


def test_missing_frontmatter(tmp_path):
    root = build_repo(tmp_path, personas="missing_frontmatter")
    report = run(root)
    assert_problem(report, "missing_frontmatter", "persona.md")


def test_unknown_frontmatter_key(tmp_path):
    root = build_repo(tmp_path, personas="unknown_key")
    report = run(root)
    assert_problem(report, "frontmatter_schema_error", "persona.md")


def test_blank_name(tmp_path):
    root = build_repo(tmp_path, personas="blank_name")
    report = run(root)
    assert_problem(report, "frontmatter_schema_error", "persona.md")


def test_bad_status(tmp_path):
    root = build_repo(tmp_path, personas="bad_status")
    report = run(root)
    assert_problem(report, "frontmatter_schema_error", "persona.md")


def test_bad_id(tmp_path):
    root = build_repo(tmp_path, personas="bad_id")
    report = run(root)
    assert_problem(report, "invalid_id", "persona.md")


def test_published_requires_real_id(tmp_path):
    root = build_repo(tmp_path, personas="published_placeholder")
    report = run(root)
    assert_problem(report, "published_requires_real_id", "persona.md")


def test_duplicate_id(tmp_path):
    root = build_repo(tmp_path, goals="duplicate_id")
    report = run(root)
    assert_problem(report, "duplicate_id", "two")


def test_duplicate_name_case_insensitive(tmp_path):
    root = build_repo(tmp_path, personas="duplicate_name")
    report = run(root)
    assert_problem(report, "duplicate_name", "two")


def test_empty_body(tmp_path):
    root = build_repo(tmp_path, personas="empty_body")
    report = run(root)
    assert_problem(report, "empty_body", "persona.md")


def test_missing_example(tmp_path):
    root = build_repo(tmp_path)
    shutil.rmtree(root / "goals" / "_example")
    report = run(root)
    assert_problem(report, "missing_example", "goals")


def test_main_exit_code_on_valid(tmp_path, capsys):
    root = build_repo(tmp_path)
    exit_code = main(["validate_content.py", str(root)])
    output = capsys.readouterr().out
    assert exit_code == 0
    assert "Content validation passed" in output


def test_main_exit_code_on_problems(tmp_path, capsys):
    root = build_repo(tmp_path, personas="bad_id")
    exit_code = main(["validate_content.py", str(root)])
    output = capsys.readouterr().out
    assert exit_code == 1
    assert "1 problem(s)" in output
