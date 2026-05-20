# Availity

Windows CLI tool for checking username availability, generating candidates, scanning wordlists, resuming interrupted runs, and exporting results.

Made by 9apf.

## Quick Start

### Run The Windows EXE

Use this if you downloaded a packaged release.

1. Open the release folder.
2. Copy `.env.example` to `.env` if `.env` does not already exist.
3. Add your token or token file path in `.env`.
4. Double-click `availity.exe`.

The app opens in a terminal window and shows the main menu.

### Run From Source

Use this if you are running the project folder directly.

1. Install Python 3.11 or newer.
2. Open a terminal in the project folder.
3. Install dependencies:

```powershell
pip install -r requirements.txt
```

4. Copy `.env.example` to `.env` and edit your settings.
5. Start the app:

```powershell
python -m src.cli
```

You can also double-click `run.bat` from the project folder.

## Configuration

Settings are controlled through `.env`.

Important fields:

- `DISCORD_TOKEN`: single token mode.
- `DISCORD_TOKENS_FILE`: path to a token list file, usually `tokens.txt`.
- `DISCORD_MULTI_TOKEN`: set to `true` to use multiple tokens from the token file.
- `DISCORD_WEBHOOK_URL`: optional webhook for available-name notifications.
- `CONCURRENCY`: number of simultaneous workers.
- `REQUEST_DELAY`: delay between requests.
- `MAX_RETRIES`: retry count for temporary failures.
- `MAX_CANDIDATES`: max generated or loaded candidates.
- `DB_PATH`: local SQLite database path.
- `OUTPUT_DIR`: where exports are written.

Do not share your `.env`, `tokens.txt`, database, logs, or output files with buyers or other users.

## Menu Options

- `Single Check`: check one username.
- `File Check`: load usernames from a text file.
- `Random Generate`: generate random usernames by length and character set.
- `Dictionary Scan`: check dictionary words as usernames.
- `Export`: save the latest run as txt, csv, or json.
- `Resume`: continue the latest unfinished run.
- `Settings`: view current configuration.
- `Exit`: close the app.

## Input Files

For file checks, use a plain text file with one username per line:

```text
nameone
name.two
name_three
```

Empty lines are ignored. Invalid usernames are filtered before checking.

## Outputs

The app writes runtime files locally:

- `data/checker.db`: run history and check results.
- `logs/app.log`: application log.
- `output/available.txt`: available usernames found during runs.
- `output/results.csv`: exported result table.
- `output/results.json`: exported JSON results.

For a clean release package, include the executable, `.env.example`, `README.md`, and any license or terms file. Do not include your personal `.env`, tokens, logs, database, or prior output.

## Building The EXE

PyInstaller is used for the Windows executable.

Install PyInstaller if needed:

```powershell
pip install pyinstaller
```

Build:

```powershell
python -m PyInstaller --noconfirm --clean --onefile --console --name availity src\cli.py
```

The built executable is created at:

```text
dist\availity.exe
```

## Troubleshooting

If the app closes immediately, run it from PowerShell so the error stays visible:

```powershell
.\dist\availity.exe
```

If token validation fails, check:

- `.env` exists in the same folder you are running from.
- `DISCORD_TOKEN` is filled in, or `DISCORD_MULTI_TOKEN=true` points to a valid `tokens.txt`.
- Tokens are written one per line in `tokens.txt`.
- The app has internet access.

If exports are empty, make sure you completed at least one run before exporting.

## Credit

Made by 9apf.
