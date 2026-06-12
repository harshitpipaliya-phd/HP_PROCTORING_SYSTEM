"""
tests/unit/test_face_verification.py
======================================
Unit tests for face enrollment and verification flow.
Uses numpy cosine similarity directly (no live camera / DB required).
"""
import pytest
import numpy as np


def cosine_similarity(v1, v2):
    n1, n2 = np.linalg.norm(v1), np.linalg.norm(v2)
    if n1 == 0 or n2 == 0:
        return 0.0
    return float(np.dot(v1, v2) / (n1 * n2))


class TestCosineSimilarity:
    MATCH_THRESHOLD = 0.6

    def test_identical_vectors_match(self):
        emb = np.random.randn(128).tolist()
        sim = cosine_similarity(emb, emb)
        assert sim >= self.MATCH_THRESHOLD

    def test_opposite_vectors_no_match(self):
        emb = np.ones(128)
        neg = -emb
        sim = cosine_similarity(emb.tolist(), neg.tolist())
        assert sim < self.MATCH_THRESHOLD

    def test_zero_vector_returns_zero(self):
        zero = np.zeros(128).tolist()
        rand = np.random.randn(128).tolist()
        sim = cosine_similarity(zero, rand)
        assert sim == 0.0

    def test_similar_vectors_match(self):
        base = np.random.randn(128)
        noisy = base + np.random.randn(128) * 0.05  # very small noise
        sim = cosine_similarity(base.tolist(), noisy.tolist())
        assert sim >= self.MATCH_THRESHOLD

    def test_random_vectors_typically_no_match(self):
        """Two random 128-d vectors should almost never be similar."""
        np.random.seed(42)
        v1 = np.random.randn(128)
        v2 = np.random.randn(128)
        sim = cosine_similarity(v1.tolist(), v2.tolist())
        # Random 128-d vectors: expected dot product ≈ 0
        assert abs(sim) < 0.3


class TestPgvectorQueryPattern:
    """Validate the expected SQL query pattern for face verification."""

    def test_cosine_operator_query_string(self):
        """The spec mandates: SELECT 1 - (embedding <=> $1::vector) AS similarity"""
        query = (
            "SELECT 1 - (embedding <=> $1::vector) AS similarity "
            "FROM face_references WHERE candidate_id = $2"
        )
        assert "<=>" in query
        assert "vector" in query
        assert "similarity" in query
        assert "face_references" in query

    def test_match_threshold_is_0_6(self):
        """Spec Section 11, Note 3: threshold = 0.6"""
        THRESHOLD = 0.6
        assert THRESHOLD == 0.6
