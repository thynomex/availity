import asyncio
from contextlib import suppress
import logging
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from rich.align import Align
from rich.console import Console, Group
from rich.live import Live
from rich.panel import Panel
from rich.rule import Rule
from rich.table import Table
from rich.text import Text

from src.checker import UsernameChecker
from src.config import AppConfig
from src.database import Database
from src.exporter import ResultExporter
from src.generator import UsernameGenerator
from src.models import CharMode, UsernameStatus
from src.providers import DiscordProvider, DiscordWebhookNotifier
from src.rate_limiter import RateLimiter, TokenPool
from src.validator import validate_username

console = Console()

BANNER_ART = """
    A     V     A    III  L      III  TTTTT  Y   Y
   A A     V   V    I     L     I       T     Y Y
  AAAAA     V V     I     L     I       T      Y
 A     A     V     III   LLLLL III      T      Y
"""
BANNER = f"[bold cyan]{BANNER_ART}[/bold cyan]"
BANNER_LINES = BANNER_ART.strip("\n").splitlines()
BANNER_WIDTH = max(len(line) for line in BANNER_LINES)
BANNER_SUBTITLE = "Made by 9apf."

# --- PLACEHOLDER_CLI_CONTINUE ---


def setup_logging(log_path: str):
    Path(log_path).parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        filename=log_path,
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def get_provider(config: AppConfig):
    return DiscordProvider(config)


def get_banner_frame(width: int) -> str:
    return "\n".join(line[:width].ljust(len(line)) for line in BANNER_LINES)


def build_shimmer_art(frame_index: int) -> Text:
    text = Text()
    sweep = frame_index % (BANNER_WIDTH + 10)
    for line_index, line in enumerate(BANNER_LINES):
        for column, char in enumerate(line):
            distance = abs(column - sweep)
            if distance <= 1:
                style = "bold white"
            elif distance <= 3:
                style = "bold bright_cyan"
            else:
                style = "cyan"
            text.append(char, style=style)
        if line_index < len(BANNER_LINES) - 1:
            text.append("\n")
    return text


def get_subtitle_frame(frame_index: int, hold_frames: int = 18) -> str:
    cycle_length = len(BANNER_SUBTITLE) + hold_frames
    visible_chars = min(frame_index % cycle_length, len(BANNER_SUBTITLE))
    subtitle = BANNER_SUBTITLE[:visible_chars]
    cursor = "_" if visible_chars < len(BANNER_SUBTITLE) else ""
    return f"{subtitle}{cursor}"


def build_banner(
    username: str = "",
    token_count: int = 1,
    multi: bool = False,
    style: str = "bold cyan",
    art: Optional[object] = None,
    subtitle: Optional[str] = None,
    show_subtitle: bool = True,
    status_markup: Optional[str] = None,
):
    if status_markup is None:
        status_parts = []
        status_parts.append(f"[green]Connected:[/green] [bold white]{username}[/bold white]")
        if multi:
            status_parts.append(f"[cyan]Tokens:[/cyan] [bold]{token_count}[/bold]")
        status_parts.append(f"[dim]{datetime.now().strftime('%Y-%m-%d %H:%M')}[/dim]")
        status_markup = "  |  ".join(status_parts)

    return Group(
        Align.center(art if isinstance(art, Text) else Text(art or BANNER_ART, style=style)),
        Align.center(Text(subtitle if subtitle is not None else BANNER_SUBTITLE, style="dim")) if show_subtitle else Text(""),
        Text(""),
        Align.center(Text.from_markup(status_markup)),
        Text(""),
    )


def show_banner(
    username: str = "",
    token_count: int = 1,
    multi: bool = False,
    animated: bool = True,
    show_subtitle: bool = True,
    status_markup: Optional[str] = None,
):
    console.clear()
    if animated:
        for width in range(1, BANNER_WIDTH + 3, 2):
            frame = get_banner_frame(min(width, BANNER_WIDTH))
            console.clear()
            console.print(build_banner(
                username,
                token_count,
                multi,
                style="bold bright_cyan",
                art=frame,
                subtitle="",
                show_subtitle=show_subtitle,
                status_markup=status_markup,
            ))
            time.sleep(0.06)

        if show_subtitle:
            for visible_chars in range(1, len(BANNER_SUBTITLE) + 1):
                console.clear()
                subtitle = BANNER_SUBTITLE[:visible_chars]
                if visible_chars < len(BANNER_SUBTITLE):
                    subtitle = f"{subtitle}_"
                console.print(build_banner(
                    username,
                    token_count,
                    multi,
                    style="bold bright_cyan",
                    subtitle=subtitle,
                    status_markup=status_markup,
                ))
                time.sleep(0.045)

    console.clear()
    console.print(build_banner(
        username,
        token_count,
        multi,
        show_subtitle=show_subtitle,
        status_markup=status_markup,
    ))


