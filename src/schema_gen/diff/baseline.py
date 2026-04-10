"""Load baseline and current JSON Schema files for comparison."""

import json
import re
import subprocess
from pathlib import Path
from typing import Any


class BaselineError(Exception):
    """Raised when the baseline cannot be loaded."""


_GIT_REF_RE = re.compile(r"^\.git#(?P<kind>branch|tag|commit)=(?P<value>.+)$")


def _parse_git_ref(against: str) -> str:
    """Extract the git ref from an ``--against`` value.

    Accepted formats::

        .git#branch=main
        .git#tag=v1.0.0
        .git#commit=abc123

    Returns the bare ref string (e.g. ``main``, ``v1.0.0``, ``abc123``).

    Raises:
        BaselineError: If the format is not recognised.
    """
    match = _GIT_REF_RE.match(against)
    if not match:
        raise BaselineError(
            f"Invalid git baseline format: {against!r}. "
            "Expected .git#branch=<name>, .git#tag=<name>, or .git#commit=<hash>"
        )
    return match.group("value")


def _git_show(ref: str, path: str) -> str | None:
    """Run ``git show <ref>:<path>`` and return the content, or None if not found.

    Returns None when the file does not exist at the given ref.
    Raises :class:`BaselineError` for unexpected git failures.
    """
    result = subprocess.run(
        ["git", "show", f"{ref}:{path}"],
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        return result.stdout
    # "does not exist" or "exists on disk, but not in" → file not found at ref.
    if "does not exist" in result.stderr or "exists on disk" in result.stderr:
        return None
    # Any other error (bad ref, corrupt repo) should surface.
    raise BaselineError(f"git show {ref}:{path} failed: {result.stderr.strip()}")


def _discover_current_json_files(jsonschema_dir: Path) -> list[str]:
    """Return sorted list of ``*.json`` filenames in *jsonschema_dir*."""
    if not jsonschema_dir.is_dir():
        return []
    return sorted(p.name for p in jsonschema_dir.glob("*.json"))


def _repo_relative_posix(path: Path) -> str:
    """Return *path* as a POSIX-style repo-relative string.

    Uses ``git rev-parse --show-toplevel`` to compute the repo root, then
    makes *path* relative to it.  Falls back to ``path.as_posix()`` if the
    repo root cannot be determined (e.g. not inside a git repository).
    """
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            check=True,
        )
        repo_root = Path(result.stdout.strip())
        return path.resolve().relative_to(repo_root).as_posix()
    except (subprocess.CalledProcessError, ValueError):
        return path.as_posix()


def _discover_baseline_json_files(ref: str, jsonschema_dir: Path) -> list[str]:
    """Return sorted list of ``*.json`` filenames that exist at *ref* in git.

    Uses ``git ls-tree`` to enumerate files at the baseline ref, catching
    deletions that ``_discover_current_json_files`` would miss.

    Raises :class:`BaselineError` for unexpected git failures (bad ref, not
    a git repo, etc.).
    """
    posix_dir = _repo_relative_posix(jsonschema_dir)
    result = subprocess.run(
        ["git", "ls-tree", "--name-only", ref, posix_dir + "/"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        stderr = result.stderr.strip()
        # "not a tree object" / path simply didn't exist at that ref → empty.
        if "not a tree object" in stderr or not stderr:
            return []
        raise BaselineError(f"git ls-tree failed for ref '{ref}': {stderr}")

    filenames: list[str] = []
    for line in result.stdout.strip().splitlines():
        name = Path(line).name
        if name.endswith(".json"):
            filenames.append(name)
    return sorted(filenames)


def load_baseline(against: str, output_dir: str) -> dict[str, dict[str, Any]]:
    """Load baseline JSON Schema files.

    Args:
        against: The ``--against`` CLI value — either a git ref
            (``.git#branch=main``) or a directory path.
        output_dir: The project's configured output directory (e.g. ``generated/``).

    Returns:
        Mapping of ``{filename: parsed_json_schema_dict}``.

    Raises:
        BaselineError: If the baseline cannot be loaded.
    """
    if against.startswith(".git#"):
        return _load_from_git(against, output_dir)
    return _load_from_directory(against)


def _load_from_git(against: str, output_dir: str) -> dict[str, dict[str, Any]]:
    """Load baseline schemas from a git ref.

    Discovers files from both the baseline ref and the current working tree
    so that deleted files (present at baseline but absent locally) are still
    included in the comparison.
    """
    ref = _parse_git_ref(against)
    jsonschema_dir = Path(output_dir) / "jsonschema"

    # Union of current and baseline files — ensures deletions are detected.
    current_files = set(_discover_current_json_files(jsonschema_dir))
    baseline_files = set(_discover_baseline_json_files(ref, jsonschema_dir))
    filenames = sorted(current_files | baseline_files)

    if not filenames:
        raise BaselineError(
            f"No JSON Schema files found in {jsonschema_dir} (current or baseline). "
            "Ensure 'jsonschema' is in your targets and run 'schema-gen generate' first."
        )

    schemas: dict[str, dict[str, Any]] = {}
    for filename in filenames:
        rel_path = _repo_relative_posix(jsonschema_dir / filename)
        content = _git_show(ref, rel_path)
        if content is not None:
            try:
                schemas[filename] = json.loads(content)
            except json.JSONDecodeError as exc:
                raise BaselineError(
                    f"Invalid JSON in baseline {ref}:{rel_path}: {exc}"
                ) from exc
    return schemas


def _load_from_directory(dir_path: str) -> dict[str, dict[str, Any]]:
    """Load baseline schemas from a directory snapshot."""
    directory = Path(dir_path)
    if not directory.is_dir():
        raise BaselineError(f"Baseline directory not found: {dir_path}")

    schemas: dict[str, dict[str, Any]] = {}
    for json_file in sorted(directory.glob("*.json")):
        try:
            schemas[json_file.name] = json.loads(json_file.read_text())
        except json.JSONDecodeError as exc:
            raise BaselineError(f"Invalid JSON in {json_file}: {exc}") from exc
    return schemas


def load_current(output_dir: str) -> dict[str, dict[str, Any]]:
    """Load current JSON Schema files from the output directory.

    Args:
        output_dir: The project's configured output directory.

    Returns:
        Mapping of ``{filename: parsed_json_schema_dict}``.

    Raises:
        BaselineError: If no JSON Schema files are found.
    """
    jsonschema_dir = Path(output_dir) / "jsonschema"
    if not jsonschema_dir.is_dir():
        raise BaselineError(
            f"No jsonschema directory found at {jsonschema_dir}. "
            "Ensure 'jsonschema' is in your targets and run 'schema-gen generate' first."
        )

    schemas: dict[str, dict[str, Any]] = {}
    for json_file in sorted(jsonschema_dir.glob("*.json")):
        try:
            schemas[json_file.name] = json.loads(json_file.read_text())
        except json.JSONDecodeError as exc:
            raise BaselineError(f"Invalid JSON in {json_file}: {exc}") from exc

    if not schemas:
        raise BaselineError(
            f"No JSON Schema files found in {jsonschema_dir}. "
            "Run 'schema-gen generate' first."
        )

    return schemas
