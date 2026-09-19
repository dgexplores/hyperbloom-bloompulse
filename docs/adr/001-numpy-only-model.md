# 001: NumPy-Only Model Implementation
**Date:** 2026-09-20
**Status:** Accepted

## Context
Vercel serverless functions have a 225MB deployment size limit. scikit-learn + SciPy exceed this limit when bundled with FastAPI, NumPy, and other dependencies.

## Decision
Implement all ML models (Isolation Forest, trend detection, physics-informed residual) using only NumPy. No SciPy, no scikit-learn, no heavy ML libraries.

## Consequences
- **Positive:** Function size stays well under 225MB (~30MB). Cold starts fast. No binary wheel compatibility issues.
- **Negative:** More implementation effort. Must maintain numerical correctness manually. No battle-tested library optimizations.
- **Mitigation:** Comprehensive property-based tests (Hypothesis) + adversarial eval + mutation testing on model code.

## Alternatives Considered
- scikit-learn + SciPy with aggressive pruning → risky, size unpredictable
- ONNX runtime + exported models → adds complexity, still needs training lib
- External ML API → violates "no API key, no external call" constraint