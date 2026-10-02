"""Validator for a CareerBench bench content repository (personas and goals).

Every content type shares the same folder-per-item shape: one folder per item,
one main markdown file with YAML frontmatter and a markdown body.

- personas/  persona.md   synthetic users for the persona LLM
- goals/     goal.md      what the user is trying to get done in a conversation

The validator is intentionally stricter than the Runner: the Runner skips a
malformed item, but CI should fail the pull request so the author fixes it
before merge.

Design notes:

- The frontmatter contract for each content type is declared data, not code:
  it lives in ``<type>/_schemas/content/frontmatter.schema.json`` and is loaded
  at runtime. Adding an allowed key is a content-only change, no edit here.
- Two rules cannot be expressed in JSON Schema and so live in this file:
  the ``id`` format/lifecycle rules (see ``canonicalize_item_id``) and
  cross-file uniqueness of ``id`` and ``name`` within a content type.
- Every problem is collected into a ``Report`` and printed at the end, so an
  author sees all mistakes in one pass instead of fixing them one rerun at a time.

Usage:

    python scripts/validate_content.py [REPO_ROOT]

REPO_ROOT defaults to the current working directory. The process exits non-zero
if at least one problem is found.
"""

from __future__ import annotations

import json
import re
import sys
import uuid
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError

# Names of the two special (non-item) folders present in every content type.
SCHEMAS_DIR = "_schemas"
EXAMPLE_DIR = "_example"

# Inside _schemas/, content/ holds the contracts CI checks about the authored files.
CONTENT_SCHEMAS_DIR = "content"

FRONTMATTER_SCHEMA_FILENAME = "frontmatter.schema.json"

FRONTMATTER_FENCE = "---"

# The literal id every item ships with while it is still a draft. It is swapped
# for a real UUID at publish time (see canonicalize_item_id).
PLACEHOLDER_ID = "placeholder-uuidv4"
DRAFT = "draft"
PUBLISHED = "published"

# Folder slugs are snake_case.
SLUG_PATTERN = re.compile(r"^[a-z0-9]+(?:_[a-z0-9]+)*$")


@dataclass(frozen=True)
class ContentType:
    """One of the top-level content directories and its main file."""

    directory: str
    main_filename: str


CONTENT_TYPES = (
    ContentType(directory="personas", main_filename="persona.md"),
    ContentType(directory="goals", main_filename="goal.md"),
)


@dataclass
class Problem:
    """A single validation failure, tied to the file that caused it.

    ``code`` is a stable machine-readable identifier (used by the tests);
    ``message`` is the human-readable explanation.
    """

    path: str
    code: str
    message: str

    def render(self) -> str:
        return f"{self.path}: {self.message}"


@dataclass
class Report:
    """Accumulates every problem found during a run so they can be printed together."""

    problems: list[Problem] = field(default_factory=list)

    def add(self, path: str, code: str, message: str) -> None:
        self.problems.append(Problem(path=path, code=code, message=message))

    @property
    def ok(self) -> bool:
        return len(self.problems) == 0

    def has_problem(self, *, code: str, path_fragment: str | None = None) -> bool:
        """Whether a problem with ``code`` exists (optionally under a path substring)."""
        for problem in self.problems:
            if problem.code != code:
                continue
            if path_fragment is not None and path_fragment not in problem.path:
                continue
            return True
        return False


@dataclass
class UniquenessTracker:
    """Remembers the ids and names already claimed within one content type.

    Uniqueness is scoped per content type: a goal and a persona may coincidentally
    share a name, but two goals may not. Names are compared case-insensitively so
    "Build a resume" and "build a resume" are treated as the same name.
    """

    ids_seen: dict[str, str] = field(default_factory=dict)
    names_seen: dict[str, str] = field(default_factory=dict)