def build_menu() -> Group:
    menu = Table(show_header=False, box=None, padding=(0, 3), show_edge=False)
    menu.add_column(justify="right", style="bold cyan", width=4)
    menu.add_column(style="white")
    menu.add_column(style="dim")

    menu.add_row("1", "Single Check", "check one username")
    menu.add_row("2", "File Check", "check list from file")
    menu.add_row("3", "Random Generate", "generate + check by length")
    menu.add_row("4", "Dictionary Scan", "dictionary words as usernames")
    menu.add_row("5", "Export", "save results to file")
    menu.add_row("6", "Resume", "continue last interrupted run")
    menu.add_row("7", "Settings", "view current config")
    menu.add_row("8", "Exit", "quit the program")

    return Group(
        Rule("[bold cyan]Menu[/bold cyan]", style="dim"),
        Text(""),
        Align.center(menu),
        Text(""),
    )


def show_menu():
    console.print(build_menu())


def wait_for_continue() -> bool:
    try:
        console.input("  [dim]Press Enter to continue...[/dim]")
        return True
    except (EOFError, KeyboardInterrupt):
        return False


def build_menu_screen(
    username: str,
    token_count: int,
    multi: bool,
    frame_index: int,
) -> Group:
    return Group(
        build_banner(
            username,
            token_count,
            multi,
            art=build_shimmer_art(frame_index),
            subtitle=get_subtitle_frame(frame_index),
        ),
        build_menu(),
        Text.from_markup("  [cyan]>[/cyan] "),
    )


def read_menu_choice(username: str, token_count: int, multi: bool) -> str:
    try:
        import msvcrt
    except ImportError:
        show_banner(username, token_count, multi, animated=False)
        show_menu()
        return console.input("  [cyan]>[/cyan] ").strip()

    frame_index = 0
    console.clear()
    with Live(
        build_menu_screen(username, token_count, multi, frame_index),
        console=console,
        refresh_per_second=12,
        transient=False,
        vertical_overflow="crop",
    ) as live:
        while True:
            if msvcrt.kbhit():
                char = msvcrt.getwch()
                if char == "\x03":
                    raise KeyboardInterrupt
                if char in "12345678":
                    return char

            frame_index += 1
            live.update(build_menu_screen(username, token_count, multi, frame_index))
            time.sleep(0.08)


# --- PLACEHOLDER_CLI_FUNCTIONS ---


async def check_single(checker: UsernameChecker, webhook: Optional[DiscordWebhookNotifier] = None):
    console.print(Rule("[cyan]Single Username Check[/cyan]", style="dim"))
    username = console.input("\n  [cyan]>[/cyan] Username: ").strip()
    if not username:
        console.print("  [red]No username entered.[/red]")
        return

    validation = validate_username(username)
    if not validation.valid:
        console.print(f"  [red]Invalid:[/red] {validation.reason}")
        return

    console.print(f"  [dim]Checking[/dim] [bold]{username}[/bold][dim]...[/dim]")
    result = await checker.check_single(username)

    if result.status == UsernameStatus.AVAILABLE:
        console.print(Panel(
            f"[bold green]AVAILABLE[/bold green]  [white]{username}[/white]",
            border_style="green", padding=(0, 2),
        ))
        if webhook:
            await webhook.notify(username)
    elif result.status == UsernameStatus.UNAVAILABLE:
        console.print(Panel(
            f"[bold red]TAKEN[/bold red]  [dim]{username}[/dim]",
            border_style="red", padding=(0, 2),
        ))
    else:
        console.print(Panel(
            f"[bold yellow]{result.status.value.upper()}[/bold yellow]  {username}\n[dim]{result.error_message or ''}[/dim]",
            border_style="yellow", padding=(0, 2),
        ))


