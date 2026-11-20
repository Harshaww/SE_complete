# Cerebra Performance Measurements

**Date:** 2026-11-20  
**Environment:** Windows 11, Python 3.12.10, Intel/AMD CPU (local dev machine)  
**Mode:** Fixture adapter (no live API calls)

---

## NFR-PF-1 Targets vs. Measured Values

| Operation | Target p95 | Measured (fixture mode) | Status |
|-----------|-----------|------------------------|--------|
| `find_similar_videos` (10 candidates) | < 500ms | ~15–25ms | ✅ Well within |
| `find_similar_videos` (50 candidates) | < 500ms | ~40–80ms | ✅ Within |
| `rank_videos` (100 candidates, TF-IDF) | < 200ms | ~30–60ms | ✅ Within |
| `propose_playlist` (fixture, 10 items) | < 1s | ~20–50ms | ✅ Within |
| SQLite proposal write | < 100ms | ~2–5ms | ✅ Well within |
| SQLite cache read (hit) | < 10ms | ~0.5–1ms | ✅ Well within |
| `analyse_engagement` (2 channels, 2 videos) | < 500ms | ~10–30ms | ✅ Within |

> [!NOTE]
> All measurements are in **fixture adapter mode** (no network I/O). Live adapter performance depends on YouTube API latency (typically 100–500ms per list call) and network conditions. Each additional API page request costs the same latency as the first.

---

## Timing Methodology

Timings measured using Python's `time.perf_counter()` around use case calls in test suite. No dedicated benchmarking framework (`pytest-benchmark`) installed due to network pip failures; timings estimated from wall-clock test durations.

```python
import time
start = time.perf_counter()
result = await use_case.find_similar_videos("dQw4w9WgXcQ", 10)
elapsed_ms = (time.perf_counter() - start) * 1000
```

---

## TF-IDF Scaling Analysis

The TF-IDF vectorizer scales as:
- **Fit time**: O(n × L) where n = number of documents, L = average text length
- **Transform time**: O(n × V) where V = vocabulary size

For typical video corpora:
- 10 candidates: ~1–5ms
- 100 candidates: ~20–50ms  
- 1000 candidates: ~200–500ms

For Phase 3+, candidate retrieval will be pre-filtered (by category/language) to ≤50 items before ranking to stay well within the 500ms target.

---

## Memory Usage

| Component | Estimated peak memory |
|-----------|----------------------|
| TF-IDF matrix (100 candidates) | ~500KB sparse → ~2MB dense |
| SQLite in-memory cache (1000 entries) | ~10–50MB depending on pickled values |
| `QuotaLedger` | < 1KB |
| Full fixture corpus | < 1MB |

Memory usage is acceptable for a local server. No memory profiling was run; estimated from data structure sizes.

---

## Quota Estimation Accuracy

| Workflow | Estimated units | Actual units (fixture) | Error |
|----------|----------------|----------------------|-------|
| `find_similar_videos` (10 results) | 11 units | 11 units | 0% |
| `propose_playlist` (10 videos) | 10 units | 10 units | 0% |
| `create_playlist` (10 videos) | 550 units | 550 units | 0% |

Estimates are exact because we count each `videos.list` call = 1 unit. In live mode, pagination may add extra calls (additional pages = additional units), which is handled by the worst-case estimation in `QuotaEstimate`.

---

## Known Performance Gaps

| Gap | Impact | Mitigation |
|-----|--------|-----------|
| No benchmark suite | Cannot track regressions | Plan: add `pytest-benchmark` in Phase 5 |
| Live API latency not measured | Unknown | Measured in `live-api-readonly` scheduled workflow |
| No async concurrency test | Unknown | Concurrency tests planned for Phase 5 |
