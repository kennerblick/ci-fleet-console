from app import security


def test_password_roundtrip():
    salt, digest = security.hash_password("geheim1234")
    assert security.verify_password("geheim1234", salt, digest)
    assert not security.verify_password("falsch", salt, digest)


def test_salts_differ():
    s1, h1 = security.hash_password("x" * 10)
    s2, h2 = security.hash_password("x" * 10)
    assert s1 != s2 and h1 != h2


def test_session_lifecycle():
    token = security.create_session("alice", "user", "local")
    session = security.get_session(token)
    assert session and session["user"] == "alice"
    security.drop_session(token)
    assert security.get_session(token) is None


def test_rate_limit():
    key = security.rate_key("1.2.3.4", "Admin")
    assert not security.rate_blocked(key)
    for _ in range(5):
        security.rate_fail(key)
    assert security.rate_blocked(key)
    security.rate_reset(key)
    assert not security.rate_blocked(key)
