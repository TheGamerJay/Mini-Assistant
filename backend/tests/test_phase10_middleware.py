"""
tests/test_phase10_middleware.py

Unit tests for Phase 10 — Auth middleware, Rate limiter, Request tracer.
All tests are in-process (no live server needed).
"""
import sys
import os
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from mini_assistant.phase10.rate_limiter import _SlidingWindow


# ── Sliding Window Rate Limiter ───────────────────────────────────────────────

class TestSlidingWindow:
    def test_allows_within_limit(self):
        w = _SlidingWindow(limit=5, window_s=60)
        for _ in range(5):
            assert w.is_allowed("client1") is True

    def test_blocks_over_limit(self):
        w = _SlidingWindow(limit=3, window_s=60)
        for _ in range(3):
            w.is_allowed("client1")
        # 4th request should be blocked
        assert w.is_allowed("client1") is False

    def test_different_keys_independent(self):
        w = _SlidingWindow(limit=2, window_s=60)
        w.is_allowed("A")
        w.is_allowed("A")
        # A is at limit; B should still be allowed
        assert w.is_allowed("A") is False
        assert w.is_allowed("B") is True

    def test_window_expiry(self):
        w = _SlidingWindow(limit=2, window_s=1)  # 1-second window
        w.is_allowed("key")
        w.is_allowed("key")
        assert w.is_allowed("key") is False
        # Wait for window to expire
        time.sleep(1.1)
        # Should be allowed again
        assert w.is_allowed("key") is True

    def test_retry_after_positive(self):
        w = _SlidingWindow(limit=1, window_s=10)
        w.is_allowed("key")
        w.is_allowed("key")  # over limit
        assert w.retry_after("key") > 0

    def test_stats(self):
        w = _SlidingWindow(limit=10, window_s=60)
        w.is_allowed("x")
        w.is_allowed("x")
        stats = w.stats("x")
        assert stats["count"] == 2
        assert stats["limit"] == 10
        assert stats["window_s"] == 60


# ── Auth middleware (unit-level key loading) ──────────────────────────────────

class TestAuthKeyLoading:
    def test_no_key_returns_empty_set(self):
        os.environ.pop("API_KEY", None)
        from mini_assistant.phase10.auth_middleware import _load_keys
        keys = _load_keys()
        assert keys == set()

    def test_single_key(self):
        os.environ["API_KEY"] = "test-key-123"
        from mini_assistant.phase10.auth_middleware import _load_keys
        keys = _load_keys()
        assert "test-key-123" in keys
        del os.environ["API_KEY"]

    def test_multi_key_comma_separated(self):
        os.environ["API_KEY"] = "key-a,key-b, key-c "
        from mini_assistant.phase10.auth_middleware import _load_keys
        keys = _load_keys()
        assert "key-a" in keys
        assert "key-b" in keys
        assert "key-c" in keys
        del os.environ["API_KEY"]


# ── Request tracer context var ────────────────────────────────────────────────

class TestRequestTracer:
    def test_get_request_id_default_empty(self):
        from mini_assistant.phase10.request_tracer import get_request_id
        assert get_request_id() == ""


# ── Health checks (import-only test) ─────────────────────────────────────────

class TestHealthChecksImport:
    def test_module_importable(self):
        from mini_assistant.phase10 import health_checks  # noqa
        assert hasattr(health_checks, "run_health_checks")

    def test_disk_probe_returns_dict(self):
        from mini_assistant.phase10.health_checks import _probe_disk
        result = _probe_disk()
        assert "name" in result
        assert result["name"] == "disk"
        assert "status" in result
        assert result["status"] in ("ok", "warn", "critical", "error")

    def test_phases_probe(self):
        from mini_assistant.phase10.health_checks import _probe_phases
        result = _probe_phases()
        assert result["name"] == "phases"
        assert "details" in result
        # phase8 + phase9 + phase10 should be ok
        assert result["details"].get("phase8") == "ok"
        assert result["details"].get("phase9") == "ok"
        assert result["details"].get("phase10") == "ok"
