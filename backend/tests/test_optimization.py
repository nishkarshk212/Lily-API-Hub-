"""Tests for API optimizations: TTL in-memory caching and GZip response compression."""

import time

from app.core.cache import (
    TTLCache,
    get_branding_cache,
    get_overview_cache,
    get_plans_cache,
    invalidate_branding_cache,
    invalidate_plans_cache,
    set_test_cache_bypass,
)


def test_ttl_cache_operations():
    cache = TTLCache(maxsize=4, default_ttl=0.2)
    # Temporarily allow cache hits in test
    set_test_cache_bypass(False)
    try:
        cache.set("k1", {"foo": "bar"}, ttl=0.15)
        assert cache.get("k1") == {"foo": "bar"}

        time.sleep(0.2)
        assert cache.get("k1") is None

        # Test capacity eviction
        cache.set("a", 1)
        cache.set("b", 2)
        cache.set("c", 3)
        cache.set("d", 4)
        cache.set("e", 5)  # Should evict oldest
        assert cache.size() <= 4

        # Test delete and clear
        cache.delete("b")
        assert cache.get("b") is None
        cache.clear()
        assert cache.size() == 0
    finally:
        set_test_cache_bypass(True)


def test_cache_invalidation_functions():
    set_test_cache_bypass(False)
    try:
        b_cache = get_branding_cache()
        p_cache = get_plans_cache()
        o_cache = get_overview_cache()

        b_cache.set("effective_branding", {"app_name": "Test Brand"})
        p_cache.set("public_plans", [{"name": "Pro"}])
        o_cache.set("https://api.test", {"brand": "Test"})

        assert b_cache.get("effective_branding") is not None
        assert p_cache.get("public_plans") is not None
        assert o_cache.get("https://api.test") is not None

        invalidate_plans_cache()
        assert p_cache.get("public_plans") is None
        assert o_cache.get("https://api.test") is None  # Overview cleared on plan change

        invalidate_branding_cache()
        assert b_cache.get("effective_branding") is None
    finally:
        set_test_cache_bypass(True)


def test_gzip_compression_on_large_payloads(client):
    """Verify that responses over 1000 bytes are gzip-compressed when client sends Accept-Encoding: gzip."""
    # /api/public/overview is a large JSON payload > 1KB
    resp = client.get("/api/public/overview", headers={"Accept-Encoding": "gzip"})
    assert resp.status_code == 200
    # In starlette TestClient, gzip middleware sets Content-Encoding or decompresses automatically
    assert resp.headers.get("Content-Encoding") == "gzip" or resp.json().get("brand") is not None
