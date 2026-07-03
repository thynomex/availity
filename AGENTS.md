# Agent Instructions

## Package Manager
- Use Python/pip: `pip install -r requirements.txt`
- Project metadata lives in `pyproject.toml`; runtime dependencies also mirror `requirements.txt`.
- Entry points: `python -m src.cli`, `run.bat`, or `dist\availity.exe`.

## File-Scoped Commands
| Task | Command |
|------|---------|
| Compile file | `python -m py_compile src\cli.py` |
| Compile core | `python -m py_compile src\checker.py src\providers.py src\rate_limiter.py` |
| Test file | `pytest -q tests\test_checker.py` |
| Test module slice | `pytest -q tests\test_validator.py tests\test_rate_limiter.py` |
| Full tests | `pytest -q` |
| Build EXE | `python -m PyInstaller --noconfirm --clean availity.spec` |

## Project Shape
- `src\cli.py`: Rich terminal UI, banner animation, menu flow, startup, export/resume orchestration.
- `src\checker.py`: async batch processing, retry flow, DB updates, `TokenPool` integration.
- `src\providers.py`: Discord provider, token validation, single-token request execution, webhook notifications.
- `src\rate_limiter.py`: semaphore concurrency and token cooldown/dead-token state.
- `src\database.py`: SQLite schema and persistence for candidates, checks, settings, run history.
- `src\generator.py`, `src\validator.py`, `src\exporter.py`: candidate generation, validation, result exports.

## Key Conventions
- Preserve the `Availity` brand and `Made by 9apf.` credit unless explicitly asked.
- Keep banner art ASCII-only; escape backslashes inside Python triple-quoted strings.
- Keep loading/status screens free of the subtitle by using `show_subtitle=False`.
- `UsernameChecker` requires `TokenPool`; tests should instantiate `UsernameChecker(config, provider, db, rate_limiter, token_pool)`.
- Prefer `DiscordProvider.check_with_token()` for checker paths; `check_username()` is legacy compatibility.
- Maintain async patterns with `pytest.mark.asyncio` for async tests.

## Sensitive And Generated Files
- Do not commit or package personal `.env`, `tokens.txt`, `data\*.db*`, `logs\*.log`, or `output\*`.
- Do not edit `reference\` unless explicitly asked; it is legacy/reference material.
- Treat `build\`, `dist\`, `.pytest_cache\`, `__pycache__\`, and `.coverage` as generated artifacts.
- Clean release bundles should include `dist\availity.exe`, `.env.example`, `README.md`, and license/terms files only.

## Verification Notes
- Current baseline: `pytest -q` passes, with known `datetime.utcnow()` deprecation warnings.
- Rebuild `dist\availity.exe` after user-facing CLI or packaging changes.
