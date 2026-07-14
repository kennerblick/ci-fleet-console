import time

from app import cache, settings_store


def _fixed_scope(monkeypatch):
    monkeypatch.setattr(settings_store, "scope_key", lambda: "testscope")


def test_get_with_stale_returns_expired_data(monkeypatch, tmp_path):
    _fixed_scope(monkeypatch)
    monkeypatch.setattr(cache.config, "CACHE_DIR", tmp_path)
    cache.put("x", {"v": 1})
    data, fresh = cache.get_with_stale("x", ttl=60)
    assert data == {"v": 1} and fresh
    # Ablauf simulieren
    import os
    p = cache._path("x")
    os.utime(p, (time.time() - 120, time.time() - 120))
    data, fresh = cache.get_with_stale("x", ttl=60)
    assert data == {"v": 1} and not fresh          # stale, aber vorhanden


def test_refresh_in_background_runs_once(monkeypatch, tmp_path):
    _fixed_scope(monkeypatch)
    monkeypatch.setattr(cache.config, "CACHE_DIR", tmp_path)
    calls = []

    def builder():
        calls.append(1)
        time.sleep(0.2)

    cache.refresh_in_background("y", builder)
    cache.refresh_in_background("y", builder)      # Guard: kein Doppelstart
    time.sleep(0.5)
    assert calls == [1]
    cache.refresh_in_background("y", builder)      # nach Abschluss wieder erlaubt
    time.sleep(0.4)
    assert calls == [1, 1]
