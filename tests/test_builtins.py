from __future__ import annotations

from pathlib import Path
from typing import Any, cast

from lex.builtins.dotenv_format import (
    check_env_files_match_sample,
    collect_env_values,
    parse_env_assignment,
    render_env_file,
)
from lex.builtins.dotenv_format import (
    run as run_dotenv_format,
)
from lex.builtins.file_structure import (
    StructureChecker,
    normalize_packages,
)
from lex.builtins.file_structure import (
    run as run_file_structure,
)
from lex.builtins.markdown_links import (
    check_markdown_file_links,
    extract_link_targets,
    iter_markdown_files,
    resolve_markdown_link,
    strip_fenced_code_blocks,
)


def test_dotenv_format_checks_explicit_pairs(tmp_path: Path) -> None:
    (tmp_path / ".env.main.sample").write_text("A=sample\nB=sample\n", encoding="utf-8")
    (tmp_path / ".env.main").write_text("B=target\nA=target\n", encoding="utf-8")

    errors = check_env_files_match_sample(tmp_path, src=".env.main.sample", tgt=".env.main")

    assert len(errors) == 1
    assert ".env.main" in errors[0]


def test_dotenv_format_parses_and_renders_assignments() -> None:
    assert parse_env_assignment(" A = value ") == ("A", "value")
    assert parse_env_assignment("# A=value") is None
    assert collect_env_values(["A=1", "A=2"]) == {"A": "2"}
    assert render_env_file(["A=sample", "", "# comment", "B=sample"], ["A=target"]) == [
        "A=target",
        "",
        "# comment",
        "B=sample",
    ]


def test_dotenv_format_discovers_targets_and_applies_fix(tmp_path: Path) -> None:
    (tmp_path / ".env.sample").write_text("A=sample\nB=sample\n", encoding="utf-8")
    target = tmp_path / ".env.local"
    target.write_text("B=target\nA=target\nEXTRA=1\n", encoding="utf-8")

    errors = check_env_files_match_sample(tmp_path, fix=True)

    assert errors == []
    assert target.read_text(encoding="utf-8") == "A=target\nB=target\nEXTRA=1\n"


def test_dotenv_format_validates_paths_and_pairs(tmp_path: Path) -> None:
    assert check_env_files_match_sample(tmp_path, src="") == ["src must be a non-empty path when provided"]
    assert check_env_files_match_sample(tmp_path, src=cast("Any", 123)) == ["src must be a path (str or Path), got int"]
    assert run_dotenv_format(repo_root=tmp_path, pairs="bad") == ["pairs must be a list of mappings"]
    assert run_dotenv_format(repo_root=tmp_path, pairs=["bad"]) == ["pairs[0] must be a mapping"]
    assert run_dotenv_format(repo_root=tmp_path, pairs=[{}]) == ["pairs[0].src is required"]
    assert run_dotenv_format(repo_root=tmp_path, pairs=[{"src": ".env.sample"}]) == ["pairs[0].tgt is required"]


def test_dotenv_format_reports_missing_source_target_and_no_targets(tmp_path: Path) -> None:
    assert "Source file not found" in check_env_files_match_sample(tmp_path)[0]

    sample = tmp_path / ".env.sample"
    sample.write_text("A=1\n", encoding="utf-8")
    assert check_env_files_match_sample(tmp_path) == [
        f"No top-level .env* files found to check (source excluded: {sample.name})"
    ]
    assert "Target file not found" in check_env_files_match_sample(tmp_path, tgt=".env.local")[0]


