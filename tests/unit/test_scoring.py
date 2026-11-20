"""Unit tests for domain/scoring.py (FR-1.5, FR-2.3, B.4)."""
import math
import pytest

from cerebra.domain.scoring import (
    W_TFIDF, W_CATEGORY, W_CHANNEL, W_LANGUAGE, W_DURATION_BAND,
    _WEIGHTS, rank_videos, rank_channels, cosine_similarity_texts,
)
from tests.conftest import make_video, make_channel


class TestWeights:
    def test_weights_sum_to_one(self):
        assert math.isclose(sum(_WEIGHTS), 1.0, rel_tol=1e-9)

    def test_all_weights_positive(self):
        assert all(w > 0 for w in _WEIGHTS)

    def test_tfidf_weight_dominant(self):
        assert W_TFIDF > W_CATEGORY + W_CHANNEL + W_LANGUAGE + W_DURATION_BAND


class TestRankVideos:
    def test_excludes_seed(self):
        seed = make_video(video_id="seed01ABCDE")
        candidates = [seed, make_video(video_id="cand01ABCDE", title="Different video")]
        results = rank_videos(seed, candidates)
        ids = [r.video_id for r in results]
        assert "seed01ABCDE" not in ids

    def test_returns_empty_for_no_candidates(self):
        seed = make_video()
        assert rank_videos(seed, []) == []

    def test_scores_in_zero_one(self):
        seed = make_video(video_id="seed01ABCDE", title="Python tutorial machine learning")
        cands = [
            make_video(video_id=f"cand{i:07d}", title=f"Python ML video {i}",
                       tags=["python", "ml"])
            for i in range(5)
        ]
        results = rank_videos(seed, cands)
        for r in results:
            assert 0.0 <= r.score <= 1.0, f"Score {r.score} out of [0,1]"

    def test_sorted_descending(self):
        seed = make_video(video_id="seed01ABCDE", title="Python tutorial")
        cands = [
            make_video(video_id=f"cand{i:07d}", title=f"{'Python tutorial ' * i} other")
            for i in range(1, 6)
        ]
        results = rank_videos(seed, cands)
        scores = [r.score for r in results]
        assert scores == sorted(scores, reverse=True)

    def test_tie_broken_by_video_id(self):
        """FR-1.9: identical data → ties broken by video_id ascending."""
        seed = make_video(video_id="seed01ABCDE", title="Python")
        # Two candidates with identical content
        c1 = make_video(video_id="AAAAA000001", title="Python tutorial", description="same content")
        c2 = make_video(video_id="BBBBB000002", title="Python tutorial", description="same content")
        results = rank_videos(seed, [c2, c1])  # deliberately reversed input order
        ids = [r.video_id for r in results]
        # Tie broken by ID: AAAAA < BBBBB
        assert ids.index("AAAAA000001") < ids.index("BBBBB000002")

    def test_tags_missing_flag_propagated(self):
        seed = make_video(video_id="seed01ABCDE")
        cand = make_video(video_id="cand01ABCDE", tags=[], tags_missing=True)
        results = rank_videos(seed, [cand])
        assert results[0].tags_missing is True

    def test_same_category_boosts_score(self):
        seed = make_video(video_id="seed01ABCDE", category_id="27", title="Education video")
        same_cat = make_video(video_id="same01ABCDE", category_id="27", title="Education video similar")
        diff_cat = make_video(video_id="diff01ABCDE", category_id="22", title="Education video other")
        results = rank_videos(seed, [same_cat, diff_cat])
        same_score = next(r.score for r in results if r.video_id == "same01ABCDE")
        diff_score = next(r.score for r in results if r.video_id == "diff01ABCDE")
        assert same_score >= diff_score


class TestRankChannels:
    def test_excludes_seed(self):
        seed = make_channel(channel_id="UCuAXFkgsw1L7xaCfnd5JJOw")
        results = rank_channels(seed, [seed])
        assert len(results) == 0

    def test_scores_in_zero_one(self):
        seed = make_channel()
        cands = [
            make_channel(channel_id=f"UCsomeChannel{i:010d}")
            for i in range(5)
        ]
        results = rank_channels(seed, cands)
        for r in results:
            assert 0.0 <= r.score <= 1.0


class TestCosineSimilarityTexts:
    def test_identical_texts_near_one(self):
        score = cosine_similarity_texts("python machine learning", "python machine learning")
        assert math.isclose(score, 1.0, abs_tol=1e-6)

    def test_empty_text_returns_zero(self):
        assert cosine_similarity_texts("", "python") == 0.0
        assert cosine_similarity_texts("python", "") == 0.0

    def test_unrelated_texts_low_score(self):
        score = cosine_similarity_texts("python machine learning", "cooking recipe pasta")
        assert score < 0.3
