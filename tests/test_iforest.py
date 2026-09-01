"""Check the numpy Isolation Forest against scikit-learn's.

scikit-learn is a dev-only dependency, so this file skips when it is absent.
The API ships without it, see model/iforest.py for why.
"""
import numpy as np
import pytest

from model.iforest import IsolationForest, average_path_length

sklearn_ensemble = pytest.importorskip("sklearn.ensemble")


def blob_with_outliers(seed=0, n=300, k=12):
    rng = np.random.default_rng(seed)
    inliers = rng.normal(0, 1, size=(n, 4))
    outliers = rng.uniform(6, 10, size=(k, 4))
    return np.vstack([inliers, outliers]), n


def test_average_path_length_matches_sklearn():
    from sklearn.ensemble._iforest import _average_path_length as sk

    for n in (1, 2, 3, 10, 64, 256, 1000):
        assert np.isclose(average_path_length(n), sk(np.array([n]))[0], atol=1e-9)


@pytest.mark.parametrize("seed", [0, 1, 2])
def test_outliers_rank_above_inliers(seed):
    """The property that matters: planted outliers score higher than the blob."""
    X, n = blob_with_outliers(seed)
    scores = IsolationForest(random_state=seed).fit(X).score_samples(X)
    assert scores[n:].min() > scores[:n].mean(), "outliers did not separate"


@pytest.mark.parametrize("seed", [0, 1, 2])
def test_ranking_agrees_with_sklearn(seed):
    """Both implementations should flag the same points as the most anomalous."""
    X, n = blob_with_outliers(seed)
    k = X.shape[0] - n

    ours = IsolationForest(random_state=seed).fit(X).score_samples(X)
    reference = sklearn_ensemble.IsolationForest(
        n_estimators=150, max_samples=256, random_state=seed,
    ).fit(X)
    # sklearn's score_samples is the negated anomaly score, so higher is normal.
    theirs = -reference.score_samples(X)

    top_ours = set(np.argsort(ours)[-k:])
    top_theirs = set(np.argsort(theirs)[-k:])
    overlap = len(top_ours & top_theirs) / k
    assert overlap >= 0.9, f"top-{k} overlap with sklearn was only {overlap:.0%}"

    correlation = np.corrcoef(ours, theirs)[0, 1]
    assert correlation > 0.9, f"score correlation with sklearn was {correlation:.2f}"


def test_scoring_is_deterministic():
    X, _ = blob_with_outliers()
    a = IsolationForest(random_state=7).fit(X).score_samples(X)
    b = IsolationForest(random_state=7).fit(X).score_samples(X)
    assert np.array_equal(a, b)


def test_scale_invariance():
    """Splits are drawn inside each feature's own range, so multiplying a
    column by a constant must not change the ranking. This is why the engine
    needs no StandardScaler."""
    X, _ = blob_with_outliers()
    stretched = X * np.array([1.0, 1000.0, 0.001, 1.0])
    a = IsolationForest(random_state=3).fit(X).score_samples(X)
    b = IsolationForest(random_state=3).fit(stretched).score_samples(stretched)
    assert np.corrcoef(a, b)[0, 1] > 0.95


def test_constant_data_does_not_crash():
    X = np.ones((40, 4))
    scores = IsolationForest(random_state=1).fit(X).score_samples(X)
    assert np.all(np.isfinite(scores))
