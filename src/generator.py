import random
import string
from pathlib import Path
from typing import Optional

import httpx

from src.config import AppConfig
from src.models import CharMode
from src.validator import validate_username


class UsernameGenerator:
    def __init__(self, config: AppConfig):
        self.config = config

    def generate_random(
        self, length: int, mode: CharMode, count: int, custom_chars: str = ""
    ) -> list[str]:
        count = min(count, self.config.max_candidates)
        length = max(self.config.min_username_length, min(length, self.config.max_username_length))

        charset = self._get_charset(mode, custom_chars)
        if not charset:
            return []

        candidates: list[str] = []
        attempts = 0
        max_attempts = count * 10

        while len(candidates) < count and attempts < max_attempts:
            attempts += 1
            name = "".join(random.choices(charset, k=length))
            result = validate_username(name, self.config)
            if result.valid and name not in candidates:
                candidates.append(name)

        return candidates

    async def generate_dictionary(
        self, min_length: int, max_length: int, max_count: int
    ) -> list[str]:
        max_count = min(max_count, self.config.max_candidates)
        words = await self.load_wordlist()

        candidates = []
        for word in words:
            word = word.lower().strip()
            if len(word) < min_length or len(word) > max_length:
                continue
            result = validate_username(word, self.config)
            if result.valid:
                candidates.append(word)
            if len(candidates) >= max_count:
                break

        return candidates

    async def load_wordlist(self) -> list[str]:
        cache_path = Path(self.config.wordlist_cache_path)
        if cache_path.exists() and cache_path.stat().st_size > 0:
            return cache_path.read_text(encoding="utf-8").splitlines()

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(self.config.wordlist_url)
                response.raise_for_status()
                content = response.text
                if len(content.splitlines()) < 100:
                    raise ValueError("Downloaded word list seems too small")
                cache_path.parent.mkdir(parents=True, exist_ok=True)
                cache_path.write_text(content, encoding="utf-8")
                return content.splitlines()
        except Exception:
            fallback_path = Path(self.config.fallback_wordlist_path)
            if fallback_path.exists():
                return fallback_path.read_text(encoding="utf-8").splitlines()
            return []

    def deduplicate(self, candidates: list[str]) -> list[str]:
        seen: set[str] = set()
        result: list[str] = []
        for c in candidates:
            if c not in seen:
                seen.add(c)
                result.append(c)
        return result

    def filter_valid(self, candidates: list[str]) -> list[str]:
        return [c for c in candidates if validate_username(c, self.config).valid]

    def _get_charset(self, mode: CharMode, custom_chars: str) -> str:
        if mode == CharMode.LETTERS:
            return string.ascii_lowercase
        elif mode == CharMode.NUMBERS:
            return string.digits
        elif mode == CharMode.ALPHANUMERIC:
            return string.ascii_lowercase + string.digits
        elif mode == CharMode.CUSTOM:
            return custom_chars if custom_chars else string.ascii_lowercase + string.digits
        return string.ascii_lowercase
