from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast


MISSING_LINE = "<missing>"
DEFAULT_SRC = ".env.sample"


@dataclass(frozen=True)
class Mismatch:
    path: Path
    line_num: int
    current: str
    expected: str


def discover_env_targets(repo_root: Path, *, src_resolved: Path) -> list[Path]:
    return sorted(path for path in repo_root.glob(".env*") if path.is_file() and path.resolve() != src_resolved)


def parse_env_assignment(line: str) -> tuple[str, str] | None:
    stripped = line.rstrip()
    if not stripped or stripped.startswith("#") or "=" not in stripped:
        return None
    key, value = stripped.split("=", 1)
    return (key.strip(), value.strip())


def collect_env_values(lines: list[str]) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in lines:
        parsed = parse_env_assignment(line)
        if parsed is not None:
            values[parsed[0]] = parsed[1]
    return values


def render_env_file(sample_lines: list[str], target_lines: list[str]) -> list[str]:
    target_values = collect_env_values(target_lines[: len(sample_lines)])
    rendered: list[str] = []
    for line in sample_lines:
        parsed = parse_env_assignment(line)
        if parsed is None:
            rendered.append(line)
            continue
        key, _value = parsed
        rendered.append(f"{key}={target_values[key]}" if key in target_values else line)
    return rendered


def find_first_env_structure_mismatch(
    expected_lines: list[str],
    target_path: Path,
    target_lines: list[str],
) -> Mismatch | None:
    total_lines = max(len(expected_lines), len(target_lines))
    for index in range(total_lines):
        expected_line = expected_lines[index] if index < len(expected_lines) else MISSING_LINE
        target_line = target_lines[index] if index < len(target_lines) else MISSING_LINE
        if expected_line != target_line:
            return Mismatch(path=target_path, line_num=index + 1, current=target_line, expected=expected_line)
    return None


def resolve_repo_path(repo_root: Path, rel_or_abs: str | Path) -> Path:
    path = Path(rel_or_abs)
    return path if path.is_absolute() else (repo_root / path).resolve()


def _validate_path_arg(name: str, value: str | Path) -> list[str]:
    if not isinstance(value, (str, Path)):
        return [f"{name} must be a path (str or Path), got {type(value).__name__}"]
    if isinstance(value, str) and not value.strip():
        return [f"{name} must be a non-empty path when provided"]
    return []


def _format_mismatch(mismatch: Mismatch, repo_root: Path) -> str:
    try:
        rel = mismatch.path.resolve().relative_to(repo_root.resolve())
    except ValueError:
        rel = mismatch.path
    return f"{rel}: line {mismatch.line_num}: {mismatch.current} -> {mismatch.expected}"


def check_env_files_match_sample(
    repo_root: Path,
    *,
    fix: bool = False,
    src: str | Path | None = None,
    tgt: str | Path | None = None,
) -> list[str]:
    src_spec: str | Path = DEFAULT_SRC if src is None else src
    if err := _validate_path_arg("src", src_spec):
        return err
    src_path = resolve_repo_path(repo_root, src_spec)
    if not src_path.exists():
        return [f"Source file not found: {src_path}"]
    try:
        sample_full = src_path.read_text(encoding="utf-8").splitlines()
    except OSError as error:
        return [f"Error reading {src_path}: {error}"]

    if tgt is not None:
        if err := _validate_path_arg("tgt", tgt):
            return err
        target = resolve_repo_path(repo_root, tgt)
        if not target.exists():
            return [f"Target file not found: {target}"]
        env_files = [target]
    else:
        env_files = discover_env_targets(repo_root, src_resolved=src_path.resolve())
        if not env_files:
            return [f"No top-level .env* files found to check (source excluded: {src_path.name})"]

    errors: list[str] = []
    for target_path in env_files:
        try:
            target_lines = target_path.read_text(encoding="utf-8").splitlines()
        except OSError as error:
            errors.append(f"Error reading {target_path}: {error}")
            continue
        expected_lines = render_env_file(sample_full, target_lines)
        prefix_len = len(sample_full)
        mismatch = find_first_env_structure_mismatch(expected_lines, target_path, target_lines[:prefix_len])
        if mismatch is None:
            continue
        if fix:
            try:
                target_path.write_text("\n".join(expected_lines + target_lines[prefix_len:]) + "\n", encoding="utf-8")
            except OSError as error:
                errors.append(f"Error writing {target_path}: {error}")
            continue
        errors.append(_format_mismatch(mismatch, repo_root))
    return errors


def _normalize_pairs(raw_pairs: object) -> tuple[list[dict[str, Any]] | None, str | None]:
    if raw_pairs is None:
        return None, None
    if not isinstance(raw_pairs, list):
        return None, "pairs must be a list of mappings"
    pairs: list[dict[str, Any]] = []
    for index, item in enumerate(raw_pairs):
        if not isinstance(item, dict):
            return None, f"pairs[{index}] must be a mapping"
        pairs.append(cast("dict[str, Any]", item))
    return pairs, None


def run(
    *,
    repo_root: Path,
    fix: bool = False,
    src: str | Path | None = None,
    tgt: str | Path | None = None,
    pairs: object | None = None,
    **_kwargs: object,
) -> list[str]:
    normalized_pairs, error = _normalize_pairs(pairs)
    if error is not None:
        return [error]
    if normalized_pairs is None:
        return check_env_files_match_sample(repo_root, fix=fix, src=src, tgt=tgt)

    errors: list[str] = []
    for index, pair in enumerate(normalized_pairs):
        pair_src = pair.get("src", src)
        pair_tgt = pair.get("tgt", tgt)
        if pair_src is None:
            return [f"pairs[{index}].src is required"]
        if pair_tgt is None:
            return [f"pairs[{index}].tgt is required"]
        errors.extend(check_env_files_match_sample(repo_root, fix=fix, src=pair_src, tgt=pair_tgt))
    return errors
