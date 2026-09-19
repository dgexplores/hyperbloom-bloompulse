# 002: Extractive Citations Only
**Date:** 2026-09-20
**Status:** Accepted

## Context
LLM paraphrasing of standards introduces hallucination risk. Maintenance engineers distrust outputs without verifiable sources.

## Decision
All citations must be verbatim spans from git-tracked corpus files (`corpus/sources/*.md`). No paraphrasing, no LLM-generated text in citations. Each citation carries: `span_text` (exact quote), `locator` (file:line), `deep_link` (GitHub URL), `confidence` (0-100).

## Consequences
- **Positive:** Auditability. Every claim traceable to source. Hallucination impossible in citations.
- **Negative:** Corpus maintenance manual. Coverage limited to tracked standards. Paraphrase flexibility lost.
- **Mitigation:** Automated PDF→markdown pipeline for corpus expansion (Phase 6). Hybrid search for recall.

## Alternatives Considered
- LLM paraphrase with citation → hallucination risk
- RAG with external vector DB → violates no-external-deps, adds cost
- Hybrid: extractive + LLM summary → summary not citable, confusing