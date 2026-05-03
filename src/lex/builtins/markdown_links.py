from __future__ import annotations

import re
from pathlib import Path


SKIP_DIR_NAMES: frozenset[str] = frozenset(
    {
        ".git",
        ".venv",
        ".uv-cache",
        ".pytest_cache",
        ".ruff_cache",
        ".mypy_cache",
        ".tox",
        "__pycache__",
        "node_modules",
        "artifacts",
        ".deepeval",
        ".vector_db",
        "htmlcov",
        "tmp",
    },
)

_LINK_RE = re.compile(r"!?\[[^\]]*\]\(\s*(?:<([^>]+)>|([^)\s]+))(?:\s+[^)]*)?\s*\)")
_REF_DEF_RE = re.compile(r"^ {0,3}\[[^\]]+\]:\s+(?:<([^>]+)>|(\S+))", re.MULTILINE)
_NON_FILE_SCHEMES = frozenset(
    f"{scheme}:" for scheme in ("http", "https", "mailto", "tel", "javascript", "data", "ftp", "ftps")
)


def iter_markdown_files(repo_root: Path, *, skip_dirs: list[str] | None = None) -> list[Path]:
    root = repo_root.resolve()
    skipped = SKIP_DIR_NAMES | frozenset(skip_dirs or [])
    results: list[Path] = []
    for path in root.rglob("*.md"):
        try:
            rel_parts = path.relative_to(root).parts
        except ValueError:
            continue
        if not any(part in skipped for part in rel_parts):
            results.append(path)
    return sorted(results)


def strip_fenced_code_blocks(text: str) -> str:
    lines = text.splitlines(keepends=True)
    out: list[str] = []
    fence: str | None = None
    for line in lines:
        stripped = line.lstrip()
        if fence is None:
            if stripped.startswith(("```", "~~~")):
                fence = stripped[:3]
                continue
            out.append(line)
        elif stripped.startswith(fence):
            fence = None
    return "".join(out)


def _link_path_part(raw: str) -> str:
    dest = raw.strip()
    if dest.startswith("<") and dest.endswith(">"):
        dest = dest[1:-1].strip()
    for sep in ("#", "?"):
        if sep in dest:
            dest = dest.split(sep, 1)[0]
    return dest.strip()


def _is_external_or_anchor(path_part: str) -> bool:
    if not path_part or path_part.startswith("#"):
        return True
    lowered = path_part.lower()
    return any(lowered.startswith(prefix) for prefix in _NON_FILE_SCHEMES)


def extract_link_targets(text: str) -> list[tuple[int, str]]:
    cleaned = strip_fenced_code_blocks(text)
    found: list[tuple[int, str]] = []
    for match in _LINK_RE.finditer(cleaned):
        found.append((cleaned.count("\n", 0, match.start()) + 1, match.group(1) or match.group(2)))
    for match in _REF_DEF_RE.finditer(cleaned):
        found.append((cleaned.count("\n", 0, match.start()) + 1, match.group(1) or match.group(2)))
    return found


def resolve_markdown_link(md_path: Path, path_part: str, *, repo_root: Path) -> Path | None:
    if _is_external_or_anchor(path_part):
        return None
    path = Path(path_part)
    candidate = path.resolve() if path.is_absolute() else (md_path.parent / path).resolve()
    try:
        candidate.relative_to(repo_root.resolve())
    except ValueError:
        return None
    return candidate


def check_markdown_file_links(
    repo_root: Path,
    *,
    paths: list[Path] | None = None,
    skip_dirs: list[str] | None = None,
) -> list[str]:
    root = repo_root.resolve()
    md_files = paths if paths is not None else iter_markdown_files(repo_root, skip_dirs=skip_dirs)
    errors: list[str] = []
    for md_path in md_files:
        resolved_md = md_path if md_path.is_absolute() else (root / md_path).resolve()
        if not resolved_md.is_file():
            errors.append(f"{md_path}: markdown file not found")
            continue
        try:
            text = resolved_md.read_text(encoding="utf-8")
        except OSError as error:
            errors.append(f"{resolved_md.relative_to(root)}: read failed ({error})")
            continue
        for line_num, raw_target in extract_link_targets(text):
            path_part = _link_path_part(raw_target)
            target = resolve_markdown_link(resolved_md, path_part, repo_root=root)
            if target is None or target.exists():
                continue
            errors.append(
                f"{resolved_md.relative_to(root)}:{line_num}: broken link target {path_part!r} -> {target.relative_to(root)}"
            )
    return errors


def run(*, repo_root: Path, skip_dirs: list[str] | None = None, **_kwargs: object) -> list[str]:
    return check_markdown_file_links(repo_root, skip_dirs=skip_dirs)
