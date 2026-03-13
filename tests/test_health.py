from main import health


def test_health_check_returns_ok() -> None:
    assert health() == {"status": "ok"}
