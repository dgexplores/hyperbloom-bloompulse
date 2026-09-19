# 005: GitHub Actions CI Over Self-Hosted
**Date:** 2026-09-20
**Status:** Accepted

## Context
CI options: GitHub Actions, GitLab CI, CircleCI, Buildkite, self-hosted runners.

## Decision
GitHub Actions on `ubuntu-latest`. Free for public repos. Native GitHub integration. Adequate minutes.

## Consequences
- **Positive:** Zero cost. Zero maintenance. Matrix builds (Python 3.12/3.14). Artifact storage. Environments/protection rules.
- **Negative:** Limited minutes (but public = unlimited). No GPU. Shared runners = variable performance.
- **Mitigation:** Cache aggressively. Parallel jobs. Self-hosted only if scale demands.

## Alternatives Considered
- Self-hosted → ops burden, not justified
- CircleCI → cost at scale
- Buildkite → overkill