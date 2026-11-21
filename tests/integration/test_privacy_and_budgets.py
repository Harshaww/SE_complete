"""NFR-PV-2 (clear-cache command, retention) and NFR-QU-1 (typical request cost vs the SRS)."""

# mark: NFR-PV-2, NFR-QU-1
from __future__ import annotations

import io
import json
import time

from cerebra.cli import main as cli_main
from cerebra.infrastructure.persistence.sqlite_stores import SQLiteCacheStore
from tests.support.helpers import run
from tests.support.live_env import make_env


def _used(env) -> int:
    return int(env.container.quota.status()["general"]["used"])


# mark: NFR-PV-2
class TestClearCacheCommand:
    def test_clear_cache_deletes_cached_data(self, tmp_path):
        env = make_env(tmp_path)
        cache = env.container.cache
        assert cache is not None
        cache.set("likes:demo", {"x": 1}, 600)
        assert cache.get("likes:demo") is not None
        out = io.StringIO()
        code = cli_main(
            ["clear-cache"], container_factory=lambda: env.container, out=out, err=io.StringIO()
        )
        assert code == 0 and json.loads(out.getvalue()) == {"cache_cleared": True}
        assert cache.get("likes:demo") is None

    def test_retention_caps_ttl(self, tmp_path):
        env = make_env(tmp_path)
        store = SQLiteCacheStore(env.container.cache._db, max_ttl_seconds=60)  # type: ignore[union-attr]
        store.set("k", "v", ttl_seconds=10 * 86400)
        row = store._db.execute("SELECT expires_at FROM cache WHERE key = ?", ("k",))[0]
        assert row["expires_at"] <= time.time() + 61  # capped to the 60 s retention


# mark: NFR-QU-1, FR-5.7
class TestTypicalRequestCost:
    """SRS NFR-QU-1: typical FR-1 <= 250 units, typical FR-4 proposal <= 400 units (actual)."""

    def test_find_similar_actual_cost_within_250(self, tmp_path):
        env = make_env(tmp_path)
        run(env.container.find_similar.find_similar_videos("pyvid000000", limit=10))
        assert 0 < _used(env) <= 250

    def test_propose_actual_cost_within_400(self, tmp_path):
        env = make_env(tmp_path)
        env.propose("python", 900)
        assert 0 < _used(env) <= 400
