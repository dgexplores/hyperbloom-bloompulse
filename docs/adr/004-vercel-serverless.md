# 004: Vercel Serverless Over Containers
**Date:** 2026-09-20
**Status:** Accepted

## Context
Options: Vercel (current), Fly.io, Railway, Render, AWS Lambda, GCP Cloud Run.

## Decision
Stay on Vercel for serverless function + static hosting. Free tier sufficient for demo. Native Next.js/Vite integration. Zero config.

## Consequences
- **Positive:** Zero cost. Automatic scaling. Global edge. Git-integrated deploys. Preview deploys on PR.
- **Negative:** 225MB function limit. 10s/60s timeout (hobby/pro). Cold starts. Vendor lock-in.
- **Mitigation:** NumPy-only keeps size low. Async streaming for large uploads. Function size budget gate in CI.

## Alternatives Considered
- Fly.io containers → more control, but cost + ops
- AWS Lambda + API Gateway → complex, cost at scale
- Self-hosted → not for demo/hackathon