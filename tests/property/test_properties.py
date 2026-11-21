"""Property-based tests (Hypothesis) – Lab Part A.

Exactly 5 required tests. Uses >= 3 of 4 lab patterns.
Each test has a one-sentence comment stating the property.
"""

from __future__ import annotations

import math

import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st

from cerebra.domain.duration import parse_duration, seconds_to_iso8601
from cerebra.domain.entities import ProposalState
from cerebra.domain.playlist_solver import solve_playlist
from cerebra.domain.quota import QuotaLedger
from cerebra.domain.scoring import _WEIGHTS, cosine_similarity_texts, rank_videos
from tests.conftest import make_video

# ── Strategies ────────────────────────────────────────────────────────────────

valid_seconds = st.integers(min_value=0, max_value=86400 * 7)  # 0 to 7 days
positive_seconds = st.integers(min_value=1, max_value=86400 * 7)
duration_seconds_in_range = st.integers(min_value=0, max_value=7200)
quota_amount = st.integers(min_value=0, max_value=5000)
video_id_strategy = st.text(
    alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-",
    min_size=11,
    max_size=11,
)
text_strategy = st.text(
    alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd", "Zs")),
    min_size=1,
    max_size=200,
)


# ═══════════════════════════════════════════════════════════════════════════════
# TEST 1 – ROUND TRIP (pattern: round-trip / inverse)
# Property: converting seconds to ISO 8601 and back is lossless for all valid durations.
# ═══════════════════════════════════════════════════════════════════════════════


@given(seconds=valid_seconds)
@settings(max_examples=500)
def test_round_trip_seconds_iso8601(seconds: int) -> None:
    """ROUND TRIP: seconds → ISO 8601 → parse_duration == seconds (FR-4.2)."""
    iso = seconds_to_iso8601(seconds)
    recovered = parse_duration(iso)
    assert recovered == seconds, f"Round-trip failed: {seconds} → {iso!r} → {recovered}"


# ═══════════════════════════════════════════════════════════════════════════════
# TEST 2 – ORDER DOES NOT MATTER (pattern: order-does-not-matter)
# Property: permuting the candidate list order yields the same final ranking and
#           scores, because ties are broken by video_id (FR-1.9).
# ═══════════════════════════════════════════════════════════════════════════════


