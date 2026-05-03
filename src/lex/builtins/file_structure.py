from __future__ import annotations

import ast
import os
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast


@dataclass(frozen=True)
class ValidationRule:
    suffix: str
    class_suffix: str
    validator: Callable[[Path, str], list[str]]


@dataclass(frozen=True)
class PackageConfig:
    dir: str
    file_suffix: str
    class_suffix: str
    validator: str
    cli_root_allowed_files: tuple[str, ...]
    cli_commands_subdir: str


def normalize_packages(packages: object) -> tuple[list[PackageConfig] | None, str | None]:
    if not isinstance(packages, list) or not packages:
        return (None, "args.packages must be a non-empty list")
    valid_kinds = frozenset({"class_pattern", "cli", "function_pattern"})
    result: list[PackageConfig] = []
    for index, raw_item in enumerate(packages):
        if not isinstance(raw_item, dict):
            return (None, f"packages[{index}] must be a mapping")
        item: dict[str, Any] = cast("dict[str, Any]", raw_item)
        try:
            dir_name = item["dir"]
            file_suffix = item["file_suffix"]
            class_suffix = item["class_suffix"]
            validator = item["validator"]
        except KeyError as error:
            return (None, f"packages[{index}] missing required key {error.args[0]!r}")
        if not isinstance(dir_name, str) or not dir_name:
            return (None, f"packages[{index}].dir must be a non-empty string")
        if not isinstance(file_suffix, str) or not file_suffix:
            return (None, f"packages[{index}].file_suffix must be a non-empty string")
        if not isinstance(class_suffix, str) or not class_suffix:
            return (None, f"packages[{index}].class_suffix must be a non-empty string")
        if not isinstance(validator, str) or validator not in valid_kinds:
            return (None, f"packages[{index}].validator must be one of {sorted(valid_kinds)}")

        allowed: tuple[str, ...] = ()
        commands_subdir = ""
        if validator == "cli":
            raw_allowed = item.get("cli_root_allowed_files")
            if (
                not isinstance(raw_allowed, list)
                or not raw_allowed
                or not all(isinstance(x, str) and x for x in raw_allowed)
            ):
                return (None, f"packages[{index}].cli_root_allowed_files must be non-empty strings")
            allowed = tuple(raw_allowed)
            raw_subdir = item.get("cli_commands_subdir")
            if not isinstance(raw_subdir, str) or not raw_subdir:
                return (None, f"packages[{index}] (cli) requires cli_commands_subdir string")
            commands_subdir = raw_subdir

        result.append(
            PackageConfig(
                dir=dir_name,
                file_suffix=file_suffix,
                class_suffix=class_suffix,
                validator=validator,
                cli_root_allowed_files=allowed,
                cli_commands_subdir=commands_subdir,
            ),
        )
    return result, None