def relative_to_root(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def split_frontmatter(text: str, rel: str, report: Report) -> tuple[dict | None, str]:
    """Split a markdown file into its YAML frontmatter mapping and its body.

    Returns ``(frontmatter, body)``. ``frontmatter`` is ``None`` (and a problem is
    recorded) when the frontmatter block is absent, unterminated, invalid YAML, or
    not a mapping. ``body`` is the markdown after the closing fence, stripped.
    """
    stripped = text.lstrip("\ufeff")
    if not stripped.startswith(FRONTMATTER_FENCE):
        report.add(rel, "missing_frontmatter", "missing YAML frontmatter (file must start with '---')")
        return None, stripped.strip()

    lines = stripped.splitlines()
    closing_index = None
    for index in range(1, len(lines)):
        if lines[index].strip() == FRONTMATTER_FENCE:
            closing_index = index
            break
    if closing_index is None:
        report.add(rel, "unclosed_frontmatter", "frontmatter is not closed with '---'")
        return None, ""

    raw_frontmatter = "\n".join(lines[1:closing_index])
    body = "\n".join(lines[closing_index + 1 :]).strip()
    try:
        loaded = yaml.safe_load(raw_frontmatter) or {}
    except yaml.YAMLError as exc:
        report.add(rel, "invalid_frontmatter_yaml", f"invalid frontmatter YAML: {exc}")
        return None, body
    if not isinstance(loaded, dict):
        report.add(rel, "frontmatter_not_mapping", "frontmatter must be a mapping")
        return None, body
    return loaded, body


def load_json_schema(path: Path, rel: str, report: Report) -> Draft202012Validator | None:
    """Parse a JSON Schema file and confirm it is itself a valid schema.

    Returns a ready-to-use validator, or ``None`` (with a problem recorded) if the
    file is not valid JSON or not a valid JSON Schema.
    """
    raw = path.read_text(encoding="utf-8")
    try:
        schema = json.loads(raw)
    except json.JSONDecodeError as exc:
        report.add(rel, "invalid_schema_json", f"invalid JSON: {exc}")
        return None
    try:
        Draft202012Validator.check_schema(schema)
    except SchemaError as exc:
        report.add(rel, "invalid_schema", f"invalid JSON Schema: {exc.message}")
        return None
    return Draft202012Validator(schema)


def describe_schema_error_location(error) -> str:
    """Render where in the frontmatter a schema error occurred, e.g. 'status' or '(root)'."""
    if not error.absolute_path:
        return "(root)"
    parts = [str(part) for part in error.absolute_path]
    return ".".join(parts)


def validate_frontmatter_against_schema(
    frontmatter: dict,
    schema: Draft202012Validator | None,
    rel: str,
    report: Report,
) -> None:
    """Report every JSON Schema violation in an item's frontmatter (allowed keys, status enum, etc.)."""
    if schema is None:
        return
    errors = sorted(schema.iter_errors(frontmatter), key=lambda e: list(e.absolute_path))
    for error in errors:
        location = describe_schema_error_location(error)
        report.add(rel, "frontmatter_schema_error", f"{location}: {error.message}")


def canonicalize_item_id(raw_id: object, status: object, rel: str, report: Report) -> str | None:
    """Validate an item's id and return its canonical form for uniqueness tracking.

    The id is the item's permanent identity (results are stored against it), so the
    rules are stricter than "a non-empty string":

    - drafts may keep the ``placeholder-uuidv4`` literal;
    - a published item must carry a real UUID (the placeholder is rejected);
    - anything that is neither the placeholder nor a valid UUID is rejected.

    Returns the canonical UUID string (lowercased/normalized so "AAAA..." and
    "aaaa..." collide), or ``None`` when the id is a placeholder or invalid and so
    should be excluded from uniqueness tracking. A missing/blank id is left to the
    frontmatter schema to report and is not re-reported here.
    """
    if not isinstance(raw_id, str) or not raw_id.strip():
        return None

    candidate = raw_id.strip()
    if candidate == PLACEHOLDER_ID:
        if status == PUBLISHED:
            report.add(
                rel,
                "published_requires_real_id",
                "published items need a real UUID id; run `uuidgen` and replace the placeholder",
            )
        return None

    try:
        parsed = uuid.UUID(candidate)
    except ValueError:
        report.add(
            rel,
            "invalid_id",
            f"'id' must be '{PLACEHOLDER_ID}' or a valid UUID (got {candidate!r})",
        )
        return None
    return str(parsed)


def load_frontmatter_schema(content_root: Path, root: Path, report: Report) -> Draft202012Validator | None:
    """Load a content type's frontmatter JSON Schema, or record a problem if it is missing/invalid."""
    path = content_root / SCHEMAS_DIR / CONTENT_SCHEMAS_DIR / FRONTMATTER_SCHEMA_FILENAME
    rel = relative_to_root(path, root)
    if not path.is_file():
        report.add(rel, "missing_frontmatter_schema", f"expected {FRONTMATTER_SCHEMA_FILENAME}")
        return None
    return load_json_schema(path, rel, report)


def register_unique_value(
    key: str,
    display: str,
    rel: str,
    seen: dict[str, str],
    *,
    code: str,
    label: str,
    report: Report,
) -> None:
    """Record ``key`` in ``seen``; report a duplicate if another file already claimed it.

    ``key`` is the normalized comparison key, ``display`` is what to show the author,
    and ``seen`` maps key -> the first file that used it.
    """
    if key in seen:
        report.add(rel, code, f"duplicate {label} {display!r}; already used in {seen[key]}")
        return
    seen[key] = rel


def check_id_uniqueness(frontmatter: dict, rel: str, tracker: UniquenessTracker, report: Report) -> None:
    canonical_id = canonicalize_item_id(frontmatter.get("id"), frontmatter.get("status"), rel, report)
    if canonical_id is None:
        return
    register_unique_value(
        canonical_id,
        canonical_id,
        rel,
        tracker.ids_seen,
        code="duplicate_id",
        label="id",
        report=report,
    )


def check_name_uniqueness(frontmatter: dict, rel: str, tracker: UniquenessTracker, report: Report) -> None:
    name = frontmatter.get("name")
    # A missing or blank name is already reported by the frontmatter schema.
    if not isinstance(name, str) or not name.strip():
        return
    display_name = name.strip()
    comparison_key = display_name.casefold()
    register_unique_value(
        comparison_key,
        display_name,
        rel,
        tracker.names_seen,
        code="duplicate_name",
        label="name",
        report=report,
    )


def validate_item_folder(
    folder: Path,
    root: Path,
    content_type: ContentType,
    frontmatter_schema: Draft202012Validator | None,
    tracker: UniquenessTracker,
    report: Report,
) -> None:
    """Validate a single item folder (slug, main file, frontmatter, id/name uniqueness, body)."""
    slug = folder.name
    folder_rel = relative_to_root(folder, root)
    if slug != EXAMPLE_DIR and not SLUG_PATTERN.match(slug):
        report.add(
            folder_rel,
            "invalid_slug",
            f"folder slug {slug!r} must be snake_case (lowercase, digits, underscores)",
        )

    main_path = folder / content_type.main_filename
    if not main_path.is_file():
        report.add(folder_rel, "missing_main_file", f"missing required {content_type.main_filename}")
        return

    rel = relative_to_root(main_path, root)
    text = main_path.read_text(encoding="utf-8")
    frontmatter, body = split_frontmatter(text, rel, report)

    if frontmatter is not None:
        validate_frontmatter_against_schema(frontmatter, frontmatter_schema, rel, report)
        check_id_uniqueness(frontmatter, rel, tracker, report)
        check_name_uniqueness(frontmatter, rel, tracker, report)

    if not body:
        report.add(rel, "empty_body", f"{content_type.main_filename} body is empty")


def validate_content_type(root: Path, content_type: ContentType, report: Report) -> None:
    """Validate every item folder under one content directory.

    Iterates the content directory, skipping ``_schemas/`` and validating every
    other folder (including ``_example/``, which must exist) as an item. ``id`` and
    ``name`` uniqueness are tracked across the whole content type.
    """
    content_root = root / content_type.directory
    if not content_root.is_dir():
        report.add(
            content_type.directory,
            "missing_content_directory",
            f"expected {content_type.directory}/ directory",
        )
        return

    frontmatter_schema = load_frontmatter_schema(content_root, root, report)
    tracker = UniquenessTracker()
    found_example = False

    for folder in sorted(content_root.iterdir()):
        if not folder.is_dir():
            continue
        if folder.name == SCHEMAS_DIR:
            continue
        if folder.name == EXAMPLE_DIR:
            found_example = True
        validate_item_folder(
            folder,
            root,
            content_type,
            frontmatter_schema,
            tracker,
            report,
        )

    if not found_example:
        report.add(content_type.directory, "missing_example", f"expected {EXAMPLE_DIR}/ template folder")


def run(root: Path) -> Report:
    """Validate the whole repo and return the accumulated report."""
    report = Report()
    for content_type in CONTENT_TYPES:
        validate_content_type(root, content_type, report)
    return report


def main(argv: list[str]) -> int:
    root = Path(argv[1]).resolve() if len(argv) > 1 else Path.cwd()
    report = run(root)

    if report.ok:
        print(f"Content validation passed for {root}.")
        return 0

    print(f"Content validation found {len(report.problems)} problem(s) in {root}:\n")
    for problem in sorted(report.problems, key=lambda p: (p.path, p.message)):
        print(f"  - {problem.render()}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
