from __future__ import annotations

import argparse
import importlib.util
import re
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any, cast

import yaml

from lex.checks import BUILTIN_CHECKS


CHECK_NAME_RE = re.compile(r"^[a-z][a-z0-9_]*$")


@dataclass(frozen=True)
class CheckConfig:
    name: str
    args: dict[str, Any]


def parse_cli_value(raw: str) -> Any:
    try:
        return yaml.safe_load(raw)
    except yaml.YAMLError:
        return raw


def parse_passthrough_args(argv: list[str]) -> tuple[dict[str, Any], list[str]]:
    parsed: dict[str, Any] = {}
    errors: list[str] = []
    index = 0
    while index < len(argv):
        token = argv[index]
        if not token.startswith("--") or token == "--":
            errors.append(f"unexpected trailing argument {token!r}; expected --key value or --key=value")
            index += 1
            continue
        raw_key = token[2:]
        if "=" in raw_key:
            key, raw_value = raw_key.split("=", 1)
            index += 1
        else:
            key = raw_key
            if index + 1 < len(argv) and not argv[index + 1].startswith("--"):
                raw_value = argv[index + 1]
                index += 2
            else:
                raw_value = "true"
                index += 1
        key = key.replace("-", "_")
        if not CHECK_NAME_RE.match(key):
            errors.append(f"invalid option name {key!r}")
            continue
        parsed[key] = parse_cli_value(raw_value)
    return parsed, errors


def load_config(config_path: Path) -> tuple[list[CheckConfig], list[str]]:
    if not config_path.is_file():
        return [], [f"{config_path}: config file not found"]
    try:
        raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    except Exception as error:
        return [], [f"{config_path}: failed to read config ({error})"]
    if not isinstance(raw, dict):
        return [], [f"{config_path}: expected a top-level YAML mapping"]
    unknown = sorted(set(raw) - {"checks"})
    if unknown:
        return [], [f"{config_path}: unknown keys: {', '.join(unknown)}"]
    checks_raw = raw.get("checks")
    if not isinstance(checks_raw, list):
        return [], [f"{config_path}: checks must be a list"]

    checks: list[CheckConfig] = []
    errors: list[str] = []
    seen: set[str] = set()
    for index, item in enumerate(checks_raw):
        location = f"{config_path}: checks[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{location}: must be a mapping")
            continue
        check_item = cast("dict[str, object]", item)
        unknown_item = sorted(set(check_item) - {"name", "args"})
        if unknown_item:
            errors.append(f"{location}: unknown keys: {', '.join(unknown_item)}")
            continue
        name = check_item.get("name")
        if not isinstance(name, str) or not CHECK_NAME_RE.match(name):
            errors.append(f"{location}: name must match ^[a-z][a-z0-9_]*$")
            continue
        args_raw = check_item.get("args", {})
        if args_raw is None:
            args: dict[str, Any] = {}
        elif isinstance(args_raw, dict):
            args = cast("dict[str, Any]", args_raw)
        else:
            errors.append(f"{location}: args must be a mapping when provided")
            continue
        if name in seen:
            errors.append(f"{location}: duplicate check name {name!r}")
            continue
        seen.add(name)
        checks.append(CheckConfig(name=name, args=args))
    return checks, errors


def _load_module(path: Path, module_name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        msg = f"cannot load module spec for {path}"
        raise ImportError(msg)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        sys.modules.pop(module_name, None)
        raise
    return module


def load_custom_checks(source_dir: Path) -> tuple[dict[str, Callable[..., list[str]]], list[str]]:
    if not source_dir.exists():
        return {}, []
    if not source_dir.is_dir():
        return {}, [f"{source_dir}: source path is not a directory"]
    checks: dict[str, Callable[..., list[str]]] = {}
    errors: list[str] = []
    for path in sorted(source_dir.glob("*.py")):
        name = path.stem
        if name.endswith("_test") or name == "conftest":
            continue
        if not CHECK_NAME_RE.match(name):
            continue
        if name in BUILTIN_CHECKS:
            errors.append(f"{path}: custom check collides with built-in check {name!r}")
            continue
        try:
            module = _load_module(path, f"_lex_custom_{name}")
        except Exception as error:
            errors.append(f"{path}: failed to import custom check ({error})")
            continue
        run = getattr(module, "run", None)
        if not callable(run):
            errors.append(f"{path}: custom check must define callable run()")
            continue
        checks[name] = cast("Callable[..., list[str]]", run)
    return checks, errors


def run_checks(
    *,
    config_path: Path,
    source_dir: Path | None,
    only: str | None = None,
    cli_args: dict[str, Any] | None = None,
) -> list[str]:
    resolved_config = config_path.resolve()
    repo_root = resolved_config.parent
    src_dir = (repo_root / "src").resolve()
    custom_source = (
        (repo_root / ".lex").resolve()
        if source_dir is None
        else (source_dir if source_dir.is_absolute() else repo_root / source_dir).resolve()
    )

    configs, config_errors = load_config(resolved_config)
    custom_checks, custom_errors = load_custom_checks(custom_source)
    if config_errors or custom_errors:
        return config_errors + custom_errors

    registry: dict[str, Callable[..., list[str]]] = {**BUILTIN_CHECKS, **custom_checks}
    selected = configs
    if only is not None:
        selected = [check for check in configs if check.name == only]
        if not selected:
            available = ", ".join(check.name for check in configs) or "(none)"
            return [f"{resolved_config}: unknown check {only!r} (configured: {available})"]

    errors: list[str] = []
    for check in selected:
        fn = registry.get(check.name)
        if fn is None:
            errors.append(
                f"{resolved_config}: check {check.name!r} is not built in and no {custom_source / f'{check.name}.py'} exists"
            )
            continue
        args = {**check.args, **(cli_args or {})}
        try:
            result = fn(repo_root=repo_root, src_dir=src_dir, **args)
        except Exception as error:
            errors.append(f"{check.name}: check execution failed ({error})")
            continue
        if not isinstance(result, list) or not all(isinstance(item, str) for item in result):
            errors.append(f"{check.name}: run() must return list[str]")
            continue
        errors.extend(f"{check.name}: {entry}" for entry in result)
    return errors


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run SIP Lex lint checks")
    parser.add_argument("-c", "--config", default="lex.yml", help="Path to lex.yml")
    parser.add_argument("-s", "--source", default=None, help="Custom check directory, default .lex next to config")
    parser.add_argument("--only", help="Run only one configured check by name")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    known, trailing = parser.parse_known_args(argv)
    cli_args, cli_errors = parse_passthrough_args(trailing)
    if cli_errors:
        for error in cli_errors:
            print(error, file=sys.stderr)
        return 2
    errors = run_checks(
        config_path=Path(known.config),
        source_dir=Path(known.source) if known.source is not None else None,
        only=known.only,
        cli_args=cli_args,
    )
    for error in errors:
        print(error, file=sys.stderr)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