@given(
    num_candidates=st.integers(min_value=2, max_value=10),
    seed=st.random_module(),
)
@settings(max_examples=200)
def test_ranking_order_does_not_matter(num_candidates: int, seed) -> None:
    """ORDER DOES NOT MATTER: permuting candidate order leaves ranking unchanged (FR-1.9)."""
    import random

    rng = random.Random(seed.seed)

    base_seed = make_video(
        video_id="seedXXXXXXX", title="Python machine learning tutorial", tags=["python", "ml"]
    )

    # Build candidates with distinct IDs
    candidates = [
        make_video(
            video_id=f"cand{i:07d}",
            title=f"Python tutorial part {i}",
            tags=["python", "tutorial"],
            category_id="27",
            language="en",
            duration_seconds=rng.randint(300, 1200),
        )
        for i in range(num_candidates)
    ]

    result_original = rank_videos(base_seed, candidates)
    shuffled = candidates[:]
    rng.shuffle(shuffled)
    result_shuffled = rank_videos(base_seed, shuffled)

    # Same IDs in same order
    assert [r.video_id for r in result_original] == [r.video_id for r in result_shuffled], (
        "Ranking changed when candidate order was permuted — violates FR-1.9 determinism"
    )
    # Same scores
    for a, b in zip(result_original, result_shuffled):
        assert math.isclose(a.score, b.score, abs_tol=1e-9), (
            f"Score changed: {a.score} vs {b.score} for video {a.video_id}"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# TEST 3 – STRUCTURE (pattern: structure)
# Property: cosine similarity is in [0,1] and cos(a,a)≈1 for non-empty text;
#           weighted_score is in [0,1] and weights sum to 1.
# ═══════════════════════════════════════════════════════════════════════════════


@given(text=text_strategy)
@settings(max_examples=300)
def test_cosine_structure_and_weights(text: str) -> None:
    """STRUCTURE: cosine similarity ∈ [0,1]; cos(a,a)≈1 for non-empty; weights sum to 1 (FR-1.5)."""
    assume(text.strip())  # non-empty

    # cos(a, a) ≈ 1
    score_self = cosine_similarity_texts(text, text)
    text_preview = repr(text[:30])
    assert math.isclose(score_self, 1.0, abs_tol=1e-6), (
        f"cos(a,a) = {score_self} for text={text_preview}"
    )

    # cos(a, b) ∈ [0, 1]
    other = "completely unrelated content xyz 123"
    score_other = cosine_similarity_texts(text, other)
    assert 0.0 <= score_other <= 1.0 + 1e-9, f"cosine similarity {score_other} out of [0,1]"

    # weights sum to 1
    assert math.isclose(sum(_WEIGHTS), 1.0, rel_tol=1e-9), f"Weights {_WEIGHTS} do not sum to 1"


@given(
    num_candidates=st.integers(min_value=1, max_value=10),
    seed_id=video_id_strategy,
)
@settings(max_examples=200)
def test_weighted_score_in_range(num_candidates: int, seed_id: str) -> None:
    """STRUCTURE: weighted_score for every candidate is in [0,1] (B.4)."""
    assume(len(seed_id) == 11)
    seed = make_video(video_id=seed_id, title="Machine learning Python deep learning")
    candidates = [
        make_video(
            video_id=f"cand{i:07d}",
            title=f"Video {i} about deep learning",
            category_id="27" if i % 2 == 0 else "28",
        )
        for i in range(num_candidates)
        if f"cand{i:07d}" != seed_id  # avoid accidental seed collision
    ]
    if not candidates:
        return
    results = rank_videos(seed, candidates)
    for r in results:
        assert 0.0 <= r.score <= 1.0 + 1e-9, (
            f"Weighted score {r.score} out of [0,1] for video {r.video_id}"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# TEST 4 – STRUCTURE (pattern: structure) — playlist solver
# Property: solver output satisfies ALL hard constraints: total ≤ requested total,
#           every video ≤ max_length, matches language, no duplicate IDs,
#           and either total ≥ fill_ratio OR an explicit infeasible reason is given.
# ═══════════════════════════════════════════════════════════════════════════════


@given(
    num_videos=st.integers(min_value=0, max_value=20),
    total_secs=st.integers(min_value=60, max_value=7200),
    max_vid_secs=st.integers(min_value=60, max_value=3600),
    fill_ratio=st.floats(min_value=0.5, max_value=1.0),
)
@settings(max_examples=300)
def test_playlist_solver_structure(
    num_videos: int,
    total_secs: int,
    max_vid_secs: int,
    fill_ratio: float,
) -> None:
    """STRUCTURE: solver output satisfies all hard constraints (FR-4.1 to FR-4.3)."""
    assume(math.isfinite(fill_ratio))
    assume(0 < fill_ratio <= 1.0)

    candidates = [
        make_video(
            video_id=f"vid{i:08d}",
            duration_seconds=max(1, (i + 1) * 60),  # varied durations
            language="en",
        )
        for i in range(num_videos)
    ]

    result = solve_playlist(
        topic="test",
        total_duration_seconds=total_secs,
        candidates=candidates,
        max_video_duration_seconds=max_vid_secs,
        language="en",
        fill_ratio=fill_ratio,
    )

    # Hard constraint 1: total ≤ requested
    assert result.total_seconds <= total_secs, (
        f"Total {result.total_seconds} > requested {total_secs}"
    )

    # Hard constraint 2: every video ≤ max_video_duration
    for item in result.items:
        assert item.duration_seconds <= max_vid_secs, (
            f"Item {item.video_id} duration {item.duration_seconds} > max {max_vid_secs}"
        )

    # Hard constraint 3: no duplicate IDs
    ids = [item.video_id for item in result.items]
    assert len(ids) == len(set(ids)), f"Duplicate video IDs: {ids}"

    # Soft constraint: feasibility correctly reported
    min_total = int(total_secs * fill_ratio)
    if result.feasible:
        assert result.total_seconds >= min_total, (
            f"Marked feasible but total {result.total_seconds} < min {min_total}"
        )
    else:
        assert result.infeasible_reason, "Marked infeasible but no infeasible_reason given"


# ═══════════════════════════════════════════════════════════════════════════════
# TEST 5 – RECURRENCE / STATE (pattern: recurrence)
# Property: quota ledger remaining(after reserve n) == remaining(before) - n and
#           release restores it; proposal state machine only follows B.3 transitions
#           and terminal states never transition.
# ═══════════════════════════════════════════════════════════════════════════════


@given(
    reserve_amounts=st.lists(
        st.integers(min_value=0, max_value=500),
        min_size=1,
        max_size=10,
    ),
    budget=st.integers(min_value=1000, max_value=10000),
)
@settings(max_examples=300)
def test_quota_ledger_recurrence(reserve_amounts: list[int], budget: int) -> None:
    """RECURRENCE: remaining(after reserve n) == remaining(before) - n; release restores (FR-5.8)."""
    q = QuotaLedger(general_budget=budget, search_budget=budget)

    for amount in reserve_amounts:
        before = q.general_remaining
        ok = q.reserve(general=amount, search=0)
        after = q.general_remaining

        if ok:
            assert after == before - amount, (
                f"After reserving {amount}: expected {before - amount}, got {after}"
            )
            # Release and verify restoration
            q.release(general=amount, search=0)
            assert q.general_remaining == before, (
                f"After release: expected {before}, got {q.general_remaining}"
            )
        else:
            # Failed reserve: remaining unchanged
            assert after == before, f"Failed reserve changed remaining: {before} → {after}"

        # Remaining is always non-negative
        assert q.general_remaining >= 0


@given(
    event_sequence=st.lists(
        st.sampled_from(
            ["confirm", "expire", "cancel", "partial_success", "partial_fail", "succeed", "fail"]
        ),
        min_size=1,
        max_size=15,
    )
)
@settings(max_examples=400)
def test_state_machine_recurrence(event_sequence: list[str]) -> None:
    """RECURRENCE/STATE: state machine only follows B.3 transitions; terminal states never transition."""
    from cerebra.domain.state_machine import StateMachineError, transition

    state = ProposalState.PROPOSED
    terminal_hit = False

    for event in event_sequence:
        if terminal_hit:
            # Terminal states MUST NOT transition
            for target in ProposalState:
                with pytest.raises(StateMachineError):
                    transition("prop-id", state, target)
            break

        # Map event to attempted transition
        transitions_map = {
            "confirm": ProposalState.CONFIRMED,
            "expire": ProposalState.EXPIRED,
            "cancel": ProposalState.CANCELLED,
            "partial_success": ProposalState.PARTIAL,
            "partial_fail": ProposalState.FAILED,
            "succeed": ProposalState.CREATED,
            "fail": ProposalState.FAILED,
        }
        target = transitions_map[event]

        try:
            new_state = transition("prop-id", state, target)
            # Transition succeeded — must be in allowed_transitions
            assert target in state.allowed_transitions(), (
                f"Transition {state.value}→{target.value} succeeded but not in allowed set"
            )
            state = new_state
            if state.is_terminal():
                terminal_hit = True
        except StateMachineError:
            # Transition rejected — must NOT be in allowed_transitions
            assert target not in state.allowed_transitions(), (
                f"Transition {state.value}→{target.value} was rejected but IS in allowed set"
            )


# ═══════════════════════════════════════════════════════════════════════════════
# EXTRA (clearly marked) – idempotence of normalise_video_ref
# ═══════════════════════════════════════════════════════════════════════════════


@given(
    vid_id=st.text(
        alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-",
        min_size=11,
        max_size=11,
    )
)
@settings(max_examples=300)
def test_extra_normalise_idempotence(vid_id: str) -> None:
    """EXTRA – idempotence: normalise(normalise(x)) == normalise(x) for valid video IDs."""
    from cerebra.domain.normalise import normalise_video_ref

    first = normalise_video_ref(vid_id)
    second = normalise_video_ref(first)
    assert first == second, f"normalise not idempotent: {vid_id!r} → {first!r} → {second!r}"