async def check_from_file(checker: UsernameChecker, config: AppConfig, db: Database, webhook: Optional[DiscordWebhookNotifier] = None):
    console.print(Rule("[cyan]File Check[/cyan]", style="dim"))
    file_path = console.input("\n  [cyan]>[/cyan] Path to file: ").strip()
    if not file_path or not Path(file_path).exists():
        console.print("  [red]File not found.[/red]")
        return

    usernames = [
        line.strip()
        for line in Path(file_path).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]

    if not usernames:
        console.print("  [red]No usernames found in file.[/red]")
        return

    if len(usernames) > config.max_candidates:
        console.print(f"  [yellow]Capped at {config.max_candidates} (from {len(usernames)})[/yellow]")
        usernames = usernames[: config.max_candidates]

    generator = UsernameGenerator(config)
    usernames = generator.deduplicate(usernames)
    usernames = generator.filter_valid(usernames)
    console.print(f"  [cyan]Loaded {len(usernames)} valid usernames[/cyan]")

    run_id = str(uuid.uuid4())
    await run_batch_with_progress(checker, usernames, run_id, db, config, webhook)


# --- PLACEHOLDER_CLI_GENERATE ---


async def generate_by_length(checker: UsernameChecker, config: AppConfig, db: Database, webhook: Optional[DiscordWebhookNotifier] = None):
    console.print(Rule("[cyan]Random Generate[/cyan]", style="dim"))
    try:
        length = int(console.input("\n  [cyan]>[/cyan] Username length (2-32): ").strip())
    except ValueError:
        console.print("  [red]Invalid number.[/red]")
        return

    if length < 2 or length > 32:
        console.print("  [red]Length must be between 2 and 32.[/red]")
        return

    console.print()
    console.print("  [dim]Character sets:[/dim]")
    console.print("    [cyan]1[/cyan] Letters only")
    console.print("    [cyan]2[/cyan] Numbers only")
    console.print("    [cyan]3[/cyan] Letters + Numbers")
    console.print("    [cyan]4[/cyan] Custom charset")
    mode_input = console.input("  [cyan]>[/cyan] Choice: ").strip()

    mode_map = {"1": CharMode.LETTERS, "2": CharMode.NUMBERS, "3": CharMode.ALPHANUMERIC, "4": CharMode.CUSTOM}
    mode = mode_map.get(mode_input, CharMode.ALPHANUMERIC)

    custom_chars = ""
    if mode == CharMode.CUSTOM:
        custom_chars = console.input("  [cyan]>[/cyan] Allowed characters: ").strip()
        if not custom_chars:
            console.print("  [dim]Defaulting to alphanumeric.[/dim]")
            mode = CharMode.ALPHANUMERIC

    try:
        count = int(console.input(f"  [cyan]>[/cyan] How many (max {config.max_candidates}): ").strip())
    except ValueError:
        console.print("  [red]Invalid number.[/red]")
        return

    count = min(count, config.max_candidates)
    generator = UsernameGenerator(config)
    console.print(f"  [dim]Generating {count} candidates...[/dim]")
    candidates = generator.generate_random(length, mode, count, custom_chars)
    candidates = generator.deduplicate(candidates)

    console.print(f"  [green]{len(candidates)} unique candidates ready.[/green]")
    if not candidates:
        return

    check_now = console.input("\n  [cyan]>[/cyan] Check now? (y/n): ").strip().lower()
    if check_now == "y":
        run_id = str(uuid.uuid4())
        await run_batch_with_progress(checker, candidates, run_id, db, config, webhook)


async def generate_dictionary(checker: UsernameChecker, config: AppConfig, db: Database, webhook: Optional[DiscordWebhookNotifier] = None):
    console.print(Rule("[cyan]Dictionary Scan[/cyan]", style="dim"))
    try:
        min_len = int(console.input("\n  [cyan]>[/cyan] Min word length: ").strip())
        max_len = int(console.input("  [cyan]>[/cyan] Max word length: ").strip())
        max_count = int(console.input(f"  [cyan]>[/cyan] Max candidates (up to {config.max_candidates}): ").strip())
    except ValueError:
        console.print("  [red]Invalid number.[/red]")
        return

    max_count = min(max_count, config.max_candidates)
    generator = UsernameGenerator(config)

    console.print("  [dim]Loading dictionary...[/dim]")
    candidates = await generator.generate_dictionary(min_len, max_len, max_count)
    console.print(f"  [green]{len(candidates)} dictionary candidates found.[/green]")

    if not candidates:
        return

    check_now = console.input("\n  [cyan]>[/cyan] Check now? (y/n): ").strip().lower()
    if check_now == "y":
        run_id = str(uuid.uuid4())
        await run_batch_with_progress(checker, candidates, run_id, db, config, webhook)


