from __future__ import annotations

from collections.abc import Callable

from lex.builtins import dotenv_format, file_structure, markdown_links


BUILTIN_CHECKS: dict[str, Callable[..., list[str]]] = {
    "dotenv_format": dotenv_format.run,
    "file_structure": file_structure.run,
    "markdown_links": markdown_links.run,
}
