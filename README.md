# Lex

Lex is a small SIP lint runner for Python repositories.

Source: <https://github.com/d1ys3nk0/lex>

It reads a root `lex.yml` file:

```yaml
---

checks:
  - name: markdown_links
  - name: dotenv_format
    args:
      pairs:
        - src: .env.main.sample
          tgt: .env.main
```

Run it from a repository root:

```sh
uv run lex -c lex.yml
uv run lex -s .lex -c lex.yml
uv run lex -c lex.yml --only markdown_links
uv run lex -c lex.yml --only dotenv_format --fix true
```

Built-in checks:

- `dotenv_format`: validates `.env*` files against sample structure.
- `file_structure`: validates configured `src/` subpackage naming and layout.
- `markdown_links`: validates relative Markdown link targets.

Custom checks live at `.lex/<check_name>.py` and expose:

```python
def run(*, repo_root, src_dir, **args) -> list[str]:
    return []
```

Custom check names must not collide with built-in names.

## Install

```sh
uv tool install git+https://github.com/d1ys3nk0/lex.git
```

Docker images are published to GHCR on `main`:

```sh
docker run --rm ghcr.io/d1ys3nk0/lex:latest
```

## Development

```sh
uv sync --frozen
uv run ruff check .
uv run ruff format --check .
uv run ty check
uv run pytest --cov=src --cov-fail-under=90
uv build --no-sources
```
