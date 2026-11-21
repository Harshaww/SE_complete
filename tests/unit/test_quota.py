"""Unit tests for domain/quota.py (FR-5.6–5.8, NFR-SA-4, TR-6)."""

from cerebra.domain.quota import QUOTA_COSTS, QuotaLedger


class TestQuotaLedger:
    def test_initial_remaining_full(self):
        q = QuotaLedger(general_budget=10000, search_budget=100)
        assert q.general_remaining == 10000
        assert q.search_remaining == 100

    def test_reserve_reduces_remaining(self):
        q = QuotaLedger(general_budget=10000, search_budget=100)
        result = q.reserve(general=500, search=1)
        assert result is True
        assert q.general_remaining == 9500
        assert q.search_remaining == 99

    def test_release_restores_remaining(self):
        q = QuotaLedger(general_budget=10000, search_budget=100)
        q.reserve(general=500, search=5)
        q.release(general=500, search=5)
        assert q.general_remaining == 10000
        assert q.search_remaining == 100

    def test_cannot_reserve_more_than_capacity(self):
        q = QuotaLedger(general_budget=100, search_budget=10)
        result = q.reserve(general=200, search=0)
        assert result is False
        # Remaining unchanged after failed reserve
        assert q.general_remaining == 100

    def test_atomic_reserve_both_pools(self):
        """If search pool is insufficient, general pool must NOT be reserved."""
        q = QuotaLedger(general_budget=10000, search_budget=0)
        result = q.reserve(general=100, search=1)
        assert result is False
        assert q.general_remaining == 10000  # general NOT consumed

    def test_consume_moves_from_reserved_to_used(self):
        q = QuotaLedger(general_budget=10000, search_budget=100)
        q.reserve(general=200, search=1)
        q.consume("videos.list", 1)
        status = q.status()
        assert status["general"]["used"] == 1  # 1 unit for videos.list

    def test_over_budget_workflow_rejected_zero_provider_calls(self):
        """TR-6: over-budget workflow rejected; FR-5.8."""
        q = QuotaLedger(general_budget=10, search_budget=100)
        result = q.can_afford(general=50, search=1)
        assert result is False

    def test_quota_exhausted_search_pool(self):
        q = QuotaLedger(general_budget=10000, search_budget=0)
        result = q.can_afford(general=1, search=1)
        assert result is False

    def test_warn_threshold_in_status(self):
        q = QuotaLedger(general_budget=100, search_budget=100)
        q.reserve(general=85, search=0)
        status = q.status()
        assert status["general"]["warn"] is True

    def test_status_includes_stale_quota_note(self):
        q = QuotaLedger()
        status = q.status()
        assert "NFR-QU-1" in status["note"] or "stale" in status["note"]

    def test_consume_search_decrements_search_pool(self):
        q = QuotaLedger(general_budget=10000, search_budget=100)
        q.reserve(general=100, search=1)
        q.consume("search.list", 1)
        assert q.search_remaining <= 99

    def test_parallel_reserve_never_overspend(self):
        """Concurrency: parallel reserves must never exceed budget."""
        import threading

        q = QuotaLedger(general_budget=1000, search_budget=100)
        successes = []
        lock = threading.Lock()

        def try_reserve():
            ok = q.reserve(general=600, search=0)
            with lock:
                successes.append(ok)

        threads = [threading.Thread(target=try_reserve) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # At most 1 of the 600-unit reserves can succeed (1000 // 600 = 1)
        assert sum(successes) <= 1
        assert q.general_remaining >= 0


class TestQuotaCosts:
    def test_all_expected_methods_present(self):
        expected = [
            "search.list",
            "videos.list",
            "channels.list",
            "playlistItems.list",
            "playlists.list",
            "playlists.insert",
            "playlistItems.insert",
        ]
        for method in expected:
            assert method in QUOTA_COSTS, f"Missing cost for {method}"

    def test_write_costs_correct(self):
        assert QUOTA_COSTS["playlists.insert"] == 50
        assert QUOTA_COSTS["playlistItems.insert"] == 50

    def test_read_costs_correct(self):
        assert QUOTA_COSTS["videos.list"] == 1
        assert QUOTA_COSTS["channels.list"] == 1
