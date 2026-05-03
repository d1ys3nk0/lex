# Lex

Lex is a small SIP lint runner for Python repositories.

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
