# BloomPulse, project description

*Hyperbloom September, AI/ML.*

## What I built

BloomPulse reads a plain CSV of industrial sensor readings and returns a bounded
verdict on a machine's condition, where every claim quotes the passage of the
published standard it rests on.

Upload a file. You get a severity, a 7 day failure probability, the channel
driving it, a work order, and the citations that justify all of it. No sensors
to install, no gateway, no vendor contract, no API key, no account.

## Why it matters

Predictive maintenance is priced and packaged for large plants. Small and
mid-size manufacturers carry the same OSHA exposure without it, and the numbers
are not small: a serious violation is up to $16,550 and a willful or repeated
one up to $165,514 per violation (OSHA, 2026 adjustment). Meanwhile the data
already exists. Any PLC or condition monitor logs temperature and vibration,
and it usually goes nowhere.

The gap is not sensing. It is that nobody turns the log into a defensible
decision. A maintenance supervisor cannot act on an anomaly score, because a
number with no source is not something you can put on a work order or defend to
an inspector.

## How the AI works

Two layers that check each other.

An Isolation Forest fits the opening slice of each series as that machine's own
baseline and scores how far the recent window has drifted from it. I implemented
it directly on numpy, because scikit-learn pulls in scipy and the three together
exceed the deployment's 225MB function limit. It is validated against
scikit-learn's implementation in the test suite: identical normalising constant,
at least 90% overlap on the most anomalous points, and score correlation above
0.9.

Fixed thresholds from ISO 10816-3 and manufacturer manuals then gate the result,
so a genuine physical breach escalates whatever the unsupervised model thinks,
and a model with no baseline to learn from cannot invent one.

Retrieval is offline and extractive. Citation spans are parsed verbatim from a
git-tracked corpus, and a test fails if any returned span is not found in it, so
the tool quotes a standard rather than paraphrasing one. Excerpts written for
the demo are labelled as synthetic. Below the confidence floor it abstains
instead of guessing.

## State

Deployed and working, 43 tests, CI, and an eval that measures span fidelity and
severity accuracy against labelled fixtures rather than asserting them. Twelve
defects were found and fixed during hardening, including an engine that leaked
one machine's baseline into the next request.

Built with FastAPI, React and numpy. MIT licensed.
