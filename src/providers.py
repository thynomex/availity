import asyncio
import logging
import random
from abc import ABC, abstractmethod
from datetime import datetime
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Optional

import httpx

from src.config import AppConfig
from src.models import AvailabilityResult, UsernameStatus, ValidationResult
from src.validator import validate_username

logger = logging.getLogger(__name__)

DISCORD_POMELO_URL = "https://discord.com/api/v9/users/@me/pomelo-attempt"
DISCORD_ME_URL = "https://discord.com/api/v9/users/@me"


class AvailabilityProvider(ABC):
    @abstractmethod
    def validate_username(self, username: str) -> ValidationResult:
        ...

    @abstractmethod
    async def check_username(self, username: str) -> AvailabilityResult:
        ...


class DiscordProvider(AvailabilityProvider):
    """Checks Discord username availability via the pomelo-attempt endpoint."""

    def __init__(self, config: AppConfig):
        self.config = config
        self._tokens: list[str] = []
        self._token_index: int = 0
        self._client: Optional[httpx.AsyncClient] = None
        self._load_tokens()

    def _load_tokens(self):
        tokens_path = Path(self.config.discord_tokens_file)

        if self.config.discord_multi_token or not self.config.discord_token:
            if tokens_path.exists():
                self._tokens = [
                    line.strip()
                    for line in tokens_path.read_text(encoding="utf-8").splitlines()
                    if line.strip()
                ]
            if self._tokens:
                return
            if self.config.discord_token:
                self._tokens = [self.config.discord_token]
                return
            raise ValueError(
                "No tokens found. Set DISCORD_TOKEN in .env or add tokens to "
                f"'{self.config.discord_tokens_file}'"
                )
        else:
            self._tokens = [self.config.discord_token]

    @property
    def current_token(self) -> str:
        return self._tokens[self._token_index]

    def _rotate_token(self):
        self._token_index = (self._token_index + 1) % len(self._tokens)
        self._client = None
        logger.info(f"Rotated to token index {self._token_index}")

    def _build_headers(self) -> dict:
        return {
            "Content-Type": "application/json",
            "Authorization": self.current_token,
        }

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                headers=self._build_headers(), timeout=30.0
            )
        return self._client

    async def get_current_user(self) -> Optional[dict]:
        client = await self._get_client()
        try:
            resp = await client.get(DISCORD_ME_URL)
            if resp.status_code == 200:
                return resp.json()
        except httpx.RequestError:
            pass
        return None

    async def validate_tokens(self) -> list[dict]:
        """Validate all tokens and return status for each.
        Returns list of {"token_index": int, "valid": bool, "username": str|None, "error": str|None}
        Removes invalid tokens from the pool after validation.
        """
        results = []
        valid_tokens = []

        for i, token in enumerate(self._tokens):
            headers = {
                "Content-Type": "application/json",
                "Authorization": token,
            }
            async with httpx.AsyncClient(headers=headers, timeout=15.0) as client:
                try:
                    resp = await client.get(DISCORD_ME_URL)
                    if resp.status_code == 200:
                        data = resp.json()
                        results.append({
                            "token_index": i,
                            "valid": True,
                            "username": data.get("username", "unknown"),
                            "error": None,
                        })
                        valid_tokens.append(token)
                    elif resp.status_code == 401:
                        results.append({
                            "token_index": i,
                            "valid": False,
                            "username": None,
                            "error": "Invalid token (401 Unauthorized)",
                        })
                    elif resp.status_code == 403:
                        results.append({
                            "token_index": i,
                            "valid": False,
                            "username": None,
                            "error": "Forbidden (403) - token may be locked",
                        })
                    else:
                        results.append({
                            "token_index": i,
                            "valid": False,
                            "username": None,
                            "error": f"HTTP {resp.status_code}",
                        })
                except httpx.RequestError as e:
                    results.append({
                        "token_index": i,
                        "valid": False,
                        "username": None,
                        "error": f"Connection error: {e}",
                    })

        self._tokens = valid_tokens
        if valid_tokens:
            self._token_index = 0
            self._client = None
        return results

    def validate_username(self, username: str) -> ValidationResult:
        return validate_username(username)

    async def check_with_token(self, username: str, token: str) -> AvailabilityResult:
        """Fire a single check request using the given token. No retries."""
        headers = {"Content-Type": "application/json", "Authorization": token}
        async with httpx.AsyncClient(headers=headers, timeout=15.0) as client:
            try:
                response = await client.post(
                    DISCORD_POMELO_URL, json={"username": username}
                )

                if response.status_code == 200:
                    data = response.json()
                    taken = data.get("taken")
                    if taken is False:
                        status = UsernameStatus.AVAILABLE
                    elif taken is True:
                        status = UsernameStatus.UNAVAILABLE
                    else:
                        return AvailabilityResult(
                            username=username,
                            status=UsernameStatus.ERROR,
                            checked_at=datetime.utcnow(),
                            error_message=f"Unexpected response: {data}",
                            provider_metadata={"response": data},
                        )
                    return AvailabilityResult(
                        username=username,
                        status=status,
                        checked_at=datetime.utcnow(),
                        provider_metadata={"provider": "discord", "response": data},
                    )

                if response.status_code == 429:
                    retry_after = self._parse_retry_after(response)
                    return AvailabilityResult(
                        username=username,
                        status=UsernameStatus.RATE_LIMITED,
                        checked_at=datetime.utcnow(),
                        error_message=f"Rate limited. Retry after: {retry_after}s",
                        provider_metadata={"status_code": 429, "retry_after": retry_after},
                    )

                if response.status_code == 401:
                    return AvailabilityResult(
                        username=username,
                        status=UsernameStatus.ERROR,
                        checked_at=datetime.utcnow(),
                        error_message="Invalid token (401)",
                        provider_metadata={"status_code": 401, "token_dead": True},
                    )

                return AvailabilityResult(
                    username=username,
                    status=UsernameStatus.ERROR,
                    checked_at=datetime.utcnow(),
                    error_message=f"HTTP {response.status_code}: {response.text}",
                    provider_metadata={"status_code": response.status_code},
                )

            except httpx.TimeoutException:
                return AvailabilityResult(
                    username=username,
                    status=UsernameStatus.ERROR,
                    checked_at=datetime.utcnow(),
                    error_message="Request timed out",
                )
            except httpx.RequestError as e:
                return AvailabilityResult(
                    username=username,
                    status=UsernameStatus.ERROR,
                    checked_at=datetime.utcnow(),
                    error_message=f"Network error: {e}",
                )

    async def check_username(self, username: str) -> AvailabilityResult:
        """Legacy interface — uses first token. Prefer check_with_token."""
        if not self._tokens:
            return AvailabilityResult(
                username=username,
                status=UsernameStatus.ERROR,
                checked_at=datetime.utcnow(),
                error_message="No valid tokens available",
            )
        return await self.check_with_token(username, self._tokens[0])

        return AvailabilityResult(
            username=username,
            status=UsernameStatus.RATE_LIMITED,
            checked_at=datetime.utcnow(),
            error_message="All tokens rate limited",
            provider_metadata={"status_code": 429, "retry_after": 5.0},
        )

    def _parse_retry_after(self, response: httpx.Response) -> float:
        header = response.headers.get("Retry-After", "")
        if not header:
            try:
                data = response.json()
                return float(data.get("retry_after", 5.0))
            except Exception:
                return 5.0
        try:
            return float(header)
        except ValueError:
            return 5.0

    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()