async def export_results(config: AppConfig, db: Database):
    console.print(Rule("[cyan]Export Results[/cyan]", style="dim"))
    run = await db.get_latest_run()
    if not run:
        console.print("  [yellow]No runs found to export.[/yellow]")
        return

    console.print(f"\n  [dim]Latest run:[/dim] [white]{run.run_id[:8]}...[/white]  ({run.checked} checked, [green]{run.available} available[/green])")

    exporter = ResultExporter(config, db)
    path = await exporter.export_available_txt(run.run_id)
    console.print(f"\n  [green]Saved:[/green] {path}")


# --- PLACEHOLDER_CLI_RESUME ---


async def resume_last_run(checker: UsernameChecker, db: Database, config: AppConfig, webhook: Optional[DiscordWebhookNotifier] = None):
    console.print(Rule("[cyan]Resume[/cyan]", style="dim"))
    run = await db.get_latest_run()
    if not run:
        console.print("  [yellow]No previous runs found.[/yellow]")
        return

    if run.finished_at:
        console.print("  [yellow]Last run already completed.[/yellow]")
        return

    pending = await db.get_pending_candidates(run.run_id)
    total = len(pending)
    console.print(f"  [cyan]Resuming:[/cyan] {total:,} candidates remaining")
    console.print()

    available_path = Path(config.output_dir) / "available.txt"
    available_path.parent.mkdir(parents=True, exist_ok=True)

    console.print(f"  [dim]Workers:[/dim] [cyan]{config.concurrency}[/cyan]")
    console.print("  [dim]Press Ctrl+C to stop. Progress is saved.[/dim]\n")

    start_time = time.time()
    last_username = ""

    def build_status_line(stats: dict) -> str:
        elapsed = time.time() - start_time
        checked = stats["checked"]
        hits = stats["available"]
        taken_count = checked - hits - stats["errors"] - stats["rate_limited"]
        left = total - checked
        rps = checked / elapsed if elapsed > 0 else 0
        hit_pct = (hits / checked * 100) if checked > 0 else 0.0
        mins = int(elapsed) // 60
        secs = int(elapsed) % 60
        return (
            f"  [cyan]>[/cyan] "
            f"[bold white]{rps:.0f}[/bold white] rps  "
            f"[bold green]{hits}[/bold green] hits  "
            f"[bold red]{taken_count}[/bold red] taken  "
            f"[bold yellow]{left:,}[/bold yellow] left  "
            f"[dim]{hit_pct:.1f}%[/dim]  "
            f"[dim]{mins}m{secs}s[/dim]  "
            f"[magenta]{last_username}[/magenta]"
        )

    with Live("  [dim]Starting workers...[/dim]", console=console, refresh_per_second=8) as live:

        def on_progress(stats, total_count):
            live.update(build_status_line(stats))

        async def on_found(result):
            nonlocal last_username
            last_username = result.username
            live.console.print(f"    [bold green]+[/bold green] [white]{result.username}[/white]")
            with open(available_path, "a", encoding="utf-8") as f:
                f.write(f"{result.username}\n")
            if webhook:
                await webhook.notify(result.username)

        def on_check(username: str):
            nonlocal last_username
            last_username = username

        def on_rate_limit(token_index: int, retry_after: float):
            live.console.print(f"    [bold yellow]![/bold yellow] [yellow]429 Too Many Requests[/yellow] [dim]token {token_index + 1} cooling {retry_after:.1f}s[/dim]")

        try:
            results = await checker.resume_run(run.run_id, progress_callback=on_progress, on_found=on_found, on_check=on_check, on_rate_limit=on_rate_limit)
        except (KeyboardInterrupt, asyncio.CancelledError):
            checker.cancel()
            stats = checker.stats
            console.print(f"\n  [yellow]Paused.[/yellow] {stats['checked']:,} checked, [green]{stats['available']}[/green] hits.")
            checker.reset()
            return

    elapsed = time.time() - start_time
    available = [r for r in results if r.status == UsernameStatus.AVAILABLE]
    rps = len(results) / elapsed if elapsed > 0 else 0
    console.print(f"\n  [bold green]{len(available)}[/bold green] hits  [dim]{rps:.0f} rps avg  {int(elapsed)}s[/dim]")


