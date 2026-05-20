import pytest

from src.config import AppConfig
from src.validator import validate_username


@pytest.fixture
def config():
    return AppConfig()


class TestValidUsername:
    def test_simple_valid(self, config):
        assert validate_username("hello", config).valid is True

    def test_with_numbers(self, config):
        assert validate_username("user123", config).valid is True

    def test_with_period(self, config):
        assert validate_username("my.name", config).valid is True

    def test_min_length(self, config):
        assert validate_username("ab", config).valid is True

    def test_max_length(self, config):
        name = "a" * 32
        assert validate_username(name, config).valid is True

    def test_underscore_middle(self, config):
        assert validate_username("user_name", config).valid is True

    def test_numbers_only(self, config):
        assert validate_username("12345", config).valid is True


class TestInvalidUsername:
    def test_empty(self, config):
        result = validate_username("", config)
        assert result.valid is False
        assert "empty" in result.reason.lower()

    def test_too_short(self, config):
        result = validate_username("a", config)
        assert result.valid is False
        assert "at least" in result.reason.lower()

    def test_too_long(self, config):
        result = validate_username("a" * 33, config)
        assert result.valid is False
        assert "at most" in result.reason.lower()

    def test_uppercase(self, config):
        result = validate_username("Hello", config)
        assert result.valid is False
        assert "lowercase" in result.reason.lower()

    def test_special_chars(self, config):
        result = validate_username("user@name", config)
        assert result.valid is False

    def test_spaces(self, config):
        result = validate_username("user name", config)
        assert result.valid is False

    def test_starts_with_period(self, config):
        result = validate_username(".username", config)
        assert result.valid is False
        assert "start" in result.reason.lower()

    def test_ends_with_period(self, config):
        result = validate_username("username.", config)
        assert result.valid is False
        assert "end" in result.reason.lower()

    def test_starts_with_underscore(self, config):
        result = validate_username("_username", config)
        assert result.valid is False

    def test_ends_with_underscore(self, config):
        result = validate_username("username_", config)
        assert result.valid is False

    def test_consecutive_periods(self, config):
        result = validate_username("user..name", config)
        assert result.valid is False
        assert "consecutive" in result.reason.lower()

    def test_consecutive_underscores(self, config):
        result = validate_username("user__name", config)
        assert result.valid is False

    def test_period_underscore(self, config):
        result = validate_username("user._name", config)
        assert result.valid is False

    def test_hyphen_not_allowed(self, config):
        result = validate_username("user-name", config)
        assert result.valid is False
