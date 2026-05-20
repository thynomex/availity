import os
from pathlib import Path

from dotenv import load_dotenv


class AppConfig:
    def __init__(self):
        load_dotenv()

        self.concurrency: int = int(os.getenv("CONCURRENCY", "50"))
        self.max_concurrency: int = 1000
        self.request_delay: float = float(os.getenv("REQUEST_DELAY", "0"))

        self.max_retries: int = int(os.getenv("MAX_RETRIES", "3"))
        self.backoff_base: float = 2.0
        self.backoff_max: float = 60.0

        self.circuit_breaker_threshold: int = int(os.getenv("CIRCUIT_BREAKER_THRESHOLD", "5"))
        self.circuit_breaker_timeout: float = float(os.getenv("CIRCUIT_BREAKER_TIMEOUT", "60.0"))

        self.max_candidates: int = int(os.getenv("MAX_CANDIDATES", "1000"))
        self.min_username_length: int = int(os.getenv("MIN_USERNAME_LENGTH", "2"))
        self.max_username_length: int = int(os.getenv("MAX_USERNAME_LENGTH", "32"))

        self.wordlist_url: str = os.getenv(
            "WORDLIST_URL",
            "https://raw.githubusercontent.com/dwyl/english-words/master/words_alpha.txt",
        )
        self.wordlist_cache_path: str = os.getenv("WORDLIST_CACHE_PATH", "data/wordlist_cache.txt")
        self.fallback_wordlist_path: str = os.getenv("FALLBACK_WORDLIST_PATH", "data/fallback_words.txt")

        self.provider: str = os.getenv("PROVIDER", "discord")
        self.api_endpoint: str = os.getenv("API_ENDPOINT", "")
        self.api_key: str = os.getenv("API_KEY", "")

        self.discord_token: str = os.getenv("DISCORD_TOKEN", "")
        self.discord_tokens_file: str = os.getenv("DISCORD_TOKENS_FILE", "tokens.txt")
        self.discord_multi_token: bool = os.getenv("DISCORD_MULTI_TOKEN", "false").lower() == "true"
        self.discord_webhook_url: str = os.getenv("DISCORD_WEBHOOK_URL", "")

        self.db_path: str = os.getenv("DB_PATH", "data/checker.db")
        self.log_path: str = os.getenv("LOG_PATH", "logs/app.log")
        self.output_dir: str = os.getenv("OUTPUT_DIR", "output")

        self.concurrency = min(self.concurrency, self.max_concurrency)

    def ensure_dirs(self):
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        Path(self.log_path).parent.mkdir(parents=True, exist_ok=True)
        Path(self.output_dir).mkdir(parents=True, exist_ok=True)
        Path(self.wordlist_cache_path).parent.mkdir(parents=True, exist_ok=True)