async def show_settings(config: AppConfig):
    console.print(Rule("[cyan]Settings[/cyan]", style="dim"))
    console.print()

    table = Table(show_header=True, header_style="bold cyan", box=None, padding=(0, 3))
    table.add_column("Setting", style="white")
    table.add_column("Value", style="yellow")

    table.add_row("Provider", config.provider)
    table.add_row("Concurrency", str(config.concurrency))
    table.add_row("Request Delay", f"{config.request_delay}s")
    table.add_row("Max Retries", str(config.max_retries))
    table.add_row("Max Candidates", str(config.max_candidates))
    table.add_row("Username Length", f"{config.min_username_length}-{config.max_username_length}")
    table.add_row("Circuit Breaker", f"{config.circuit_breaker_threshold} failures / {config.circuit_breaker_timeout}s timeout")
    table.add_row("DB Path", config.db_path)
    table.add_row("Output Dir", config.output_dir)
    table.add_row("Webhook", "enabled" if config.discord_webhook_url else "[dim]disabled[/dim]")

    console.print(table)
    console.print("\n  [dim]Edit .env to change settings, then restart.[/dim]")


async def run_batch_with_progress(
    checker: UsernameChecker, usernames: list[str], run_id: str, db: Database, config: AppConfig,
    webhook: Optional[DiscordWebhookNotifier] = None,
):
    available_path = Path(config.output_dir) / "available.txt"
    available_path.parent.mkdir(parents=True, exist_ok=True)
    interrupted = False

    total = len(usernames)
    start_time = time.time()
    last_username = ""
    hits = 0
    taken = 0

    console.print()
    console.print(f"  [dim]Workers:[/dim] [cyan]{config.concurrency}[/cyan]  [dim]Candidates:[/dim] [cyan]{total:,}[/cyan]")
    console.print(f"  [dim]Press Ctrl+C to stop. Progress is saved.[/dim]\n")

    def build_status_line(stats: dict) -> str:
        nonlocal hits, taken
        elapsed = time.time() - start_time
        checked = stats["checked"]
        hits = stats["available"]
        taken = checked - hits - stats["errors"] - stats["rate_limited"]
        left = total - checked
        rps = checked / elapsed if elapsed > 0 else 0
        hit_pct = (hits / checked * 100) if checked > 0 else 0.0

        mins = int(elapsed) // 60
        secs = int(elapsed) % 60
        time_str = f"{mins}m{secs}s"

        line = (
            f"  [cyan]>[/cyan] "
            f"[bold white]{rps:.0f}[/bold white] rps  "
            f"[bold green]{hits}[/bold green] hits  "
            f"[bold red]{taken}[/bold red] taken  "
            f"[bold yellow]{left:,}[/bold yellow] left  "
            f"[dim]{hit_pct:.1f}%[/dim]  "
            f"[dim]{time_str}[/dim]  "
            f"[magenta]{last_username}[/magenta]"
        )
        return line

    with Live("  [dim]Starting workers...[/dim]", console=console, refresh_per_second=8) as live:

        def on_progress(stats, total_count):
            live.update(build_status_line(stats))

        async def on_found(result):
            nonlocal last_username
            last_username = result.username
            live.console.print(f"    [bold green]+[/bold green] [white]{result.username}[/white]")
            with open(available_path, "a", encoding="utf-8") as f:
                f.write(f"{result.username}\n")
            if webhook:
                await webhook.notify(result.username)

        def on_check(username: str):
            nonlocal last_username
            last_username = username

        def on_rate_limit(token_index: int, retry_after: float):
            live.console.print(f"    [bold yellow]![/bold yellow] [yellow]429 Too Many Requests[/yellow] [dim]token {token_index + 1} cooling {retry_after:.1f}s[/dim]")

        try:
            results = await checker.check_batch(usernames, run_id, progress_callback=on_progress, on_found=on_found, on_check=on_check, on_rate_limit=on_rate_limit)
        except KeyboardInterrupt:
            checker.cancel()
            interrupted = True
            results = []
        except asyncio.CancelledError:
            checker.cancel()
            interrupted = True
            results = []

    if interrupted:
        stats = checker.stats
        elapsed = time.time() - start_time
        console.print(f"\n  [yellow]Paused.[/yellow] {stats['checked']:,}/{total:,} checked in {int(elapsed)}s, [green]{stats['available']}[/green] hits.")
        console.print("  [dim]Use Resume (option 6) to continue later.[/dim]")
        checker.reset()
        return

    elapsed = time.time() - start_time
    available = [r for r in results if r.status == UsernameStatus.AVAILABLE]
    final_taken = len(results) - len(available) - sum(1 for r in results if r.status in (UsernameStatus.ERROR, UsernameStatus.RATE_LIMITED))
    rps = len(results) / elapsed if elapsed > 0 else 0

    console.print()
    console.print(f"  [bold green]{len(available)}[/bold green] hits  [bold red]{final_taken}[/bold red] taken  [dim]{rps:.0f} rps avg  {int(elapsed)}s[/dim]")

    if available:
        exporter = ResultExporter(config, db)
        await exporter.export_all(run_id)
        console.print(f"  [dim]Exported to {config.output_dir}/[/dim]")
    else:
        console.print(f"  [dim]No available usernames found.[/dim]")


