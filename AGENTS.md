# Agent instructions

## Python
- Always use `uv` to manage Python libraries and run scripts (`uv add`, `uv run`). No bare `pip install`.
- The project venv is `.venv/` in the repo root (Python 3.12, from `pyproject.toml` + `uv.lock`). Recreate it with `uv sync`.

## Git
- Do not add AI attribution to commits or PRs: no `Co-Authored-By` trailers, no "Generated with ..." lines. Commits are authored by the repo owner only.
