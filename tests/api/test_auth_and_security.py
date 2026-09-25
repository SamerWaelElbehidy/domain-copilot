import asyncio
import base64
import json
from datetime import UTC, datetime, timedelta

import jwt
import pytest
from fastapi import Depends
from starlette.testclient import TestClient

from api.app import create_app
from api.container import Container
from api.deps import require
from api.rate_limit import TokenBucketLimiter
from application.use_cases.authenticate_user import make_dummy_hash
from config.api_settings import DEV_JWT_SECRET, ApiSettings
from domain.entities.user import User
from domain.value_objects.role import Permission, Role
from infrastructure.security.jwt_token_service import JwtTokenService
from infrastructure.security.password_hasher import ScryptPasswordHasher
from tests.fakes.in_memory import InMemoryUserRepository

SECRET = "a-test-secret-that-is-long-enough-for-hs256-0123456789"
PASSWORD = "correct horse battery staple"


def make_settings(**overrides) -> ApiSettings:
    base = {
        "app_env": "development",
        "jwt_secret": SECRET,
        "jwt_ttl_minutes": 60,
        "cors_origins": (),
        "rate_limit_per_minute": 1000,
        "login_attempts_per_minute": 5,
        "max_body_bytes": 1000,
        "upload_max_bytes": 5000,
    }
    return ApiSettings(**{**base, **overrides})


class Stack:
    def __init__(self, settings: ApiSettings | None = None, clock=None) -> None:
        self.settings = settings or make_settings()
        self.users = InMemoryUserRepository()
        self.hasher = ScryptPasswordHasher()
        kwargs = {"clock": clock} if clock else {}
        self.tokens = JwtTokenService(self.settings.jwt_secret, 60, **kwargs)
        self.container = Container(
            settings=self.settings,
            users=self.users,
            hasher=self.hasher,
            tokens=self.tokens,
            dummy_hash=make_dummy_hash(self.hasher),
            login_limiter=TokenBucketLimiter(self.settings.login_attempts_per_minute),
        )
        self.app = create_app(self.settings, self.container)

        @self.app.get("/_test/decide")
        async def decide(user: User = Depends(require(Permission.DECIDE_WORK_ORDER))):
            return {"ok": user.username}

        @self.app.get("/_test/boom")
        async def boom():
            raise RuntimeError("secret internal detail: db password is hunter2")

        self.client = TestClient(self.app, raise_server_exceptions=False)

    def add_user(self, username: str, role: Role, disabled: bool = False) -> User:
        user = User(f"u-{username}", username, role, disabled)
        asyncio.run(self.users.create(user, self.hasher.hash(PASSWORD)))
        return user

    def login(self, username: str, password: str = PASSWORD):
        return self.client.post("/auth/login", json={"username": username, "password": password})

    def token_for(self, username: str) -> str:
        return self.login(username).json()["access_token"]

    def auth(self, username: str) -> dict:
        return {"Authorization": f"Bearer {self.token_for(username)}"}


@pytest.fixture
def stack() -> Stack:
    s = Stack()
    s.add_user("tech1", Role.TECHNICIAN)
    s.add_user("super1", Role.SUPERVISOR)
    s.add_user("admin1", Role.ADMIN)
    return s


# --- login ------------------------------------------------------------------


def test_login_returns_a_bearer_token_and_me_works(stack):
    response = stack.login("tech1")

    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer" and body["role"] == "technician"
    me = stack.client.get("/auth/me", headers={"Authorization": f"Bearer {body['access_token']}"})
    assert me.json()["username"] == "tech1"


def test_wrong_password_and_unknown_user_get_the_same_generic_answer(stack):
    wrong = stack.login("tech1", "not-the-password")
    unknown = stack.login("nobody", PASSWORD)

    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json()["detail"] == unknown.json()["detail"] == "invalid username or password"


