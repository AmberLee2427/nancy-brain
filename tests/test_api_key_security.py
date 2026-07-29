import sqlite3

from connectors.http_api import auth
from connectors.http_api.rate_limit import SlidingWindowRateLimiter


def test_principal_weights_are_private_persistent_and_clamped(tmp_path, monkeypatch):
    db_path = tmp_path / "users.db"
    monkeypatch.setattr(auth, "DB_PATH", str(db_path))
    auth.create_api_key_weight_table()

    first = auth.api_key_principal("first-key")
    second = auth.api_key_principal("second-key")
    assert first != second
    assert "first-key" not in first

    assert auth.set_principal_weight(first, "docs/a.md", 9.0) == 2.0
    assert auth.set_principal_weight(second, "docs/a.md", 0.1) == 0.5

    assert auth.get_principal_weights(first) == {"docs/a.md": 2.0}
    assert auth.get_principal_weights(second) == {"docs/a.md": 0.5}

    # Reopening through a new connection demonstrates that preferences are durable.
    with sqlite3.connect(db_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM api_key_weights").fetchone()[0] == 2


def test_expired_principal_weights_are_removed(tmp_path, monkeypatch):
    db_path = tmp_path / "users.db"
    monkeypatch.setattr(auth, "DB_PATH", str(db_path))
    auth.create_api_key_weight_table()
    principal = auth.api_key_principal("expiring-key")

    auth.set_principal_weight(principal, "docs/a.md", 1.5, ttl_days=0)

    assert auth.get_principal_weights(principal) == {}


def test_sliding_window_rate_limiter_can_be_disabled():
    limiter = SlidingWindowRateLimiter(limit=0, window_seconds=60)
    for _ in range(100):
        assert limiter.check("user") == (True, 0)


def test_sliding_window_rate_limiter_rejects_over_limit():
    limiter = SlidingWindowRateLimiter(limit=2, window_seconds=60)

    assert limiter.check("user") == (True, 0)
    assert limiter.check("user") == (True, 0)
    allowed, retry_after = limiter.check("user")

    assert allowed is False
    assert 1 <= retry_after <= 60
    assert limiter.check("other-user") == (True, 0)
