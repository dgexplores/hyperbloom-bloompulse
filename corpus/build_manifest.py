"""Regenerate corpus/manifest.json with real digests of the source files.

Run after editing anything under corpus/sources/. The test suite fails if the
manifest and the files on disk disagree, so provenance cannot drift silently.

    PYTHONPATH=. python corpus/build_manifest.py
    PYTHONPATH=. python corpus/build_manifest.py --check
"""
from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

CORPUS = Path(__file__).resolve().parent
MANIFEST = CORPUS / "manifest.json"


def build() -> dict:
    existing = json.loads(MANIFEST.read_text(encoding="utf-8")) if MANIFEST.exists() else {}

    sources = []
    for path in sorted((CORPUS / "sources").glob("*.md")):
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        sources.append({
            "doc_id": path.stem.replace("_", "-"),
            "path": f"corpus/sources/{path.name}",
            "sha256": digest,
            "bytes": path.stat().st_size,
        })

    # One digest over the per-file digests, so the corpus as a whole has an id.
    rollup = hashlib.sha256(
        "".join(source["sha256"] for source in sources).encode()
    ).hexdigest()

    version = existing.get("version", "bloompulse-2026.08.31-v1")
    corpus_hash = f"sha256:{rollup}"

    # A rebuild with no content change must be a no-op, otherwise every run
    # rewrites generated_at and `git diff --exit-code` can never be clean.
    if (
        existing.get("sources") == sources
        and existing.get("corpus_hash") == corpus_hash
        and existing.get("generated_at")
    ):
        generated_at = existing["generated_at"]
    else:
        generated_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()

    return {
        "version": version,
        "corpus_hash": corpus_hash,
        "generated_at": generated_at,
        "sources": sources,
        "retrieval": "offline extractive, spans parsed verbatim from the files above",
        "free_tier": True,
    }


def is_current() -> bool:
    """True when the manifest on disk matches what build() would write."""
    if not MANIFEST.exists():
        return False
    existing = json.loads(MANIFEST.read_text(encoding="utf-8"))
    return build() == existing


if __name__ == "__main__":
    if "--check" in sys.argv:
        if is_current():
            print("corpus/manifest.json is current")
        else:
            print(
                "::error::corpus/manifest.json is stale. "
                "Run: PYTHONPATH=. python corpus/build_manifest.py",
                file=sys.stderr,
            )
            sys.exit(1)
    else:
        manifest = build()
        MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        print(f"wrote {MANIFEST}")
        for source in manifest["sources"]:
            print(f"  {source['sha256'][:16]}  {source['path']}")