def test_markdown_links_reports_missing_relative_target(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("[missing](./missing.md)\n", encoding="utf-8")

    errors = check_markdown_file_links(tmp_path)

    assert len(errors) == 1
    assert "broken link" in errors[0]


def test_markdown_links_skips_code_fences_external_anchors_and_dirs(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text(
        "[external](https://example.com)\n[anchor](#section)\n```md\n[ignored](./missing.md)\n```\n",
        encoding="utf-8",
    )
    ignored = tmp_path / "ignored"
    ignored.mkdir()
    (ignored / "SKIP.md").write_text("[missing](./missing.md)\n", encoding="utf-8")

    assert check_markdown_file_links(tmp_path, skip_dirs=["ignored"]) == []
    assert iter_markdown_files(tmp_path, skip_dirs=["ignored"]) == [tmp_path / "README.md"]


def test_markdown_links_extracts_inline_angle_and_reference_targets() -> None:
    text = "[one](<docs/a b.md>)\n[ref]: ./target.md\n"

    assert extract_link_targets(text) == [(1, "docs/a b.md"), (2, "./target.md")]


def test_markdown_links_resolves_only_repo_local_file_targets(tmp_path: Path) -> None:
    md_path = tmp_path / "README.md"
    md_path.write_text("ok\n", encoding="utf-8")

    assert resolve_markdown_link(md_path, "https://example.com", repo_root=tmp_path) is None
    assert resolve_markdown_link(md_path, "../outside.md", repo_root=tmp_path) is None
    assert resolve_markdown_link(md_path, "./target.md", repo_root=tmp_path) == (tmp_path / "target.md").resolve()


def test_markdown_links_reports_missing_path_argument(tmp_path: Path) -> None:
    assert check_markdown_file_links(tmp_path, paths=[Path("missing.md")]) == ["missing.md: markdown file not found"]
    assert strip_fenced_code_blocks("a\n~~~\nb\n~~~\nc\n") == "a\nc\n"


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


def test_file_structure_normalizes_config_errors() -> None:
    assert normalize_packages(None) == (None, "args.packages must be a non-empty list")
    assert normalize_packages(["bad"]) == (None, "packages[0] must be a mapping")
    assert normalize_packages([{}]) == (None, "packages[0] missing required key 'dir'")
    assert normalize_packages(
        [
            {
                "dir": "cli",
                "file_suffix": "_command.py",
                "class_suffix": "Command",
                "validator": "cli",
            }
        ]
    ) == (None, "packages[0].cli_root_allowed_files must be non-empty strings")


def test_file_structure_reports_missing_src_and_package_dir(tmp_path: Path) -> None:
    assert run_file_structure(src_dir=tmp_path / "missing", packages=[]) == ["args.packages must be a non-empty list"]

    src = tmp_path / "src"
    src.mkdir()
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

    assert errors == [f"Directory not found: {src / 'services'}"]


def test_file_structure_validates_class_and_function_patterns(tmp_path: Path) -> None:
    src = tmp_path / "src"
    services = src / "services"
    jobs = src / "jobs"
    services.mkdir(parents=True)
    jobs.mkdir()
    (services / "search.py").write_text("class Other:\n    pass\n", encoding="utf-8")
    (jobs / "daily_job.py").write_text("def daily_job():\n    pass\n", encoding="utf-8")

    class_errors = run_file_structure(
        src_dir=src,
        packages=[
            {
                "dir": "services",
                "file_suffix": ".py",
                "class_suffix": "Service",
                "validator": "class_pattern",
            },
        ],
    )
    function_errors = run_file_structure(
        src_dir=src,
        packages=[
            {
                "dir": "jobs",
                "file_suffix": "_job.py",
                "class_suffix": "Job",
                "validator": "function_pattern",
            },
        ],
    )

    assert "expected class ending with 'Service' not found" in class_errors[0]
    assert "expected functions daily_job_async not found" in function_errors[0]


def test_file_structure_reports_parse_errors(tmp_path: Path) -> None:
    path = tmp_path / "bad.py"
    path.write_text("def nope(:\n", encoding="utf-8")
    checker = StructureChecker(tmp_path, [])

    assert "cannot parse file" in checker._validate_class_pattern(path, "Service")[0]
    assert "cannot parse file" in checker._validate_function_pattern(path, "Job")[0]
    assert "cannot parse file" in checker._validate_cli_command_decorators(path)[0]


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


def test_file_structure_cli_validates_root_commands_and_nested_files(tmp_path: Path) -> None:
    src = tmp_path / "src"
    cli = src / "cli"
    commands = cli / "commands"
    other = cli / "other"
    commands.mkdir(parents=True)
    other.mkdir()
    (cli / "extra.py").write_text("pass\n", encoding="utf-8")
    (commands / "bad.py").write_text("pass\n", encoding="utf-8")
    (commands / "good_command.py").write_text("def run():\n    pass\n", encoding="utf-8")
    (other / "hidden.py").write_text("pass\n", encoding="utf-8")

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

    assert any("unexpected file in" in error for error in errors)
    assert any("file name must end with '_command.py'" in error for error in errors)
    assert any("command file should contain a function decorated" in error for error in errors)
    assert any("unexpected file outside commands/" in error for error in errors)


def test_file_structure_cli_accepts_command_decorator(tmp_path: Path) -> None:
    src = tmp_path / "src"
    commands = src / "cli" / "commands"
    commands.mkdir(parents=True)
    (src / "cli" / "app.py").write_text("pass\n", encoding="utf-8")
    (commands / "__init__.py").write_text("import click\n\ngroup = click.group()\n", encoding="utf-8")
    (commands / "run_command.py").write_text(
        "class group:\n"
        "    @staticmethod\n"
        "    def command():\n"
        "        return lambda fn: fn\n"
        "\n"
        "@group.command()\n"
        "def run():\n"
        "    pass\n",
        encoding="utf-8",
    )

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

    assert errors == []
