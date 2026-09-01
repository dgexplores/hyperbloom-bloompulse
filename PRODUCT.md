# BloomPulse

## What it is

BloomPulse reads a plain CSV of industrial sensor readings and returns a bounded
verdict on a machine's condition, with every claim anchored to a verbatim,
locatable passage in a published standard.

Upload a file. Get a severity, a failure window, a root-cause channel, a work
order, and the citations that justify all of it. No sensors to install, no
gateway, no vendor contract, no API key.

## Mechanism

Two layers that check each other:

1. An Isolation Forest fits the opening slice of the series as a baseline and
   scores how far the recent window has drifted from it. It is implemented
   directly on numpy in `model/iforest.py`, because scikit-learn plus scipy
   does not fit inside the deployment's function size limit.
2. Fixed thresholds from ISO 10816-3 and the NTN bearing manual gate the result,
   so a genuine physical breach escalates whatever the unsupervised model thinks.

Retrieval is offline and extractive against a git-tracked corpus, so the tool
quotes a standard rather than paraphrasing one. A verdict it cannot support
above the confidence floor is reported as an abstention.

## Who uses it

Maintenance supervisors and plant engineers at small and mid-size US
manufacturers, the 70% with no predictive-maintenance program at all. They own
the machine, sign the work order, and answer for the OSHA citation.

They are not data scientists. They already read standards, nameplates and
drawings fluently, and they distrust a number that arrives without a source.

## The scene

A laptop in a shop-floor office or on a rolling cart. Overhead fluorescents,
often daylight. Interruptions. The output gets printed and walked to the person
holding the wrench, or pasted into a CMMS ticket.

## What must be true

- Every claim carries a verbatim span, a locator, a deep link and a version hash.
- Low confidence abstains rather than guessing.
- The verdict names the channel that drove it, and the standard that sets the limit.
- Nothing about the demo requires a key, an account, or hardware.
- The tool advises. It never substitutes for a certified inspection, and it says so.

## Constraints

- FastAPI plus a React/Vite single page, deployed on Vercel as static assets
  and one Python serverless function.
- The function budget is 225MB, which rules out scipy and therefore scikit-learn.
- CPU-only inference, no GPU and no external model call. About 40ms locally
  and under 100ms on the deployed function.
- Max 500 rows, 2MB per upload.
- MIT licensed. Corpus is public-domain or fair-use excerpt, tracked in a manifest.

## Context

Built solo for HyperBloom Hacks 2026. Judged on AI at the core, industrial
application, innovation, execution, and accessibility.

## Assumptions

Recorded from the existing codebase, README and the session brief rather than a
live interview. The audience and scene above are inferred from the stated market
(US SME manufacturing) and should be confirmed.
