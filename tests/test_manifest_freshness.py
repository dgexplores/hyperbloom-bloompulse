"""Freshness check for corpus/manifest.json (Prove-It for CI failure).

CI runs `python corpus/build_manifest.py` then `git diff --exit-code`.
`build()` stamps `generated_at=now()` on every run, so the diff is never
empty and the backend job always fails even when no source changed.
"""
import json
from pathlib import Path

from corpus.build_manifest import build

MANIFEST = Path(__file__).resolve().parent.parent / "corpus" / "manifest.json"


def test_rebuild_preserves_generated_at_when_nothing_changed():
    """Re-running the builder on unchanged sources must be a no-op."""
    existing = json.loads(MANIFEST.read_text(encoding="utf-8"))
    rebuilt = build()
    assert rebuilt["generated_at"] == existing["generated_at"], (
        f"builder rewrote generated_at {existing['generated_at']} -> "
        f"{rebuilt['generated_at']} with no source change; "
        "CI diff can never be clean"
    )
    assert rebuilt["sources"] == existing["sources"]
    assert rebuilt["corpus_hash"] == existing["corpus_hash"]