def test_a_disabled_account_cannot_log_in(stack):
    stack.add_user("gone", Role.TECHNICIAN, disabled=True)

    assert stack.login("gone").status_code == 401


def test_repeated_failed_logins_are_throttled(stack):
    codes = [stack.login("tech1", "bad").status_code for _ in range(7)]

    assert codes[:5] == [401] * 5
    assert 429 in codes[5:]


def test_the_password_is_never_returned_or_logged_in_responses(stack):
    body = stack.login("tech1").text

    assert PASSWORD not in body and "password_hash" not in body


# --- tokens -----------------------------------------------------------------


def test_missing_and_malformed_tokens_are_rejected(stack):
    assert stack.client.get("/auth/me").status_code == 401
    bad = stack.client.get("/auth/me", headers={"Authorization": "Bearer not.a.token"})
    assert bad.status_code == 401
    assert bad.headers["www-authenticate"] == "Bearer"


def test_an_expired_token_is_rejected():
    past = datetime.now(UTC) - timedelta(hours=3)
    s = Stack(clock=lambda: past)
    s.add_user("tech1", Role.TECHNICIAN)

    token = s.token_for("tech1")

    # the service that issued it in the past now sees the real clock
    fresh = JwtTokenService(SECRET, 60)
    from domain.errors.domain_errors import InvalidTokenError

    with pytest.raises(InvalidTokenError):
        fresh.verify(token)


def test_a_token_signed_with_another_secret_is_rejected(stack):
    forged = jwt.encode(
        {"sub": "u-tech1", "username": "tech1", "role": "admin", "iss": "domain-copilot",
         "exp": int((datetime.now(UTC) + timedelta(hours=1)).timestamp())},
        "some-other-secret-that-is-also-long-enough-0000000",
        algorithm="HS256",
    )

    response = stack.client.get("/auth/me", headers={"Authorization": f"Bearer {forged}"})

    assert response.status_code == 401


def test_an_unsigned_alg_none_token_is_rejected(stack):
    def b64(data: dict) -> str:
        return base64.urlsafe_b64encode(json.dumps(data).encode()).rstrip(b"=").decode()

    exp = int((datetime.now(UTC) + timedelta(hours=1)).timestamp())
    claims = {
        "sub": "u-admin1", "username": "admin1", "role": "admin",
        "iss": "domain-copilot", "exp": exp,
    }
    token = f"{b64({'alg': 'none', 'typ': 'JWT'})}.{b64(claims)}."

    response = stack.client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 401


def test_disabling_an_account_revokes_tokens_it_already_holds(stack):
    headers = stack.auth("tech1")
    assert stack.client.get("/auth/me", headers=headers).status_code == 200

    stack.users.records["u-tech1"] = type(stack.users.records["u-tech1"])(
        User("u-tech1", "tech1", Role.TECHNICIAN, disabled=True),
        stack.users.records["u-tech1"].password_hash,
    )

    assert stack.client.get("/auth/me", headers=headers).status_code == 401


# --- authorization (FR-8) ---------------------------------------------------


def test_permissions_are_enforced_server_side_by_role(stack):
    assert stack.client.get("/_test/decide", headers=stack.auth("tech1")).status_code == 403
    assert stack.client.get("/_test/decide", headers=stack.auth("admin1")).status_code == 403
    ok = stack.client.get("/_test/decide", headers=stack.auth("super1"))
    assert ok.status_code == 200 and ok.json() == {"ok": "super1"}
    assert stack.client.get("/_test/decide").status_code == 401


def test_a_role_change_applies_immediately_not_at_token_expiry(stack):
    headers = stack.auth("tech1")
    assert stack.client.get("/_test/decide", headers=headers).status_code == 403

    record = stack.users.records["u-tech1"]
    stack.users.records["u-tech1"] = type(record)(
        User("u-tech1", "tech1", Role.SUPERVISOR), record.password_hash
    )

    assert stack.client.get("/_test/decide", headers=headers).status_code == 200


