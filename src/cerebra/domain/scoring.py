"""TF-IDF / cosine similarity + weighted scoring (FR-1.5, B.4).

Weights (ADR decision, approved by team):
  w1 = 0.60  TF-IDF cosine over text corpus
  w2 = 0.15  category match
  w3 = 0.10  same channel
  w4 = 0.10  language match
  w5 = 0.05  duration band match

All weights sum to 1.0.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer

from cerebra.domain.entities import ChannelMetadata, DurationBand, VideoMetadata

# Approved weights (FR-2.3 ADR)
W_TFIDF = 0.60
W_CATEGORY = 0.15
W_CHANNEL = 0.10
W_LANGUAGE = 0.10
W_DURATION_BAND = 0.05

_WEIGHTS = (W_TFIDF, W_CATEGORY, W_CHANNEL, W_LANGUAGE, W_DURATION_BAND)
assert math.isclose(sum(_WEIGHTS), 1.0), "Weights must sum to 1.0"


@dataclass(frozen=True)
class VideoScoreResult:
    video_id: str
    score: float  # ∈ [0, 1]
    tags_missing: bool


@dataclass(frozen=True)
class ChannelScoreResult:
    channel_id: str
    score: float  # ∈ [0, 1]


def _cosine(a: np.ndarray, b: np.ndarray) -> float:
    """Cosine similarity between two dense vectors. Returns 0 for zero vectors."""
    norm_a = float(np.linalg.norm(a))
    norm_b = float(np.linalg.norm(b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return float(np.dot(a, b) / (norm_a * norm_b))


def _clamp(val: float) -> float:
    return max(0.0, min(1.0, val))


def rank_videos(
    seed: VideoMetadata,
    candidates: Sequence[VideoMetadata],
) -> list[VideoScoreResult]:
    """Score and rank candidates against seed (FR-1.5, FR-1.9).

    Returns results sorted by descending score, ties broken by video_id (FR-1.9).
    The seed itself is excluded.
    Does NOT filter by FR-1.7 limit — caller applies that.
    """
    if not candidates:
        return []

    # Build corpus: seed first, then candidates (excluding seed duplicates)
    filtered = [c for c in candidates if c.video_id != seed.video_id]
    if not filtered:
        return []

    all_texts = [seed.text_corpus()] + [c.text_corpus() for c in filtered]

    # TF-IDF vectorisation
    vec = TfidfVectorizer(
        strip_accents="unicode",
        lowercase=True,
        ngram_range=(1, 2),
        min_df=1,
        sublinear_tf=True,
    )
    try:
        tfidf_matrix = vec.fit_transform(all_texts).toarray()
    except ValueError:
        # Empty vocabulary (e.g. all texts are empty)
        tfidf_matrix = np.zeros((len(all_texts), 1))

    seed_vec = tfidf_matrix[0]
    seed_band = DurationBand.from_seconds(seed.duration_seconds)

    results: list[VideoScoreResult] = []
    for idx, cand in enumerate(filtered):
        cand_vec = tfidf_matrix[idx + 1]
        cosine_score = _cosine(seed_vec, cand_vec)

        category_match = 1.0 if seed.category_id and seed.category_id == cand.category_id else 0.0
        same_channel = 1.0 if seed.channel_id == cand.channel_id else 0.0
        lang_match = (
            1.0 if seed.language and cand.language and seed.language == cand.language else 0.0
        )
        band_match = 1.0 if DurationBand.from_seconds(cand.duration_seconds) == seed_band else 0.0

        score = _clamp(
            W_TFIDF * cosine_score
            + W_CATEGORY * category_match
            + W_CHANNEL * same_channel
            + W_LANGUAGE * lang_match
            + W_DURATION_BAND * band_match
        )

        results.append(
            VideoScoreResult(
                video_id=cand.video_id,
                score=score,
                tags_missing=cand.tags_missing,
            )
        )

    # Sort: descending score, then ascending video_id as tie-break (FR-1.9)
    results.sort(key=lambda r: (-r.score, r.video_id))
    return results


def rank_channels(
    seed: ChannelMetadata,
    candidates: Sequence[ChannelMetadata],
) -> list[ChannelScoreResult]:
    """Score and rank channel candidates against seed (FR-1.5)."""
    filtered = [c for c in candidates if c.channel_id != seed.channel_id]
    if not filtered:
        return []

    all_texts = [seed.text_corpus()] + [c.text_corpus() for c in filtered]
    vec = TfidfVectorizer(
        strip_accents="unicode", lowercase=True, ngram_range=(1, 2), min_df=1, sublinear_tf=True
    )
    try:
        tfidf_matrix = vec.fit_transform(all_texts).toarray()
    except ValueError:
        tfidf_matrix = np.zeros((len(all_texts), 1))

    seed_vec = tfidf_matrix[0]
    seed_topics = set(seed.topic_categories)

    results: list[ChannelScoreResult] = []
    for idx, cand in enumerate(filtered):
        cand_vec = tfidf_matrix[idx + 1]
        cosine_score = _cosine(seed_vec, cand_vec)

        topic_match = 1.0 if seed_topics and set(cand.topic_categories) & seed_topics else 0.0
        lang_match = (
            1.0 if seed.language and cand.language and seed.language == cand.language else 0.0
        )
        cadence_match = (
            1.0
            if seed.upload_cadence_per_month > 0
            and cand.upload_cadence_per_month > 0
            and abs(seed.upload_cadence_per_month - cand.upload_cadence_per_month)
            <= seed.upload_cadence_per_month * 0.5
            else 0.0
        )

        # Channel: use w1=TF-IDF, w2=topic, w4=lang, w5=cadence; w3(channel)=0
        score = _clamp(
            W_TFIDF * cosine_score
            + W_CATEGORY * topic_match
            + W_LANGUAGE * lang_match
            + W_DURATION_BAND * cadence_match
        )

        results.append(ChannelScoreResult(channel_id=cand.channel_id, score=score))

    results.sort(key=lambda r: (-r.score, r.channel_id))
    return results


def cosine_similarity_texts(text_a: str, text_b: str) -> float:
    """Utility: cosine similarity between two raw text strings.

    Returns 0.0 if either text is empty, produces an empty vocabulary,
    or either TF-IDF vector is the zero vector (undefined cosine).
    """
    if not text_a.strip() or not text_b.strip():
        return 0.0
    vec = TfidfVectorizer(
        strip_accents="unicode",
        lowercase=True,
        sublinear_tf=True,
        token_pattern=r"(?u)\b\w+\b",  # noqa: S106 - regex, not a secret
    )
    try:
        m = vec.fit_transform([text_a, text_b]).toarray()
    except ValueError:
        # Empty vocabulary after tokenisation (all tokens filtered)
        return 0.0
    return _cosine(m[0], m[1])
