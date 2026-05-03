from __future__ import annotations

from pathlib import Path

from lex.builtins.dotenv_format import check_env_files_match_sample
from lex.builtins.file_structure import run as run_file_structure
from lex.builtins.markdown_links import check_markdown_file_links


def test_dotenv_format_checks_explicit_pairs(tmp_path: Path) -> None:
    (tmp_path / ".env.main.sample").write_text("A=sample\nB=sample\n", encoding="utf-8")
    (tmp_path / ".env.main").write_text("B=target\nA=target\n", encoding="utf-8")

    errors = check_env_files_match_sample(tmp_path, src=".env.main.sample", tgt=".env.main")

    assert len(errors) == 1
    assert ".env.main" in errors[0]


def test_markdown_links_reports_missing_relative_target(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("[missing](./missing.md)\n", encoding="utf-8")

    errors = check_markdown_file_links(tmp_path)

    assert len(errors) == 1
    assert "broken link" in errors[0]


def test_file_structure_validates_configured_package(tmp_path: Path) -> None:
    src = tmp_path / "src"
    services = src / "services"
    services.mkdir(parents=True)
    (services / "search_service.py").write_text("class SearchService:\n    pass\n", encoding="utf-8")

    errors = run_file_structure(
        src_dir=src,
        packages=[
            {
                "dir": "services",
                "file_suffix": "_service.py",
                "class_suffix": "Service",
                "validator": "class_pattern",
            },
        ],
    )

    assert errors == []


def test_file_structure_cli_requires_group_in_commands_init(tmp_path: Path) -> None:
    src = tmp_path / "src"
    commands = src / "cli" / "commands"
    commands.mkdir(parents=True)
    (src / "cli" / "app.py").write_text("import click\n\n@click.group()\ndef app():\n    pass\n", encoding="utf-8")
    (commands / "__init__.py").write_text("", encoding="utf-8")

    errors = run_file_structure(
        src_dir=src,
        packages=[
            {
                "dir": "cli",
                "file_suffix": "_command.py",
                "class_suffix": "Command",
                "validator": "cli",
                "cli_root_allowed_files": ["app.py"],
                "cli_commands_subdir": "commands",
            },
        ],
    )

    assert len(errors) == 1
    assert "__init__.py should define a click group" in errors[0]