def test_technician_cannot_approve_and_admin_cannot_approve_either():
    from domain.value_objects.role import has_permission

    assert not has_permission(Role.TECHNICIAN, Permission.DECIDE_WORK_ORDER)
    assert not has_permission(Role.ADMIN, Permission.DECIDE_WORK_ORDER)
    assert has_permission(Role.SUPERVISOR, Permission.DECIDE_WORK_ORDER)


# --- headers, correlation, limits, errors -----------------------------------


def test_security_headers_are_present(stack):
    response = stack.client.get("/health")

    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert "default-src 'self'" in response.headers["content-security-policy"]
    assert response.headers["cache-control"] == "no-store"


def test_interactive_docs_get_a_looser_csp_than_the_api(stack):
    docs = stack.client.get("/docs")
    api = stack.client.get("/health")

    assert "cdn.jsdelivr.net" in docs.headers["content-security-policy"]
    assert "cdn.jsdelivr.net" not in api.headers["content-security-policy"]


def test_a_safe_request_id_is_echoed_and_an_unsafe_one_is_replaced(stack):
    echoed = stack.client.get("/health", headers={"X-Request-ID": "req-12345678"})
    replaced = stack.client.get("/health", headers={"X-Request-ID": "bad id with spaces!"})

    assert echoed.headers["x-request-id"] == "req-12345678"
    assert replaced.headers["x-request-id"] != "bad id with spaces!"
    assert len(replaced.headers["x-request-id"]) >= 8


def test_an_oversized_body_is_rejected_with_413(stack):
    response = stack.client.post("/auth/login", content=b"x" * 5000,
                                 headers={"Content-Type": "application/json"})

    assert response.status_code == 413


def test_the_global_rate_limit_returns_429_with_retry_after():
    s = Stack(make_settings(rate_limit_per_minute=3))

    codes = [s.client.get("/health") for _ in range(6)]

    assert [r.status_code for r in codes][:3] == [200, 200, 200]
    limited = next(r for r in codes if r.status_code == 429)
    assert int(limited.headers["retry-after"]) >= 1


def test_an_unexpected_error_is_a_generic_500_that_leaks_nothing(stack):
    response = stack.client.get("/_test/boom")

    assert response.status_code == 500
    assert "hunter2" not in response.text and "RuntimeError" not in response.text
    assert response.json()["request_id"] == response.headers["x-request-id"]


def test_readiness_reports_dependency_state(stack):
    async def up():
        return True

    async def down():
        return False

    stack.container.readiness_checks = {"postgres": up}
    assert stack.client.get("/ready").status_code == 200

    stack.container.readiness_checks = {"postgres": up, "qdrant": down}
    degraded = stack.client.get("/ready")
    assert degraded.status_code == 503 and degraded.json()["qdrant"] is False
    assert stack.client.get("/health").status_code == 200


def test_openapi_documents_the_api(stack):
    spec = stack.client.get("/openapi.json").json()

    assert "/auth/login" in spec["paths"] and "/ready" in spec["paths"]


# --- configuration and crypto -----------------------------------------------


def test_a_non_development_environment_refuses_the_default_signing_secret():
    with pytest.raises(RuntimeError):
        make_settings(app_env="production", jwt_secret=DEV_JWT_SECRET).validate()
    make_settings(app_env="production").validate()  # a real secret is accepted


def test_a_short_signing_secret_is_rejected():
    with pytest.raises(ValueError):
        JwtTokenService("too-short")


def test_password_hashes_are_salted_and_reject_tampering():
    hasher = ScryptPasswordHasher()
    first, second = hasher.hash(PASSWORD), hasher.hash(PASSWORD)

    assert first != second
    assert hasher.verify(PASSWORD, first) and not hasher.verify("wrong", first)
    assert not hasher.verify(PASSWORD, first[:-4] + "AAAA")
    assert not hasher.verify(PASSWORD, "garbage")
