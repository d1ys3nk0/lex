from __future__ import annotations

from pathlib import Path

from lex.cli import load_config, main, parse_cli_value, parse_passthrough_args, run_checks


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


def test_parse_passthrough_args_reports_invalid_tokens() -> None:
    parsed, errors = parse_passthrough_args(["extra", "--Bad", "value", "--flag"])

    assert parsed == {"flag": True}
    assert errors == [
        "unexpected trailing argument 'extra'; expected --key value or --key=value",
        "invalid option name 'Bad'",
    ]


def test_parse_cli_value_falls_back_to_raw_on_invalid_yaml() -> None:
    assert parse_cli_value("[") == "["


def test_load_config_validates_top_level_shape_and_unknown_keys(tmp_path: Path) -> None:
    missing = tmp_path / "missing.yml"
    assert load_config(missing) == ([], [f"{missing}: config file not found"])

    config = tmp_path / "lex.yml"
    config.write_text("- no\n", encoding="utf-8")
    assert load_config(config) == ([], [f"{config}: expected a top-level YAML mapping"])

    config.write_text("---\nunknown: true\nchecks: []\n", encoding="utf-8")
    assert load_config(config) == ([], [f"{config}: unknown keys: unknown"])


def test_load_config_validates_check_items(tmp_path: Path) -> None:
    config = tmp_path / "lex.yml"
    config.write_text(
        "---\nchecks:\n  - bad\n  - name: Bad\n  - name: ok\n    args: []\n  - name: ok\n  - name: ok\n",
        encoding="utf-8",
    )

    checks, errors = load_config(config)

    assert len(checks) == 1
    assert checks[0].name == "ok"
    assert checks[0].args == {}
    assert errors == [
        f"{config}: checks[0]: must be a mapping",
        f"{config}: checks[1]: name must match ^[a-z][a-z0-9_]*$",
        f"{config}: checks[2]: args must be a mapping when provided",
        f"{config}: checks[4]: duplicate check name 'ok'",
    ]


def test_load_config_accepts_null_args(tmp_path: Path) -> None:
    config = tmp_path / "lex.yml"
    config.write_text("---\nchecks:\n  - name: markdown_links\n    args:\n", encoding="utf-8")

    checks, errors = load_config(config)

    assert errors == []
    assert len(checks) == 1
    assert checks[0].args == {}


def test_run_checks_reports_unknown_only_with_configured_checks(tmp_path: Path) -> None:
    config = tmp_path / "lex.yml"
    config.write_text("---\nchecks:\n  - name: markdown_links\n", encoding="utf-8")

    errors = run_checks(config_path=config, source_dir=None, only="dotenv_format")

    assert errors == [f"{config.resolve()}: unknown check 'dotenv_format' (configured: markdown_links)"]


def test_run_checks_reports_unregistered_check_path(tmp_path: Path) -> None:
    config = tmp_path / "lex.yml"
    config.write_text("---\nchecks:\n  - name: custom_check\n", encoding="utf-8")

    errors = run_checks(config_path=config, source_dir=None)

    assert errors == [
        f"{config.resolve()}: check 'custom_check' is not built in and no {tmp_path / '.lex/custom_check.py'} exists"
    ]


def test_run_checks_reports_custom_source_file_path(tmp_path: Path) -> None:
    source = tmp_path / ".lex"
    source.write_text("not a directory\n", encoding="utf-8")
    config = tmp_path / "lex.yml"
    config.write_text("---\nchecks: []\n", encoding="utf-8")

    assert run_checks(config_path=config, source_dir=source) == [f"{source}: source path is not a directory"]


def test_run_checks_reports_custom_import_and_contract_errors(tmp_path: Path) -> None:
    source = tmp_path / ".lex"
    source.mkdir()
    (source / "broken.py").write_text("raise RuntimeError('boom')\n", encoding="utf-8")
    (source / "missing_run.py").write_text("VALUE = 1\n", encoding="utf-8")
    config = tmp_path / "lex.yml"
    config.write_text("---\nchecks: []\n", encoding="utf-8")

    errors = run_checks(config_path=config, source_dir=source)

    assert errors == [
        f"{source / 'broken.py'}: failed to import custom check (boom)",
        f"{source / 'missing_run.py'}: custom check must define callable run()",
    ]


def test_run_checks_reports_runtime_and_return_contract_errors(tmp_path: Path) -> None:
    source = tmp_path / ".lex"
    source.mkdir()
    (source / "bad_return.py").write_text("def run(**_args):\n    return 'bad'\n", encoding="utf-8")
    (source / "raises.py").write_text("def run(**_args):\n    raise RuntimeError('boom')\n", encoding="utf-8")
    config = tmp_path / "lex.yml"
    config.write_text("---\nchecks:\n  - name: bad_return\n  - name: raises\n", encoding="utf-8")

    errors = run_checks(config_path=config, source_dir=source)

    assert errors == [
        "bad_return: run() must return list[str]",
        "raises: check execution failed (boom)",
    ]


def test_run_checks_does_not_double_prefix_file_structure_validation(tmp_path: Path) -> None:
    config = tmp_path / "lex.yml"
    config.write_text("---\nchecks:\n  - name: file_structure\n", encoding="utf-8")

    errors = run_checks(config_path=config, source_dir=None)

    assert errors == ["file_structure: args.packages must be a non-empty list"]


def test_main_returns_error_for_bad_passthrough(capsys) -> None:  # noqa: ANN001
    assert main(["--bad-option", "--Bad"]) == 2

    assert "invalid option name 'Bad'" in capsys.readouterr().err


def test_main_returns_success_for_clean_config(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("ok\n", encoding="utf-8")
    config = tmp_path / "lex.yml"
    config.write_text("---\nchecks:\n  - name: markdown_links\n", encoding="utf-8")

    assert main(["--config", str(config)]) == 0
