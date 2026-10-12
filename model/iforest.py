"""
Isolation Forest, implemented directly on numpy.

Not a reimplementation for its own sake. scikit-learn pulls in scipy, and the
three together are roughly 200MB unpacked, which puts the API past Vercel's
225MB function limit. The algorithm itself is small, so it is cheaper to own it
than to drag scipy into a serverless bundle for one estimator.

This is the algorithm as published (Liu, Ting and Zhou, 2008): build trees that
split on a random feature at a random value, and score a point by how few
splits it takes to isolate it. Anomalies isolate quickly.

`tests/test_iforest.py` checks the ranking against scikit-learn's version.
"""
from __future__ import annotations

from functools import lru_cache

import numpy as np

# A leaf is ("leaf", size). A branch is (feature, threshold, left, right).
Node = tuple


@lru_cache(maxsize=512)
def average_path_length(n: int) -> float:
    """Expected path length of an unsuccessful BST search over n points.

    The normalising constant c(n) from the paper. Without it, scores would
    depend on how many points were sampled per tree.
    """
    if n <= 1:
        return 0.0
    if n == 2:
        return 1.0
    harmonic = np.log(n - 1) + np.euler_gamma
    return 2.0 * harmonic - 2.0 * (n - 1) / n


class IsolationForest:
    """Scale invariant by construction, because every split is drawn inside the
    feature's own range within the node. No standardisation step is needed."""

    def __init__(self, n_estimators: int = 150, max_samples: int = 256,
                 random_state: int = 42):
        self.n_estimators = n_estimators
        self.max_samples = max_samples
        self.random_state = random_state
        self.trees_: list[Node] = []
        self.subsample_size_ = 0
        self._row_ranges: dict | None = None

    def _grow(self, X: np.ndarray, depth: int, limit: int, rng) -> Node:
        n = len(X)
        if depth >= limit or n <= 1:
            return ("leaf", n)

        # Only features that actually vary can isolate anything.
        low, high = X.min(axis=0), X.max(axis=0)
        usable = np.flatnonzero(high > low)
        if usable.size == 0:
            return ("leaf", n)

        feature = int(usable[rng.integers(usable.size)])
        threshold = float(rng.uniform(low[feature], high[feature]))
        mask = X[:, feature] < threshold
        left_count = int(np.count_nonzero(mask))
        if left_count == 0 or left_count == n:
            return ("leaf", n)

        return (
            feature,
            threshold,
            self._grow(X[mask], depth + 1, limit, rng),
            self._grow(X[~mask], depth + 1, limit, rng),
        )

    def _grow_rows(self, rows: list[list[float]], depth: int, limit: int, rng) -> Node:
        """Build tiny trees without allocating arrays at every branch.

        The feature order, random draws, comparisons and recursion order match
        _grow exactly. Larger/non-finite inputs retain the numpy path.
        """
        n = len(rows)
        if depth >= limit or n <= 1:
            return ("leaf", n)
        if n == 2:
            first, second = rows
            cache = self._row_ranges
            key = frozenset((id(first), id(second))) if cache is not None else None
            usable = cache.get(key) if cache is not None else None
            if usable is None:
                usable = [i for i in range(len(first)) if first[i] != second[i]]
                if cache is not None:
                    cache[key] = usable
            if not usable:
                return ("leaf", n)
            feature = int(usable[rng.integers(len(usable))])
            a, b = first[feature], second[feature]
            lower, upper = (a, b) if a < b else (b, a)
            threshold = float(rng.uniform(lower, upper))
            if threshold <= lower:
                return ("leaf", n)
            return (feature, threshold, ("leaf", 1), ("leaf", 1))

        cache = self._row_ranges
        key = frozenset(map(id, rows)) if cache is not None else None
        ranges = cache.get(key) if cache is not None else None
        if ranges is None:
            columns = list(zip(*rows))
            low = [min(column) for column in columns]
            high = [max(column) for column in columns]
            usable = [i for i in range(len(low)) if high[i] > low[i]]
            if cache is not None:
                cache[key] = (low, high, usable)
        else:
            low, high, usable = ranges
        if not usable:
            return ("leaf", n)
        feature = int(usable[rng.integers(len(usable))])
        threshold = float(rng.uniform(low[feature], high[feature]))
        left: list[list[float]] = []
        right: list[list[float]] = []
        for row in rows:
            (left if row[feature] < threshold else right).append(row)
        if not left or not right:
            return ("leaf", n)
        return (
            feature, threshold,
            self._grow_rows(left, depth + 1, limit, rng),
            self._grow_rows(right, depth + 1, limit, rng),
        )

    def fit(self, X: np.ndarray) -> IsolationForest:
        X = np.asarray(X, dtype=float)
        n = len(X)
        if n == 0:
            raise ValueError("cannot fit on an empty set")

        self.subsample_size_ = min(self.max_samples, n)
        limit = max(1, int(np.ceil(np.log2(max(self.subsample_size_, 2)))))
        rng = np.random.default_rng(self.random_state)

        self.trees_ = []
        # The API normally fits 8-30 rows. Python scalars avoid thousands of
        # small numpy reductions/copies, without changing the learned forest.
        rows = X.tolist() if n <= 32 and np.isfinite(X).all() else None
        # Ranges depend only on row membership, not ordering or random draws.
        # Share them within this fit only; never cache trees or model results.
        self._row_ranges = {} if rows is not None else None
        for _ in range(self.n_estimators):
            idx = rng.choice(n, self.subsample_size_, replace=n < self.subsample_size_)
            if rows is not None:
                self.trees_.append(self._grow_rows([rows[i] for i in idx], 0, limit, rng))
            else:
                self.trees_.append(self._grow(X[idx], 0, limit, rng))
        self._row_ranges = None
        return self

    def _path_length(self, x: np.ndarray, node: Node) -> float:
        depth = 0
        while node[0] != "leaf":
            feature, threshold, left, right = node
            node = left if x[feature] < threshold else right
            depth += 1
        # A leaf holding several points would have kept splitting given depth,
        # so charge the expected remaining depth for those points.
        return depth + average_path_length(node[1])

    def score_samples(self, X: np.ndarray) -> np.ndarray:
        """Anomaly score in (0, 1). Higher means more anomalous."""
        if not self.trees_:
            raise ValueError("fit must be called before scoring")
        X = np.asarray(X, dtype=float)
        c = average_path_length(self.subsample_size_)
        if c <= 0:
            return np.full(len(X), 0.5)
        trees = self.trees_
        mean_depth = np.array([
            sum(self._path_length(x, tree) for tree in trees) / len(trees) for x in X.tolist()
        ])
        return 2.0 ** (-mean_depth / c)
