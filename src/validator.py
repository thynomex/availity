import re
from typing import Optional

from src.config import AppConfig
from src.models import ValidationResult

ALLOWED_CHARS = re.compile(r"^[a-z0-9_.]+$")
CONSECUTIVE_SPECIAL = re.compile(r"[_.]{2}")


def validate_username(username: str, config: Optional[AppConfig] = None) -> ValidationResult:
    if config is None:
        config = AppConfig()

    if not username:
        return ValidationResult(valid=False, reason="Username cannot be empty")

    if len(username) < config.min_username_length:
        return ValidationResult(
            valid=False,
            reason=f"Username must be at least {config.min_username_length} characters",
        )

    if len(username) > config.max_username_length:
        return ValidationResult(
            valid=False,
            reason=f"Username must be at most {config.max_username_length} characters",
        )

    if username != username.lower():
        return ValidationResult(valid=False, reason="Username must be lowercase")

    if not ALLOWED_CHARS.match(username):
        return ValidationResult(
            valid=False, reason="Username can only contain lowercase letters, numbers, underscores, and periods"
        )

    if username[0] in "_.":
        return ValidationResult(valid=False, reason="Username cannot start with a period or underscore")

    if username[-1] in "_.":
        return ValidationResult(valid=False, reason="Username cannot end with a period or underscore")

    if CONSECUTIVE_SPECIAL.search(username):
        return ValidationResult(valid=False, reason="Username cannot have consecutive periods or underscores")

    return ValidationResult(valid=True)