class StructureChecker:
    @staticmethod
    def _noop_validator(_path: Path, _class_suffix: str) -> list[str]:
        return []

    def __init__(self, base_dir: Path, package_configs: list[PackageConfig]) -> None:
        self.base_dir = base_dir
        validators: dict[str, Callable[[Path, str], list[str]]] = {
            "class_pattern": self._validate_class_pattern,
            "function_pattern": self._validate_function_pattern,
        }
        self._packages: list[tuple[PackageConfig, ValidationRule]] = []
        for pkg in package_configs:
            fn = StructureChecker._noop_validator if pkg.validator == "cli" else validators[pkg.validator]
            self._packages.append((pkg, ValidationRule(pkg.file_suffix, pkg.class_suffix, fn)))

    @staticmethod
    def _snake_to_pascal(name: str) -> str:
        return "".join(part.capitalize() for part in name.split("_") if part)

    def _validate_class_pattern(self, path: Path, expected_class_suffix: str) -> list[str]:
        base = path.name.removesuffix(".py")
        suffix_to_remove = "_" + expected_class_suffix.lower()
        without_suffix = (
            base[: -len(suffix_to_remove)] if base.endswith(suffix_to_remove) else "_".join(base.split("_")[:-1])
        )
        expected_class = self._snake_to_pascal(without_suffix or base) + expected_class_suffix
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError as error:
            return [f"{path}: cannot parse file ({error})"]
        class_names = {node.name for node in ast.walk(tree) if isinstance(node, ast.ClassDef)}
        if expected_class in class_names or any(name.endswith(expected_class_suffix) for name in class_names):
            return []
        return [
            f"{path}: expected class ending with '{expected_class_suffix}' not found; found classes: {', '.join(sorted(class_names)) or 'none'}"
        ]

    def _validate_function_pattern(self, path: Path, expected_suffix: str) -> list[str]:
        base_name = path.name.removesuffix(".py").removesuffix(f"_{expected_suffix.lower()}")
        expected_sync = f"{base_name}_{expected_suffix.lower()}"
        expected_async = f"{base_name}_{expected_suffix.lower()}_async"
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError as error:
            return [f"{path}: cannot parse file ({error})"]
        function_names = {
            node.name for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        missing = [name for name in (expected_sync, expected_async) if name not in function_names]
        if not missing:
            return []
        return [
            f"{path}: expected functions {', '.join(missing)} not found; found functions: {', '.join(sorted(function_names)) or 'none'}"
        ]

    @staticmethod
    def _validate_cli_command_decorators(path: Path) -> list[str]:
        try:
            content = path.read_text(encoding="utf-8")
            tree = ast.parse(content)
        except SyntaxError as error:
            return [f"{path}: cannot parse file ({error})"]
        if path.name == "__init__.py" and ("@click.group()" in content or "click.group()" in content):
            return []
        if path.name == "__init__.py":
            return [f"{path}: __init__.py should define a click group with @click.group()"]
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for decorator in node.decorator_list:
                if (
                    isinstance(decorator, ast.Call)
                    and isinstance(decorator.func, ast.Attribute)
                    and decorator.func.attr == "command"
                ):
                    return []
        return [f"{path}: command file should contain a function decorated with @group.command() or @click.command()"]

    def _validate_standard_directory(self, pkg: PackageConfig, rule: ValidationRule) -> list[str]:
        errors: list[str] = []
        dir_path = self.base_dir / pkg.dir
        if not dir_path.exists():
            return [f"Directory not found: {dir_path}"]
        for root, _dirs, files in os.walk(dir_path):
            for filename in files:
                if not filename.endswith(".py"):
                    continue
                path = Path(root) / filename
                if not filename.endswith(rule.suffix):
                    errors.append(f"{path}: file name must end with '{rule.suffix}'")
                    continue
                errors.extend(rule.validator(path, rule.class_suffix))
        return errors

    def _validate_cli_directory(self, pkg: PackageConfig, rule: ValidationRule) -> list[str]:
        errors: list[str] = []
        dir_path = self.base_dir / pkg.dir
        if not dir_path.exists():
            return [f"Directory not found: {dir_path}"]
        allowed_root = frozenset(pkg.cli_root_allowed_files)
        for root, _dirs, files in os.walk(dir_path):
            for filename in files:
                if not filename.endswith(".py"):
                    continue
                path = Path(root) / filename
                rel_parent = path.parent.relative_to(dir_path)
                if path.parent == dir_path:
                    if filename not in allowed_root:
                        errors.append(
                            f"{path}: unexpected file in {dir_path} (allowed: {', '.join(sorted(allowed_root))})"
                        )
                    continue
                if pkg.cli_commands_subdir in rel_parent.parts:
                    if filename == "__init__.py":
                        errors.extend(self._validate_cli_command_decorators(path))
                        continue
                    if not filename.endswith(rule.suffix):
                        errors.append(f"{path}: file name must end with '{rule.suffix}'")
                        continue
                    errors.extend(self._validate_cli_command_decorators(path))
                    continue
                errors.append(f"{path}: unexpected file outside {pkg.cli_commands_subdir}/")
        return errors

    def validate_all(self) -> list[str]:
        errors: list[str] = []
        for pkg, rule in self._packages:
            if pkg.validator == "cli":
                errors.extend(self._validate_cli_directory(pkg, rule))
            else:
                errors.extend(self._validate_standard_directory(pkg, rule))
        return errors


def run(*, src_dir: Path, packages: object | None = None, **_kwargs: object) -> list[str]:
    normalized, error = normalize_packages(packages)
    if error is not None:
        return [error]
    if not src_dir.is_dir():
        return [f"src_dir not found: {src_dir}"]
    return StructureChecker(src_dir, normalized or []).validate_all()
