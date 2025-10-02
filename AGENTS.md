# Repository Guidelines

## Project Structure & Module Organization
- Core package lives in `pdf2zh_next/` with CLI entrypoints in `main.py` and the FastAPI service in `http_api.py`.
- Translation engines sit in `pdf2zh_next/translator/`, shared helpers in `pdf2zh_next/utils/`, and config schemas in `pdf2zh_next/config/`.
- Static assets (templates, UI strings) live in `pdf2zh_next/assets/` and `pdf2zh_next/gui_translation.yaml`.
- Documentation sources are in `docs/` (see `mkdocs.yml`), while Docker and packaging assets live under `Dockerfile` and `script/`.
- Tests belong in `tests/`; legacy experiments remain in `test/`—prefer `tests/` for new coverage.

## Build, Test, and Development Commands
- Install runtime and dev dependencies with `uv sync --dev` from the project root.
- Run the CLI locally using `uv run pdf2zh --help`; launch the HTTP API via `uv run uvicorn pdf2zh_next.http_api:app --reload`.
- Start the Gradio web UI with `uv run python pdf2zh_next/gui.py` to verify interactive flows.
- Enforce style before committing: `uv run ruff check` and `uv run ruff format --check` (or `uv run pre-commit run --all-files`).
- Execute the test suite using `uv run pytest`; narrow focus with `uv run pytest tests/config/test_main.py -k initialize_config` when iterating.

## Coding Style & Naming Conventions
- Target Python 3.10+ with 4-space indentation and snake_case module, file, and config key names.
- Ruff governs linting/formatting (line length 88) with additional ignores in `setup.cfg`; keep patches compliant or add scoped overrides.
- Prefer explicit exceptions over silent failures; align new configuration fields with existing patterns in `pdf2zh_next/config` and update translations alongside code changes.

## Testing Guidelines
- Mirror package structure under `tests/` and name files `test_<feature>.py` with descriptive test functions.
- Reuse fixtures from `tests/config/conftest.py` for environment setup and extend them instead of duplicating logic.
- For translator integrations, add regression checks similar to `tests/config/test_model.py` that assert validation and error messages.
- Include FastAPI or CLI smoke tests when user-facing behavior changes to prevent regressions.

## Commit & Pull Request Guidelines
- Follow the conventional prefixes observed in history (`feat:`, `fix:`, `docs:`, `refactor:`) and keep subject lines under ~72 characters.
- Keep commits scoped; update user docs or configuration examples whenever behavior changes.
- Pull requests should outline intent, list verification commands, link issues, and attach UI/API snapshots when helpful.
- Use draft PRs while work is in progress and mark ready only after tests and linting pass.
