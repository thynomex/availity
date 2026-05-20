import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from pathlib import Path

from src.config import AppConfig
from src.models import UsernameStatus
from src.providers import DiscordProvider, DiscordWebhookNotifier


@pytest.fixture
def mock_config(tmp_path):
    config = MagicMock(spec=AppConfig)
    config.discord_token = "test_token_123"
    config.discord_tokens_file = str(tmp_path / "tokens.txt")
    config.discord_multi_token = False
    config.discord_webhook_url = ""
    return config


@pytest.fixture
def multi_token_config(tmp_path):
    tokens_file = tmp_path / "tokens.txt"
    tokens_file.write_text("token_one\ntoken_two\ntoken_three\n")
    config = MagicMock(spec=AppConfig)
    config.discord_token = ""
    config.discord_tokens_file = str(tokens_file)
    config.discord_multi_token = True
    config.discord_webhook_url = ""
    return config


def make_mock_response(status_code, json_data, headers=None):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data
    resp.headers = headers or {}
    resp.text = str(json_data)
    return resp


class TestDiscordProvider:
    def test_init_single_token(self, mock_config):
        provider = DiscordProvider(mock_config)
        assert provider.current_token == "test_token_123"
        assert len(provider._tokens) == 1

    def test_init_multi_token(self, multi_token_config):
        provider = DiscordProvider(multi_token_config)
        assert len(provider._tokens) == 3
        assert provider.current_token == "token_one"

    def test_init_no_token_raises(self, tmp_path):
        config = MagicMock(spec=AppConfig)
        config.discord_token = ""
        config.discord_tokens_file = str(tmp_path / "nonexistent.txt")
        config.discord_multi_token = False
        with pytest.raises(ValueError, match="No tokens found"):
            DiscordProvider(config)

    def test_init_multi_token_empty_file_raises(self, tmp_path):
        tokens_file = tmp_path / "tokens.txt"
        tokens_file.write_text("")
        config = MagicMock(spec=AppConfig)
        config.discord_token = ""
        config.discord_tokens_file = str(tokens_file)
        config.discord_multi_token = True
        with pytest.raises(ValueError, match="No tokens found"):
            DiscordProvider(config)

    def test_validate_valid(self, mock_config):
        provider = DiscordProvider(mock_config)
        result = provider.validate_username("testuser")
        assert result.valid is True

    def test_validate_invalid(self, mock_config):
        provider = DiscordProvider(mock_config)
        result = provider.validate_username("")
        assert result.valid is False

    @pytest.mark.asyncio
    async def test_check_username_available(self, mock_config):
        provider = DiscordProvider(mock_config)
        mock_resp = make_mock_response(200, {"taken": False})

        with patch("src.providers.httpx.AsyncClient") as MockClient:
            instance = AsyncMock()
            instance.post = AsyncMock(return_value=mock_resp)
            instance.__aenter__ = AsyncMock(return_value=instance)
            instance.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = instance

            result = await provider.check_with_token("coolname", "test_token")
            assert result.status == UsernameStatus.AVAILABLE

    @pytest.mark.asyncio
    async def test_check_username_taken(self, mock_config):
        provider = DiscordProvider(mock_config)
        mock_resp = make_mock_response(200, {"taken": True})

        with patch("src.providers.httpx.AsyncClient") as MockClient:
            instance = AsyncMock()
            instance.post = AsyncMock(return_value=mock_resp)
            instance.__aenter__ = AsyncMock(return_value=instance)
            instance.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = instance

            result = await provider.check_with_token("takenname", "test_token")
            assert result.status == UsernameStatus.UNAVAILABLE

    @pytest.mark.asyncio
    async def test_check_username_rate_limited(self, mock_config):
        provider = DiscordProvider(mock_config)
        mock_resp = make_mock_response(429, {"retry_after": 5.0}, {"Retry-After": "5.0"})

        with patch("src.providers.httpx.AsyncClient") as MockClient:
            instance = AsyncMock()
            instance.post = AsyncMock(return_value=mock_resp)
            instance.__aenter__ = AsyncMock(return_value=instance)
            instance.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = instance

            result = await provider.check_with_token("anyname", "test_token")
            assert result.status == UsernameStatus.RATE_LIMITED

    @pytest.mark.asyncio
    async def test_check_username_unauthorized(self, mock_config):
        provider = DiscordProvider(mock_config)
        mock_resp = make_mock_response(401, {"message": "Unauthorized"})

        with patch("src.providers.httpx.AsyncClient") as MockClient:
            instance = AsyncMock()
            instance.post = AsyncMock(return_value=mock_resp)
            instance.__aenter__ = AsyncMock(return_value=instance)
            instance.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = instance

            result = await provider.check_with_token("anyname", "test_token")
            assert result.status == UsernameStatus.ERROR
            assert result.provider_metadata.get("token_dead") is True


class TestDiscordWebhookNotifier:
    @pytest.mark.asyncio
    async def test_notify_sends_embed(self):
        notifier = DiscordWebhookNotifier("https://discord.com/api/webhooks/test")
        mock_client = AsyncMock()
        mock_client.post = AsyncMock()
        mock_client.is_closed = False
        notifier._client = mock_client

        await notifier.notify("coolname")
        mock_client.post.assert_called_once()
        call_kwargs = mock_client.post.call_args
        assert "coolname" in str(call_kwargs)

    @pytest.mark.asyncio
    async def test_notify_skips_empty_url(self):
        notifier = DiscordWebhookNotifier("")
        await notifier.notify("coolname")