class DiscordWebhookNotifier:
    """Sends available username notifications to a Discord webhook."""

    def __init__(self, webhook_url: str):
        self.webhook_url = webhook_url
        self._client: Optional[httpx.AsyncClient] = None
        self._found_count: int = 0

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=10.0)
        return self._client

    async def notify(self, username: str):
        if not self.webhook_url:
            return
        self._found_count += 1
        client = await self._get_client()
        payload = {
            "username": "Username Checker",
            "embeds": [
                {
                    "title": "Username Available",
                    "description": f"# `{username}`\nThis username is available to claim on Discord.",
                    "color": 0x57F287,
                    "fields": [
                        {
                            "name": "Username",
                            "value": f"`{username}`",
                            "inline": True,
                        },
                        {
                            "name": "Length",
                            "value": str(len(username)),
                            "inline": True,
                        },
                        {
                            "name": "Total Found",
                            "value": str(self._found_count),
                            "inline": True,
                        },
                    ],
                    "footer": {
                        "text": "Discord Username Checker",
                    },
                    "timestamp": datetime.utcnow().isoformat(),
                }
            ]
        }
        try:
            await client.post(
                self.webhook_url,
                json=payload,
                headers={"Content-Type": "application/json"},
            )
        except httpx.RequestError as e:
            logger.warning(f"Webhook notification failed: {e}")

    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()
