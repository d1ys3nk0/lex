from __future__ import annotations

from pathlib import Path

from lex.cli import parse_passthrough_args, run_checks


def test_run_checks_uses_root_config_and_default_missing_source(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("[ok](./target.md)\n", encoding="utf-8")
    (tmp_path / "target.md").write_text("ok\n", encoding="utf-8")
    config = tmp_path / "lex.yml"
    config.write_text("---\n\nchecks:\n  - name: markdown_links\n", encoding="utf-8")

    assert run_checks(config_path=config, source_dir=None) == []


def test_custom_check_receives_repo_root_src_dir_and_yaml_cli_args(tmp_path: Path) -> None:
    source = tmp_path / ".lex"
    source.mkdir()
    (source / "custom_check.py").write_text(
        "def run(*, repo_root, src_dir, flag=False, count=0, **_args):\n"
        "    assert repo_root.name == 'repo'\n"
        "    assert src_dir == repo_root / 'src'\n"
        "    return [] if flag and count == 3 else ['bad args']\n",
        encoding="utf-8",
    )
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".lex").symlink_to(source, target_is_directory=True)
    config = repo / "lex.yml"
    config.write_text("---\n\nchecks:\n  - name: custom_check\n", encoding="utf-8")

    errors = run_checks(config_path=config, source_dir=None, cli_args={"flag": True, "count": 3})

    assert errors == []


def test_custom_builtin_collision_fails_before_running(tmp_path: Path) -> None:
    source = tmp_path / ".lex"
    source.mkdir()
    marker = tmp_path / "ran"
    (source / "markdown_links.py").write_text(
        f"def run(**_args):\n    __import__('pathlib').Path({str(marker)!r}).write_text('x')\n    return []\n",
        encoding="utf-8",
    )
    config = tmp_path / "lex.yml"
    config.write_text("---\n\nchecks:\n  - name: markdown_links\n", encoding="utf-8")

    errors = run_checks(config_path=config, source_dir=source)

    assert any("collides with built-in check" in error for error in errors)
    assert not marker.exists()


def test_parse_passthrough_args_supports_yaml_scalars() -> None:
    parsed, errors = parse_passthrough_args(["--fix", "--count", "3", "--name=abc", "--enabled=false"])

    assert errors == []
    assert parsed == {"fix": True, "count": 3, "name": "abc", "enabled": False}
