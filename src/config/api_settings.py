from __future__ import annotations

import os
from dataclasses import dataclass

DEV_JWT_SECRET = "dev-only-secret-change-me-dev-only-secret"
PLACEHOLDER_SECRETS = {DEV_JWT_SECRET, "change-me-to-a-long-random-string-at-least-32-chars"}


@dataclass(frozen=True)
class ApiSettings:
    app_env: str
    jwt_secret: str
    jwt_ttl_minutes: int
    cors_origins: tuple[str, ...]
    rate_limit_per_minute: int
    login_attempts_per_minute: int
    max_body_bytes: int
    upload_max_bytes: int

    @staticmethod
    def from_env() -> ApiSettings:
        env = os.environ.get
        settings = ApiSettings(
            app_env=env("APP_ENV", "development"),
            jwt_secret=env("JWT_SECRET", DEV_JWT_SECRET),
            jwt_ttl_minutes=int(env("JWT_TTL_MINUTES", "60")),
            cors_origins=tuple(o.strip() for o in env("CORS_ORIGINS", "").split(",") if o.strip()),
            rate_limit_per_minute=int(env("RATE_LIMIT_PER_MINUTE", "120")),
            login_attempts_per_minute=int(env("LOGIN_ATTEMPTS_PER_MINUTE", "5")),
            max_body_bytes=int(env("MAX_BODY_BYTES", "1000000")),
            upload_max_bytes=int(env("UPLOAD_MAX_BYTES", "10000000")),
        )
        settings.validate()
        return settings

    def validate(self) -> None:
        """Refuse to start in a non-development environment with a default
        or short signing secret (OWASP: security misconfiguration)."""
        if self.app_env != "development" and (
            self.jwt_secret in PLACEHOLDER_SECRETS or len(self.jwt_secret) < 32
        ):
            raise RuntimeError(
                "JWT_SECRET must be set to a unique random value of >= 32 characters "
                f"when APP_ENV={self.app_env}"
            )