async def async_main():
    config = AppConfig()
    config.ensure_dirs()
    setup_logging(config.log_path)
    logging.info("Application started")

    db = Database(config.db_path)
    await db.init_db()

    provider = get_provider(config)
    rate_limiter = RateLimiter(config)
    token_pool = TokenPool(provider._tokens)
    checker = UsernameChecker(config, provider, db, rate_limiter, token_pool)

    webhook = None
    if config.discord_webhook_url:
        webhook = DiscordWebhookNotifier(config.discord_webhook_url)

    show_banner(
        animated=True,
        show_subtitle=False,
        status_markup="[dim]Validating tokens...[/dim]",
    )

    token_results = await provider.validate_tokens()
    valid_count = sum(1 for t in token_results if t["valid"])
    invalid_count = sum(1 for t in token_results if not t["valid"])

    for t in token_results:
        idx = t["token_index"] + 1
        if t["valid"]:
            console.print(f"    [green]Token {idx}[/green]  [bold white]{t['username']}[/bold white]")
        else:
            console.print(f"    [red]Token {idx}[/red]  [dim]{t['error']}[/dim]")

    console.print()

    if valid_count == 0:
        console.print("  [bold red]No valid tokens. Cannot continue.[/bold red]")
        console.print("  [dim]Check your DISCORD_TOKEN in .env or tokens in tokens.txt[/dim]")
        return

    token_pool = TokenPool(provider._tokens)
    checker.token_pool = token_pool

    if invalid_count > 0:
        console.print(f"  [yellow]{invalid_count} invalid token(s) removed from pool.[/yellow]")

    primary_name = next((t["username"] for t in token_results if t["valid"]), "unknown")
    show_banner(primary_name, valid_count, config.discord_multi_token)

    try:
        while True:
            choice = read_menu_choice(primary_name, valid_count, config.discord_multi_token)
            console.clear()

            if choice == "1":
                await check_single(checker, webhook)
            elif choice == "2":
                await check_from_file(checker, config, db, webhook)
            elif choice == "3":
                await generate_by_length(checker, config, db, webhook)
            elif choice == "4":
                await generate_dictionary(checker, config, db, webhook)
            elif choice == "5":
                await export_results(config, db)
            elif choice == "6":
                await resume_last_run(checker, db, config, webhook)
            elif choice == "7":
                await show_settings(config)
            elif choice == "8":
                console.clear()
                console.print("\n  [dim]Goodbye.[/dim]\n")
                break
            else:
                console.print("  [red]Invalid option.[/red]")

            console.print()
            if not wait_for_continue():
                console.print("\n  [yellow]Interrupted. State saved.[/yellow]")
                break
            show_banner(primary_name, valid_count, config.discord_multi_token)
    except (KeyboardInterrupt, EOFError):
        console.print("\n\n  [yellow]Interrupted. State saved.[/yellow]")
    finally:
        with suppress(Exception, KeyboardInterrupt, asyncio.CancelledError):
            await provider.close()
        if webhook:
            with suppress(Exception, KeyboardInterrupt, asyncio.CancelledError):
                await webhook.close()
        with suppress(Exception, KeyboardInterrupt, asyncio.CancelledError):
            await db.close()
        logging.info("Application stopped")


def main():
    try:
        asyncio.run(async_main())
    except (KeyboardInterrupt, EOFError):
        pass


if __name__ == "__main__":
    main()
