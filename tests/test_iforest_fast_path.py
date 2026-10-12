"""Tiny-tree optimization must preserve the numpy tree builder exactly."""
import numpy as np
import pytest

from model.iforest import IsolationForest


class NumpyReference(IsolationForest):
    def _grow_rows(self, rows, depth, limit, rng):
        return self._grow(np.asarray(rows), depth, limit, rng)


@pytest.mark.parametrize("n", [1, 2, 8, 15, 30, 32, 33, 80])
@pytest.mark.parametrize("seed", [0, 7, 42])
def test_tiny_tree_exact_parity(n, seed):
    rng = np.random.default_rng(seed)
    X = rng.normal(size=(n, 6))
    X[:, 1] = X[:, 0]  # duplicate feature
    X[:, 3] = 5.0  # constant feature
    fast = IsolationForest(random_state=seed).fit(X)
    reference = NumpyReference(random_state=seed).fit(X)
    assert fast.trees_ == reference.trees_
    query = rng.normal(size=(20, 6))
    assert np.array_equal(fast.score_samples(query), reference.score_samples(query))


def test_tiny_constant_rows():
    model = IsolationForest().fit(np.ones((15, 6)))
    assert model.trees_ == [("leaf", 15)] * 150


def test_nonfinite_uses_numpy_path():
    class NoScalarPath(IsolationForest):
        def _grow_rows(self, rows, depth, limit, rng):
            raise AssertionError("nonfinite input must retain numpy semantics")

    X = np.ones((8, 2))
    X[0, 0] = np.nan
    assert NoScalarPath().fit(X).trees_ == [("leaf", 8)] * 150


def test_degenerate_split_remains_leaf():
    class LowestThreshold:
        def integers(self, n):
            return 0

        def uniform(self, low, high):
            return low

    model = IsolationForest()
    assert model._grow_rows([[0.0], [1.0]], 0, 2, LowestThreshold()) == ("leaf", 2)
