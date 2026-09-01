# Demo guide, 90 seconds

Open https://hyperbloom-bloompulse.vercel.app, or run `make backend` and
`make frontend` locally.

To skip straight to a result, the demo is linkable:
`?demo=failing` and `?demo=healthy`.

1. **Open the page.** The chart is already there: pre-printed grid, ISO 10816-3
   zone bands down the right margin, and both alarm limits ruled across the
   paper at 2.8 and 4.5 mm/s. Nothing has been analysed yet. Say the line:
   *the limits are printed before any data arrives, so you can see what the
   machine is being judged against.*

2. **Click "Failing sample"**, or drag `model/sample_anomaly.csv` onto the
   field. The three pens draw left to right at constant chart speed.

3. **Point at the crossing.** The red vibration pen climbs through the dashed
   2.8 mm/s line and past the solid 4.5 mm/s line into Zone D. The EVENT flag
   marks the sample the verdict turns on.

4. **Read the verdict.** CRITICAL, 82% anomaly, 83% chance of failure inside
   7 days, 3 day window, driven by temperature rise. Confidence 92%, because
   two independent channels crossed their limits and agree.

5. **Scroll the authority column.** Four citations. Each carries the verbatim
   span, its locator, the sha256 of the corpus file it was parsed from, a
   Verify link, and one line saying why it was attached to this verdict. The
   NTN excerpt is tagged SYNTHETIC EXCERPT, because it was written for the demo.

6. **Click "Export work order".** A markdown work order downloads with the
   action, parts, downtime, lockout flag and every citation.

7. **Click "Healthy sample".** NORMAL, confidence 88%, no lockout, and it still
   cites ISO 10816-3 Zone A/B. The all-clear is a claim too, so it carries a
   source.

8. **Optional, the honest part.** Upload a CSV with a missing column. It comes
   back with a 400 naming the column and the expected header, not a crash.

9. **Close on `/docs`** for the OpenAPI schema, or `make eval` for the measured
   numbers: span fidelity, severity accuracy against labelled fixtures, and
   latency.
